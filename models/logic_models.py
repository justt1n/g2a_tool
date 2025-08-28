from typing import List, Optional

from pydantic import BaseModel

from models.g2g_models import Offer
from models.sheet_models import Payload


class CompareTarget(BaseModel):
    name: str
    price: float


class AnalysisResult(BaseModel):
    competitor_name: str | None = None
    competitive_price: float | None = None
    top_sellers_for_log: List[Offer] | None = None
    sellers_below_min: List[Offer] | None = None


class PayloadResult(BaseModel):
    status: int  # 1 for success, 0 for failure
    payload: Payload
    competition: list[Offer] | None = None
    final_price: CompareTarget | None = None
    log_message: str | None = None

    offer_id: Optional[str] = None
    offer_type: Optional[str] = None

