"""Generate two tiny sample PDFs for local demo/eval (no external deps)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "samples"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, lines: list[str]) -> None:
    content_lines = ["BT", "/F1 12 Tf", "50 750 Td"]
    for i, line in enumerate(lines):
        if i == 0:
            content_lines.append(f"({_escape(line)}) Tj")
        else:
            content_lines.append("0 -18 Td")
            content_lines.append(f"({_escape(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines)
    objects = [
        "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n",
        f"4 0 obj<< /Length {len(stream.encode('latin-1', errors='replace'))} >>stream\n{stream}\nendstream\nendobj\n",
        "5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    pdf = ["%PDF-1.4\n"]
    offsets = [0]
    for obj in objects:
        offsets.append(sum(len(x.encode("latin-1", errors="replace")) for x in pdf))
        pdf.append(obj)
    xref_pos = sum(len(x.encode("latin-1", errors="replace")) for x in pdf)
    xref = [f"xref\n0 {len(objects) + 1}\n", "0000000000 65535 f \n"]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n")
    trailer = (
        f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = "".join(pdf + xref + [trailer]).encode("latin-1", errors="replace")
    path.write_bytes(raw)


def main() -> None:
    write_pdf(
        OUT / "acme_employee_handbook.pdf",
        [
            "ACME Employee Handbook",
            "Paid leave policy: full-time employees receive 15 days annual leave.",
            "Remote work: employees may work remotely up to 3 days per week.",
            "Expense claims must be submitted within 30 days.",
        ],
    )
    write_pdf(
        OUT / "beta_product_spec.pdf",
        [
            "Beta Product Specification",
            "Product name: Nebula Search Appliance.",
            "Latency SLO: p95 query latency under 200 milliseconds.",
            "Supported connectors: PDF, Markdown, Confluence.",
        ],
    )
    # Longer mix so splitter creates multiple chunks for rerank demos.
    mix_lines = ["Enterprise Knowledge Mix Document"]
    mix_lines += [
        "Cafeteria menu updates every Monday and includes vegetarian options."
    ] * 25
    mix_lines += [
        "Nebula Search Appliance latency SLO: p95 query latency under 200 milliseconds."
    ] * 8
    mix_lines += [
        "Parking permits are required for all employee vehicles in lot B."
    ] * 25
    mix_lines += [
        "Supported connectors for Nebula include PDF, Markdown, and Confluence."
    ] * 8
    write_pdf(OUT / "enterprise_knowledge_mix.pdf", mix_lines)
    print(f"Wrote sample PDFs to {OUT}")


if __name__ == "__main__":
    main()
