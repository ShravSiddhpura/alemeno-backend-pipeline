from celery import Celery
from .config import settings
from .database import SessionLocal, engine
from .models import Job, Transaction, JobSummary
from .utils.data_processor import clean_and_detect_anomalies
from .utils.llm_client import GroqLLMClient
import datetime
import pandas as pd

celery_app = Celery("tasks", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

@celery_app.task(name="process_transaction_pipeline_job")
def process_transaction_pipeline_job(job_id: str, csv_bytes_str: bytes):
    db = SessionLocal()
    llm = GroqLLMClient()
    
    try:
        # Update system processing status
        job_record = db.query(Job).filter(Job.id == job_id).first()
        if not job_record: return
        job_record.status = "processing"
        db.commit()

        # Step a & b: Process & Clean Data frames
        df, raw_count, clean_count = clean_and_detect_anomalies(csv_bytes_str)
        job_record.row_count_raw = raw_count
        job_record.row_count_clean = clean_count
        
        # Step c: Batch LLM Classification
        missing_category_mask = df['original_category'].isna()
        unassigned_df = df[missing_category_mask]
        
        classifications_map = {}
        llm_failed_flag = False
        llm_raw_string_log = None
        
        if not unassigned_df.empty:
            # Structuring entities for safe context payload compression
            batch_payload = []
            for idx, row in unassigned_df.iterrows():
                batch_payload.append({
                    "index": int(idx),
                    "merchant": row["merchant"],
                    "amount": float(row["amount"]),
                    "notes": str(row["notes"]) if pd.notna(row["notes"]) else ""
                })
            
            try:
                # Fire single structured inference to fill categorical holes
                response_dict = llm.classify_transaction_batch(batch_payload)
                llm_raw_string_log = str(response_dict)
                for item in response_dict.get("classifications", []):
                    classifications_map[int(item["index"])] = item["category"]
            except Exception as e:
                llm_failed_flag = True
                llm_raw_string_log = f"Execution Error: {str(e)}"
        
        # Stage data out to relational storage records
        db_transactions = []
        for idx, row in df.iterrows():
            final_cat = row['category']
            applied_llm_cat = None
            
            if idx in classifications_map:
                applied_llm_cat = classifications_map[idx]
                final_cat = applied_llm_cat
            elif missing_category_mask.loc[idx] and not llm_failed_flag:
                final_cat = "Other" # Fallback if missing from LLM return array

            t = Transaction(
                job_id=job_id,
                txn_id=row['txn_id'],
                date=row['date'],
                merchant=row['merchant'],
                amount=float(row['amount']),
                currency=row['currency'],
                status=row['status'],
                category=final_cat,
                account_id=row['account_id'],
                is_anomaly=bool(row['is_anomaly']),
                anomaly_reason=row['anomaly_reason'],
                llm_category=applied_llm_cat,
                llm_raw_response=llm_raw_string_log if idx in classifications_map else None,
                llm_failed=llm_failed_flag if missing_category_mask.loc[idx] else False
            )
            db_transactions.append(t)
            
        db.bulk_save_objects(db_transactions)
        db.commit()

        # Step d: LLM Comprehensive Ledger Narrative Summary
        currency_groups = df.groupby('currency')['amount'].sum().to_dict()
        top_merchants_list = df['merchant'].value_counts().head(3).index.tolist()
        anomaly_count_val = int(df['is_anomaly'].sum())
        
        metadata_snapshot = {
            "total_spend_by_currency": currency_groups,
            "top_3_merchants": top_merchants_list,
            "anomaly_count": anomaly_count_val
        }
        
        try:
            narrative_res = llm.generate_narrative_summary(metadata_snapshot)
        except Exception as e:
            narrative_res = {
                "total_spend_by_currency": {k: float(v) for k, v in currency_groups.items()},
                "top_3_merchants": top_merchants_list,
                "anomaly_count": anomaly_count_val,
                "spending_narrative": "System failed to construct comprehensive narrative telemetry via LLM endpoints safely.",
                "risk_level": "medium"
            }
            
        summary_record = JobSummary(
            job_id=job_id,
            total_spend_inr=float(currency_groups.get('INR', 0.0)),
            total_spend_usd=float(currency_groups.get('USD', 0.0)),
            top_merchants=top_merchants_list,
            anomaly_count=anomaly_count_val,
            narrative=narrative_res.get("spending_narrative"),
            risk_level=narrative_res.get("risk_level", "low")
        )
        db.add(summary_record)
        
        # Complete Job Status tracking securely
        job_record.status = "completed"
        job_record.completed_at = datetime.datetime.utcnow()
        db.commit()

    except Exception as e:
        db.rollback()
        job_record = db.query(Job).filter(Job.id == job_id).first()
        if job_record:
            job_record.status = "failed"
            job_record.error_message = str(e)
            db.commit()
    finally:
        db.close()