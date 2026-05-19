"""
AI 설정 관리 API - 프로바이더/모델/API키 동적 변경 지원.
설정은 사용자별 DB에 저장 (재시작 없이 즉시 적용).
"""
import json
import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException
from pathlib import Path
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

_SETTINGS_FILE = Path(__file__).parent.parent.parent / "ai_settings.json"

from .deps import get_current_user
from ..core.database import get_db
from ..models.user import User
from ..models.user_ai_config import UserAIConfig
from ..services.auto_trade import ai_analyst

router = APIRouter(prefix="/ai-config", tags=["ai-config"])
logger = logging.getLogger(__name__)

PROVIDERS_META: dict = {
    "ollama": {
        "label": "Ollama",
        "desc": "로컬에서 직접 실행. 인터넷 불필요. 완전 무료.",
        "tier": "free",
        "needs_key": False,
        "needs_url": True,
        "models": ["llama3.2", "llama3.1", "mistral", "gemma2", "qwen2.5", "deepseek-r1"],
        "key_url": None,
    },
    "groq": {
        "label": "Groq",
        "desc": "무료 API 티어 제공. 빠른 추론 속도.",
        "tier": "free",
        "needs_key": True,
        "needs_url": False,
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
        "key_url": "https://console.groq.com",
    },
    "anthropic": {
        "label": "Claude",
        "desc": "Anthropic Claude. 높은 추론 품질.",
        "tier": "paid",
        "needs_key": True,
        "needs_url": False,
        "models": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-6"],
        "key_url": "https://console.anthropic.com",
    },
    "openai": {
        "label": "ChatGPT",
        "desc": "OpenAI GPT 모델. 범용적으로 우수.",
        "tier": "paid",
        "needs_key": True,
        "needs_url": False,
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
        "key_url": "https://platform.openai.com/api-keys",
    },
    "grok": {
        "label": "Grok (xAI)",
        "desc": "xAI의 Grok 모델. OpenAI 호환 API.",
        "tier": "paid",
        "needs_key": True,
        "needs_url": False,
        "models": ["grok-3-mini", "grok-3", "grok-2"],
        "key_url": "https://console.x.ai",
    },
}


async def _get_or_create_config(user_id: int, db: AsyncSession) -> UserAIConfig:
    result = await db.execute(select(UserAIConfig).where(UserAIConfig.user_id == user_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = UserAIConfig(user_id=user_id)
        db.add(cfg)
        await db.flush()
    return cfg


async def get_user_ai_config(user_id: int, db: AsyncSession) -> dict:
    """내부 서비스에서 사용자별 AI 설정을 가져올 때 사용"""
    result = await db.execute(select(UserAIConfig).where(UserAIConfig.user_id == user_id))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return {"provider": "ollama", "model": "llama3.2", "api_key": "", "ollama_url": "http://localhost:11434"}
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "api_key": cfg.api_key,
        "ollama_url": cfg.ollama_url,
    }


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


@router.get("")
async def get_config(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 AI 설정 반환 (API 키는 마스킹)"""
    cfg = await _get_or_create_config(user.id, db)
    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "api_key_masked": _mask_key(cfg.api_key),
        "api_key_set": bool(cfg.api_key),
        "ollama_url": cfg.ollama_url,
        "providers": PROVIDERS_META,
    }


class AIConfigUpdate(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None
    ollama_url: Optional[str] = None


@router.post("")
async def save_config(
    body: AIConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 AI 설정 저장"""
    if body.provider not in PROVIDERS_META:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 프로바이더: {body.provider}")

    cfg = await _get_or_create_config(user.id, db)
    cfg.provider = body.provider
    cfg.model = body.model
    if body.api_key:
        cfg.api_key = body.api_key
    if body.ollama_url:
        cfg.ollama_url = body.ollama_url

    # 런타임 메모리에 즉시 반영 (재시작 없이 모든 프로바이더 즉시 적용)
    cfg_dict = {
        "provider": cfg.provider,
        "model": cfg.model,
        "api_key": cfg.api_key or "",
        "ollama_url": cfg.ollama_url or "http://localhost:11434",
    }
    ai_analyst.set_config(cfg_dict)

    # 파일도 갱신 (서버 재시작 후 복원용)
    try:
        _SETTINGS_FILE.write_text(json.dumps(cfg_dict, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"ai_settings.json 갱신 실패: {e}")

    logger.info(f"AI 설정 저장: user={user.id} provider={cfg.provider} model={cfg.model}")
    return {"ok": True, "provider": cfg.provider, "model": cfg.model}


@router.post("/test")
async def test_connection(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 저장된 설정으로 AI 연결 테스트"""
    cfg_dict = await get_user_ai_config(user.id, db)
    provider = cfg_dict.get("provider", "ollama")
    api_key = cfg_dict.get("api_key", "")

    try:
        if provider == "ollama":
            base = cfg_dict.get("ollama_url", "http://localhost:11434")
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{base}/api/tags")
            if res.status_code == 200:
                models = [m["name"] for m in res.json().get("models", [])]
                return {"ok": True, "message": f"Ollama 연결 성공 (설치된 모델: {len(models)}개)"}
            return {"ok": False, "message": f"Ollama 응답 오류 ({res.status_code})"}

        elif provider == "groq":
            if not api_key:
                return {"ok": False, "message": "API 키가 설정되지 않았습니다."}
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            ok = res.status_code == 200
            return {"ok": ok, "message": "Groq 연결 성공" if ok else f"Groq 오류: {res.status_code}"}

        elif provider == "anthropic":
            if not api_key:
                return {"ok": False, "message": "API 키가 설정되지 않았습니다."}
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                )
            ok = res.status_code == 200
            return {"ok": ok, "message": "Claude 연결 성공" if ok else f"Claude 오류: {res.status_code}"}

        elif provider == "openai":
            if not api_key:
                return {"ok": False, "message": "API 키가 설정되지 않았습니다."}
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            ok = res.status_code == 200
            return {"ok": ok, "message": "OpenAI 연결 성공" if ok else f"OpenAI 오류: {res.status_code}"}

        elif provider == "grok":
            if not api_key:
                return {"ok": False, "message": "API 키가 설정되지 않았습니다."}
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            ok = res.status_code == 200
            return {"ok": ok, "message": "Grok 연결 성공" if ok else f"Grok 오류: {res.status_code}"}

        return {"ok": False, "message": "알 수 없는 프로바이더"}

    except httpx.ConnectError:
        return {"ok": False, "message": f"서버에 연결할 수 없습니다. ({provider})"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
