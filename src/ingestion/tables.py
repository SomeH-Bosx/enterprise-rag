"""表格序列化：输出 Markdown 表，便于 RAG 文本检索。

Step3.6 扩展：供 PDF / DOCX / PPTX loader 使用，不改 Loader 注册架构。
"""

from __future__ import annotations

from typing import Any, Sequence


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = " ".join(text.split())
    # Escape pipes so Markdown columns stay intact
    return text.replace("|", "\\|")


def rows_to_markdown(rows: Sequence[Sequence[Any]]) -> str:
    """
    Convert a 2D row/cell matrix into a GitHub-flavored Markdown table.
    Empty matrices return "".
    """
    cleaned: list[list[str]] = []
    for row in rows:
        cells = [_cell(c) for c in row]
        if any(cells):
            cleaned.append(cells)
    if not cleaned:
        return ""

    width = max(len(r) for r in cleaned)
    normalized = [r + [""] * (width - len(r)) for r in cleaned]
    header = normalized[0]
    body = normalized[1:] if len(normalized) > 1 else []

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    # Single-row tables: keep header + separator only (still valid Markdown)
    return "\n".join(lines)


def pdfplumber_table_to_markdown(table: list[list[Any]] | None) -> str:
    if not table:
        return ""
    return rows_to_markdown(table)


def docx_table_to_markdown(table: Any) -> str:
    """python-docx Table → Markdown."""
    rows: list[list[str]] = []
    for row in table.rows:
        rows.append([(cell.text or "") for cell in row.cells])
    return rows_to_markdown(rows)


def pptx_table_to_markdown(table: Any) -> str:
    """python-pptx Table → Markdown."""
    rows: list[list[str]] = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            cells.append(cell.text_frame.text if cell.text_frame is not None else "")
        rows.append(cells)
    return rows_to_markdown(rows)
