"""
AI 설정 관리 API - 프로바이더/모델/API키 동적 변경 지원.
설정은 backend/ai_settings.json에 저장 (재시작 없이 즉시 적용).
"""
import json
import httpx
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from .deps import get_current_user
from ..models.user import User

router = APIRouter(prefix="/ai-config", tags=["ai-config"])
logger = logging.getLogger(__name__)

SETTINGS_FILE = Path(__file__).parent.parent.parent / "ai_settings.json"

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
    "gemini": {
        "label": "Gemini",
        "desc": "Google Gemini. 무료 티어(Flash) 포함.",
        "tier": "free",
        "needs_key": True,
        "needs_url": False,
        "models": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
        "key_url": "https://aistudio.google.com/apikey",
    },
}

DEFAULT_SETTINGS: dict = {
    "provider": "ollama",
    "model": "llama3.2",
    "api_key": "",
    "ollama_url": "http://localhost:11434",
}


def _load() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def _save(data: dict):
    SETTINGS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get_ai_config() -> dict:
    """auto_strategy.py 등 내부 서비스에서 현재 AI 설정을 가져올 때 사용"""
    return _load()


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


@router.get("")
async def get_config():
    """현재 AI 설정 반환 (API 키는 마스킹)"""
    cfg = _load()
    return {
        "provider": cfg.get("provider", "ollama"),
        "model": cfg.get("model", "llama3.2"),
        "api_key_masked": _mask_key(cfg.get("api_key", "")),
        "api_key_set": bool(cfg.get("api_key", "")),
        "ollama_url": cfg.get("ollama_url", "http://localhost:11434"),
        "providers": PROVIDERS_META,
    }


class AIConfigUpdate(BaseModel):
    provider: str
    model: str
    api_key: Optional[str] = None   # None 또는 빈 문자열이면 기존 키 유지
    ollama_url: Optional[str] = None


@router.post("")
async def save_config(body: AIConfigUpdate, user: User = Depends(get_current_user)):
    """AI 설정 저장"""
    if body.provider not in PROVIDERS_META:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 프로바이더: {body.provider}")

    cfg = _load()
    cfg["provider"] = body.provider
    cfg["model"] = body.model
    if body.api_key:                           # 새 키가 있을 때만 덮어씀
        cfg["api_key"] = body.api_key
    if body.ollama_url:
        cfg["ollama_url"] = body.ollama_url

    _save(cfg)
    logger.info(f"AI 설정 저장: provider={cfg['provider']} model={cfg['model']}")
    return {"ok": True, "provider": cfg["provider"], "model": cfg["model"]}


@router.post("/test")
async def test_connection(user: User = Depends(get_current_user)):
    """현재 저장된 설정으로 AI 연결 테스트"""
    cfg = _load()
    provider = cfg.get("provider", "ollama")
    api_key = cfg.get("api_key", "")

    try:
        if provider == "ollama":
            base = cfg.get("ollama_url", "http://localhost:11434")
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

        elif provider == "gemini":
            if not api_key:
                return {"ok": False, "message": "API 키가 설정되지 않았습니다."}
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                )
            ok = res.status_code == 200
            return {"ok": ok, "message": "Gemini 연결 성공" if ok else f"Gemini 오류: {res.status_code}"}

        return {"ok": False, "message": "알 수 없는 프로바이더"}

    except httpx.ConnectError:
        return {"ok": False, "message": f"서버에 연결할 수 없습니다. ({provider})"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
