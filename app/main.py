from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import uuid
from typing import Optional
from .database import get_db, Base, engine
from .models import Job, Transaction, JobSummary
from .schemas import JobUploadResponse, JobStatusResponse, JobResultsResponse

# Ensure tables are built upon container bootstrap initialization sequences
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI-Powered Transaction Pipeline Architecture", version="1.0.0")

@app.post("/jobs/upload", response_model=JobUploadResponse)
def upload_transactions_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid resource format extension. Only CSV logs processed.")
    
    job_id = str(uuid.uuid4())
    csv_bytes = file.file.read()
    
    # Save the base tracking record
    new_job = Job(id=job_id, filename=file.filename, status="pending")
    db.add(new_job)
    db.commit()
    
    # Send processing task off to Celery workers out of process
    from .tasks import process_transaction_pipeline_job
    process_transaction_pipeline_job.delay(job_id, csv_bytes)
    
    return {"job_id": job_id, "status": "pending"}

@app.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Requested transaction compilation tracking token not found.")
    
    summary_payload = None
    if job.status == "completed" and job.summary:
        summary_payload = {
            "total_spend_inr": job.summary.total_spend_inr,
            "total_spend_usd": job.summary.total_spend_usd,
            "top_merchants": job.summary.top_merchants,
            "anomaly_count": job.summary.anomaly_count,
            "narrative": job.summary.narrative,
            "risk_level": job.summary.risk_level
        }
        
    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "row_count_raw": job.row_count_raw,
        "row_count_clean": job.row_count_clean,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "error_message": job.error_message,
        "summary": summary_payload
    }

@app.get("/jobs/{job_id}/results", response_model=JobResultsResponse)
def get_job_results(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job tracking reference invalid.")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Data parsing execution unresolved. Current state: {job.status}")

    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    anomalies = [t for t in transactions if t.is_anomaly]
    
    # Synthesize interactive high-level metric aggregates
    breakdown = {}
    for t in transactions:
        cat = t.category or "Uncategorised"
        curr = t.currency or "UNKNOWN"
        if cat not in breakdown: breakdown[cat] = {}
        breakdown[cat][curr] = breakdown[cat].get(curr, 0.0) + (t.amount or 0.0)

    llm_summary_payload = {
        "total_spend_inr": job.summary.total_spend_inr,
        "total_spend_usd": job.summary.total_spend_usd,
        "top_merchants": job.summary.top_merchants,
        "anomaly_count": job.summary.anomaly_count,
        "narrative": job.summary.narrative,
        "risk_level": job.summary.risk_level
    } if job.summary else None

    return {
        "job_id": job.id,
        "status": job.status,
        "cleaned_transactions": transactions,
        "flagged_anomalies": anomalies,
        "per_category_spend_breakdown": breakdown,
        "llm_summary": llm_summary_payload
    }

@app.get("/jobs")
def list_all_jobs(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status.lower())
    jobs = query.order_by(Job.created_at.desc()).all()
    return [
        {
            "job_id": j.id,
            "filename": j.filename,
            "status": j.status,
            "row_count_raw": j.row_count_raw,
            "created_at": j.created_at
        } for j in jobs
    ]