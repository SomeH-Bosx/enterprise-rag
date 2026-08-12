from langchain_core.documents import Document

from src.reranker.lexical import LexicalReranker


def test_lexical_reranker_prefers_relevant_chunk():
    docs = [
        Document(page_content="Parking permits are required in lot B.", metadata={"chunk_id": "noise"}),
        Document(
            page_content="Nebula Search Appliance latency SLO: p95 under 200 milliseconds.",
            metadata={"chunk_id": "signal"},
        ),
        Document(page_content="Cafeteria menu updates every Monday.", metadata={"chunk_id": "noise2"}),
    ]
    ranked = LexicalReranker().rerank(
        "What is the p95 latency SLO for Nebula Search Appliance?",
        docs,
        top_n=2,
    )
    assert ranked[0].metadata["chunk_id"] == "signal"
    assert ranked[0].metadata["reranker"] == "lexical"
    assert len(ranked) == 2
