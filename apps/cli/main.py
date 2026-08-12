from __future__ import annotations

import json
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config.logging import setup_logging
from src.config.settings import get_settings
from src.eval.runner import run_eval
from src.services.ingest_service import IngestService
from src.services.qa_service import QAService

setup_logging()


@click.group()
def cli():
    """Enterprise RAG CLI."""


@cli.command("ingest-dir")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def ingest_dir(directory: Path):
    """Ingest all PDFs under a directory."""
    service = IngestService(get_settings())
    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        click.echo("No PDF files found.")
        return
    for pdf in pdfs:
        result = service.ingest_pdf(pdf)
        click.echo(f"OK {pdf.name} -> {result['doc_id']} ({result['chunk_count']} chunks)")


@cli.command("eval")
@click.option(
    "--questions",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=ROOT / "data" / "eval" / "questions.json",
    show_default=True,
)
@click.option(
    "--report",
    type=click.Path(dir_okay=False, path_type=Path),
    default=ROOT / "data" / "eval" / "report.md",
    show_default=True,
)
def eval_cmd(questions: Path, report: Path):
    """Run mini evaluation and write report.md."""
    settings = get_settings()
    qa = QAService(settings)
    result = run_eval(questions, report, qa_service=qa, settings=settings)
    click.echo(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    click.echo(f"Report written to {result['report_path']}")


@cli.command("compare")
@click.argument("question")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=ROOT / "docs" / "retrieval_ablation.md",
    show_default=True,
)
def compare_cmd(question: str, out: Path):
    """Compare dense-only vs dense+rerank and write markdown (Phase2)."""
    qa = QAService(get_settings())
    data = qa.compare_rerank(question)
    lines = [
        "# Retrieval Ablation (Phase2 Reranker)",
        "",
        f"Question: **{data['question']}**",
        "",
        "## Baseline: Dense Top-K (no rerank)",
        "",
        "```json",
        json.dumps(data["baseline_dense"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Dense Recall + CrossEncoder Rerank → Top-N",
        "",
        "```json",
        json.dumps(data["dense_plus_rerank"], ensure_ascii=False, indent=2),
        "```",
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    click.echo(f"Wrote {out}")


if __name__ == "__main__":
    cli()
