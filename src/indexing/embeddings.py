from functools import lru_cache

from langchain_ollama import OllamaEmbeddings

from src.config.settings import Settings, bypass_local_proxy, get_settings


@lru_cache
def get_embeddings(base_url: str | None = None, model: str | None = None) -> OllamaEmbeddings:
    bypass_local_proxy()
    settings = get_settings()
    return OllamaEmbeddings(
        model=model or settings.embed_model,
        base_url=base_url or settings.ollama_base_url,
    )


def reset_embeddings_cache() -> None:
    get_embeddings.cache_clear()
