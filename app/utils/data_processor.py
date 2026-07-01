import pandas as pd
import numpy as np
import io

def clean_and_detect_anomalies(csv_bytes: bytes):
    df = pd.read_csv(io.BytesIO(csv_bytes))
    raw_count = len(df)
    
    # Drop exact duplicates
    df = df.drop_duplicates()
    
    # Clean Transaction IDs
    df['txn_id'] = df['txn_id'].fillna('').astype(str).str.strip()
    
    # Normalize Date formats to ISO 8601
    def parse_date(val):
        if pd.isna(val): return None
        for fmt in ('%d-%m-%Y', '%Y/%m/%dB', '%Y/%m/%d', '%Y-%m-%d'):
            try:
                return pd.to_datetime(str(val).strip(), format=fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        try:
            return pd.to_datetime(str(val).strip()).strftime('%Y-%m-%d')
        except:
            return str(val)

    df['date'] = df['date'].apply(parse_date)
    
    # Strip Currency Symbols from amounts
    df['amount'] = df['amount'].astype(str).str.replace(r'[\$,]', '', regex=True)
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0)
    
    # Normalize Text Formatting
    df['currency'] = df['currency'].fillna('').astype(str).str.upper().str.strip()
    df['status'] = df['status'].fillna('').astype(str).str.upper().str.strip()
    df['category'] = df['category'].fillna('').astype(str).str.strip()
    df['merchant'] = df['merchant'].fillna('').astype(str).str.strip()
    df['account_id'] = df['account_id'].fillna('UNKNOWN').astype(str).str.strip()
    
    # Save original user categories before filling blanks for downstream LLM workflow
    df['original_category'] = df['category'].replace('', np.nan)
    df['category'] = df['category'].replace('', 'Uncategorised')
    
    # Anomaly Detection Step 1: Statistical Outliers (3x Median)
    medians = df.groupby('account_id')['amount'].transform('median')
    df['is_outlier'] = df['amount'] > (3 * medians)
    
    # Anomaly Detection Step 2: Domestic Brands Alignment Anomaly
    domestic_brands = ['swiggy', 'ola', 'irctc']
    df['is_domestic_currency_anomaly'] = (df['currency'] == 'USD') & (df['merchant'].str.lower().isin(domestic_brands))
    
    # Synthesize Flag Assertions
    df['is_anomaly'] = df['is_outlier'] | df['is_domestic_currency_anomaly']
    
    def structural_reason(row):
        reasons = []
        if row['is_outlier']: reasons.append("Amount exceeds 3x account median standard deviation.")
        if row['is_domestic_currency_anomaly']: reasons.append("USD execution detected for traditional domestic infrastructure merchant.")
        return " | ".join(reasons) if reasons else None
        
    df['anomaly_reason'] = df.apply(structural_reason, axis=1)
    
    return df, raw_count, len(df)