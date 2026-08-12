from langchain_core.documents import Document

from src.generation.postprocess import validate_page_references
from src.retrieval.hybrid import rrf_fuse
from src.retrieval.router import route_query


def test_route_filename_match():
    docs = [
        {"doc_id": "a1", "filename": "acme_employee_handbook.pdf"},
        {"doc_id": "b1", "filename": "beta_product_spec.pdf"},
    ]
    decision = route_query("In acme_employee_handbook, how many leave days?", docs)
    assert decision.reason == "filename_match"
    assert decision.doc_ids == ["a1"]


def test_rrf_prefers_overlap():
    d1 = Document(page_content="a", metadata={"chunk_id": "1"})
    d2 = Document(page_content="b", metadata={"chunk_id": "2"})
    d3 = Document(page_content="c", metadata={"chunk_id": "3"})
    fused = rrf_fuse([[d1, d2], [d2, d3]])
    assert fused[0].metadata["chunk_id"] == "2"


def test_validate_pages_drops_hallucination():
    retrieval = [
        Document(page_content="x", metadata={"page": 1}),
        Document(page_content="y", metadata={"page": 2}),
    ]
    assert validate_page_references([1, 99], retrieval) == [1]
