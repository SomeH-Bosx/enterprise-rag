from __future__ import annotations

from langchain_core.documents import Document

SYSTEM_STRUCTURED = """你是企业知识库 RAG 问答助手。
硬性规则：
1. 仅依据检索到的上下文回答，禁止编造外部知识。
2. 若上下文不足以回答，final_answer 必须为：文档中未找到相关内容。
3. 必须进行简短分步推理，写入 reasoning_summary。
4. relevant_pages 只能填写上下文中出现过的页码。
5. 输出必须是合法 JSON，字段为：
   final_answer, reasoning_summary, relevant_pages
不要输出 Markdown 代码块。"""


def build_context(documents: list[Document]) -> str:
    blocks: list[str] = []
    for doc in documents:
        meta = doc.metadata or {}
        page = meta.get("page", "N/A")
        source = meta.get("source") or meta.get("filename") or meta.get("doc_id") or "unknown"
        blocks.append(
            f'Text retrieved from page {page} (source={source}):\n"""\n{doc.page_content}\n"""'
        )
    return "\n\n---\n\n".join(blocks)


def build_simple_prompt(context: str, question: str, history: str = "") -> str:
    history_block = ""
    if (history or "").strip():
        history_block = f"""对话历史（仅供理解指代与追问，回答仍必须依据下方检索上下文）：
{history.strip()}

"""
    return f"""仅依据下方检索上下文回答，禁止编造外部知识。
若无相关内容，直接回复：文档中未找到相关内容。
{history_block}检索上下文：
{context}

当前问题：{question}
"""


def build_casual_prompt(question: str, history: str = "") -> str:
    """Phase3 casual_chat path: answer without retrieval context."""
    history_block = ""
    if (history or "").strip():
        history_block = f"""对话历史：
{history.strip()}

"""
    return f"""你是企业知识库助手。当前问题属于闲聊，无需检索文档。
请用简洁、友好的中文直接回答。若被问到身份，说明你是企业知识库问答助手。
不要编造公司内部政策或文档内容。
{history_block}用户：{question}
助手："""


def build_structured_prompt(
    context: str,
    question: str,
    history: str = "",
) -> list[dict[str, str]]:
    history_block = ""
    if (history or "").strip():
        history_block = f"""对话历史（理解指代用）：
{history.strip()}

"""
    user = f"""{history_block}以下是检索上下文：
{context}

以下是当前问题：
"{question}"

请输出 JSON：
{{
  "final_answer": "...",
  "reasoning_summary": "...",
  "relevant_pages": [1, 2]
}}"""
    return [
        {"role": "system", "content": SYSTEM_STRUCTURED},
        {"role": "user", "content": user},
    ]
