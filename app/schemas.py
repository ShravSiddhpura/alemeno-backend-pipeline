from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime

# --- API Interaction Schemas ---
class JobUploadResponse(BaseModel):
    job_id: str
    status: str

class JobStatusResponse(BaseModel):
    id: str
    filename: str
    status: str
    row_count_raw: int
    row_count_clean: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    summary: Optional[Dict] = None

class TransactionData(BaseModel):
    txn_id: Optional[str]
    date: Optional[str]
    merchant: Optional[str]
    amount: Optional[float]
    currency: Optional[str]
    status: Optional[str]
    category: Optional[str]
    account_id: Optional[str]
    is_anomaly: bool
    anomaly_reason: Optional[str]

class JobResultsResponse(BaseModel):
    job_id: str
    status: str
    cleaned_transactions: List[TransactionData]
    flagged_anomalies: List[TransactionData]
    per_category_spend_breakdown: Dict[str, Dict[str, float]]
    llm_summary: Optional[Dict] = None

# --- LLM Structured Output Schemas ---
class SingleClassification(BaseModel):
    index: int
    category: str  # Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, or Other

class BatchClassificationResponse(BaseModel):
    classifications: List[SingleClassification]

class FinalNarrativeResponse(BaseModel):
    total_spend_by_currency: Dict[str, float]
    top_3_merchants: List[str]
    anomaly_count: int
    spending_narrative: str
    risk_level: str  # low, medium, high