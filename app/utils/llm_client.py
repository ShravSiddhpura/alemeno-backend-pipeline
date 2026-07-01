import json
import time
from groq import Groq
from ..config import settings
from ..schemas import BatchClassificationResponse, FinalNarrativeResponse

class GroqLLMClient:
    def __init__(self):
        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = settings.GROQ_MODEL

    def execute_with_exponential_backoff(self, messages, response_format, retries=3):
        base_delay = 2.0
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == retries - 1:
                    raise e
                time.sleep(base_delay * (2 ** attempt))
        return None

    def classify_transaction_batch(self, items: list) -> dict:
        """
        Accepts a list of dicts: [{'index': int, 'merchant': str, 'amount': float, 'notes': str}]
        """
        prompt = (
            "You are a highly analytical context parser. Categorize these transactions into exactly one of: "
            "Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, or Other.\n"
            f"Input List: {json.dumps(items)}\n\n"
            "Respond using exact valid JSON adhering strictly to this schema: "
            "{ 'classifications': [ {'index': 0, 'category': 'Food'} ] }"
        )
        messages = [
            {"role": "system", "content": "You output strict valid JSON schemas mapping transaction entities."},
            {"role": "user", "content": prompt}
        ]
        raw_res = self.execute_with_exponential_backoff(messages, BatchClassificationResponse)
        return json.loads(raw_res)

    def generate_narrative_summary(self, dataset_summary_snapshot: dict) -> dict:
        prompt = (
            f"Analyze this payload of calculated operational financial indicators:\n{json.dumps(dataset_summary_snapshot)}\n\n"
            "Provide a final summary JSON structural output matching this payload framework:\n"
            "{\n"
            "  'total_spend_by_currency': {'INR': 0.0, 'USD': 0.0},\n"
            "  'top_3_merchants': ['merchantA', 'merchantB'],\n"
            "  'anomaly_count': 0,\n"
            "  'spending_narrative': '2-3 sentences evaluating the overall trajectory risk profile.',\n"
            "  'risk_level': 'low' \n"
            "}"
        )
        messages = [
            {"role": "system", "content": "You evaluate accounting ledger anomalies and formulate JSON executives."},
            {"role": "user", "content": prompt}
        ]
        raw_res = self.execute_with_exponential_backoff(messages, FinalNarrativeResponse)
        return json.loads(raw_res)