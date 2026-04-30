from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ExchangeAccountCreate(BaseModel):
    exchange: str           # binance, upbit, bybit, okx
    label: str              # 사용자 정의 이름
    api_key: str
    api_secret: str
    is_paper: bool = True


class ExchangeAccountUpdate(BaseModel):
    label: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    is_active: Optional[bool] = None


class ExchangeAccountRead(BaseModel):
    id: int
    exchange: str
    label: str
    api_key_masked: str     # 마스킹된 키만 반환 (보안)
    is_paper: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
