from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..core.encryption import encrypt, decrypt, mask
from ..models.user import User
from ..models.exchange_account import ExchangeAccount
from ..schemas.exchange_account import (
    ExchangeAccountCreate,
    ExchangeAccountUpdate,
    ExchangeAccountRead,
)
from .deps import get_current_user

router = APIRouter(prefix="/exchange-accounts", tags=["exchange-accounts"])

SUPPORTED_EXCHANGES = ["upbit", "binance", "bybit"]

# 거래소별 BTC 연결 테스트 심볼
_BTC_SYMBOL: dict[str, str] = {
    "upbit":   "BTC/KRW",
    "binance": "BTC/USDT",
    "bybit":   "BTC/USDT",
}


def _to_read(account: ExchangeAccount) -> ExchangeAccountRead:
    plain_key = decrypt(account.api_key_encrypted)
    return ExchangeAccountRead(
        id=account.id,
        exchange=account.exchange,
        label=account.label,
        api_key_masked=mask(plain_key),
        is_paper=account.is_paper,
        is_active=account.is_active,
        created_at=account.created_at,
    )


async def _get_account_or_404(account_id: int, user: User, db: AsyncSession) -> ExchangeAccount:
    result = await db.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.id == account_id,
            ExchangeAccount.user_id == user.id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="거래소 계정을 찾을 수 없습니다.")
    return account


def _make_connector(account: ExchangeAccount):
    from ..services.exchange.connector import ExchangeConnector
    return ExchangeConnector(
        exchange_id=account.exchange,
        api_key=decrypt(account.api_key_encrypted),
        api_secret=decrypt(account.api_secret_encrypted),
        is_paper=account.is_paper,
    )


@router.get("/", response_model=list[ExchangeAccountRead])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ExchangeAccount)
        .where(ExchangeAccount.user_id == user.id)
        .order_by(ExchangeAccount.created_at.desc())
    )
    return [_to_read(a) for a in result.scalars().all()]


@router.post("/", response_model=ExchangeAccountRead, status_code=201)
async def create_account(
    data: ExchangeAccountCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if data.exchange not in SUPPORTED_EXCHANGES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 거래소입니다. 지원: {', '.join(SUPPORTED_EXCHANGES)}",
        )
    if not data.api_key.strip() or not data.api_secret.strip():
        raise HTTPException(status_code=400, detail="API 키와 시크릿을 모두 입력해주세요.")

    account = ExchangeAccount(
        user_id=user.id,
        exchange=data.exchange,
        label=data.label,
        api_key_encrypted=encrypt(data.api_key.strip()),
        api_secret_encrypted=encrypt(data.api_secret.strip()),
        is_paper=data.is_paper,
        is_active=True,
    )
    db.add(account)
    await db.flush()
    return _to_read(account)


@router.patch("/{account_id}", response_model=ExchangeAccountRead)
async def update_account(
    account_id: int,
    data: ExchangeAccountUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = await _get_account_or_404(account_id, user, db)

    if data.label is not None:
        account.label = data.label
    if data.api_key is not None and data.api_key.strip():
        account.api_key_encrypted = encrypt(data.api_key.strip())
    if data.api_secret is not None and data.api_secret.strip():
        account.api_secret_encrypted = encrypt(data.api_secret.strip())
    if data.is_active is not None:
        account.is_active = data.is_active

    await db.flush()
    return _to_read(account)


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = await _get_account_or_404(account_id, user, db)
    await db.delete(account)


@router.get("/portfolio")
async def get_portfolio(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """모든 실거래 계정의 총 자산을 KRW로 합산"""
    result = await db.execute(
        select(ExchangeAccount).where(
            ExchangeAccount.user_id == user.id,
            ExchangeAccount.is_paper == False,
            ExchangeAccount.is_active == True,
        )
    )
    accounts = result.scalars().all()

    if not accounts:
        return {"has_real_account": False, "total_krw": 0, "accounts": []}

    from ..services.exchange.connector import ExchangeConnector as EC
    total_krw = 0.0
    account_list = []

    for account in accounts:
        connector = _make_connector(account)
        try:
            raw = await connector.fetch_balance()
            await connector.close()
        except Exception:
            await connector.close()
            continue

        krw = float((raw.get("KRW") or {}).get("free") or 0)
        coins_krw = 0.0

        for currency, info in raw.items():
            if currency in ("info", "free", "used", "total", "datetime", "timestamp", "KRW"):
                continue
            if not isinstance(info, dict):
                continue
            amount = float(info.get("free") or 0)
            if amount <= 0:
                continue
            try:
                pub = EC(exchange_id=account.exchange, is_paper=True)
                ticker = await pub.fetch_ticker(f"{currency}/KRW")
                await pub.close()
                coins_krw += amount * float(ticker["last"])
            except Exception:
                pass

        account_total = krw + coins_krw
        total_krw += account_total
        account_list.append({
            "account_id": account.id,
            "label": account.label,
            "krw_free": krw,
            "coins_krw": coins_krw,
            "total_krw": account_total,
        })

    return {"has_real_account": True, "total_krw": total_krw, "accounts": account_list}


@router.get("/{account_id}/test")
async def test_connection(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = await _get_account_or_404(account_id, user, db)
    connector = _make_connector(account)
    btc_symbol = _BTC_SYMBOL.get(account.exchange, "BTC/USDT")
    try:
        ticker = await connector.fetch_ticker(btc_symbol)
        await connector.close()
        return {
            "ok": True,
            "btc_price": ticker["last"],
            "quote": "KRW" if account.exchange == "upbit" else "USDT",
        }
    except Exception as e:
        await connector.close()
        return {"ok": False, "error": str(e)}


@router.get("/{account_id}/balance")
async def get_balance(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = await _get_account_or_404(account_id, user, db)

    if account.is_paper:
        raise HTTPException(status_code=400, detail="모의거래 계정은 잔고 조회를 지원하지 않습니다.")

    connector = _make_connector(account)
    try:
        raw = await connector.fetch_balance()
        await connector.close()
    except Exception as e:
        await connector.close()
        raise HTTPException(status_code=502, detail=f"잔고 조회 실패: {e}")

    # 보유량이 있는 자산만 반환
    balances = []
    for currency, info in raw.items():
        if currency in ("info", "free", "used", "total", "datetime", "timestamp"):
            continue
        if not isinstance(info, dict):
            continue
        total = info.get("total") or 0
        if total > 0:
            balances.append({
                "currency": currency,
                "free": info.get("free") or 0,
                "used": info.get("used") or 0,
                "total": total,
            })

    return {"balances": balances}


@router.get("/{account_id}/deposit-address/{currency}")
async def get_deposit_address(
    account_id: int,
    currency: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = await _get_account_or_404(account_id, user, db)

    if account.is_paper:
        raise HTTPException(status_code=400, detail="모의거래 계정은 입금 주소를 지원하지 않습니다.")

    currency = currency.upper()
    if currency == "KRW":
        raise HTTPException(status_code=400, detail="KRW 입금은 업비트 앱/웹에서 계좌이체로 진행해주세요.")

    connector = _make_connector(account)
    try:
        result = await connector._exchange.fetch_deposit_address(currency)
        await connector.close()
        return {
            "currency": currency,
            "address": result.get("address"),
            "tag": result.get("tag"),
        }
    except Exception as e:
        await connector.close()
        raise HTTPException(status_code=502, detail=f"입금 주소 조회 실패: {e}")
