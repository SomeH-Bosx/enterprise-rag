from __future__ import annotations

from functools import lru_cache

import httpx
from langchain_ollama import ChatOllama, OllamaLLM

from src.config.settings import Settings, bypass_local_proxy, get_settings


@lru_cache
def get_chat_llm(base_url: str | None = None, model: str | None = None, temperature: float | None = None):
    bypass_local_proxy()
    settings = get_settings()
    return ChatOllama(
        model=model or settings.llm_model,
        base_url=base_url or settings.ollama_base_url,
        temperature=settings.llm_temperature if temperature is None else temperature,
    )


@lru_cache
def get_completion_llm(base_url: str | None = None, model: str | None = None):
    bypass_local_proxy()
    settings = get_settings()
    return OllamaLLM(
        model=model or settings.llm_model,
        base_url=base_url or settings.ollama_base_url,
    )


def invoke_chat(messages: list[dict[str, str]], settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    llm = get_chat_llm(
        base_url=cfg.ollama_base_url,
        model=cfg.llm_model,
        temperature=cfg.llm_temperature,
    )
    result = llm.invoke(messages)
    content = getattr(result, "content", result)
    return str(content)


def invoke_text(prompt: str, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    llm = get_completion_llm(base_url=cfg.ollama_base_url, model=cfg.llm_model)
    return str(llm.invoke(prompt))


def check_ollama_health(settings: Settings | None = None) -> dict:
    bypass_local_proxy()
    cfg = settings or get_settings()
    url = cfg.ollama_base_url.rstrip("/") + "/api/tags"
    try:
        with httpx.Client(timeout=3.0, trust_env=False) as client:
            resp = client.get(url)
            ok = resp.status_code == 200
            return {"ok": ok, "status_code": resp.status_code, "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "url": url}
