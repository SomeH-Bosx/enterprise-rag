from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config.settings import Settings, get_settings

CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


def build_splitter(settings: Settings | None = None) -> RecursiveCharacterTextSplitter:
    cfg = settings or get_settings()
    return RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
        separators=CHINESE_SEPARATORS,
    )


def split_documents(
    documents: list[Document],
    settings: Settings | None = None,
) -> list[Document]:
    splitter = build_splitter(settings)
    return splitter.split_documents(documents)
