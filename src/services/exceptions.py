class RagError(Exception):
    def __init__(self, message: str, error_code: str = "RAG_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class EmptyQueryError(RagError):
    def __init__(self, message: str = "Query is empty"):
        super().__init__(message, error_code="EMPTY_QUERY")


class NoIndexError(RagError):
    def __init__(self, message: str = "No documents indexed. Please ingest a PDF first."):
        super().__init__(message, error_code="NO_INDEX")


class DocumentNotFoundError(RagError):
    def __init__(self, doc_id: str):
        super().__init__(f"Document not found: {doc_id}", error_code="DOC_NOT_FOUND")


class IngestError(RagError):
    def __init__(self, message: str):
        super().__init__(message, error_code="INGEST_ERROR")
