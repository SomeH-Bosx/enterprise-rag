"""Enterprise RAG 命令行入口：入库 / 评测 / 检索消融对比。"""

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
    """Enterprise RAG 命令行工具。"""


@cli.command("ingest-dir")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def ingest_dir(directory: Path):
    """入库目录下的样例文档（pdf 及其他已支持类型）。"""
    service = IngestService(get_settings())
    patterns = ("*.pdf", "*.docx", "*.pptx", "*.md", "*.txt", "*.doc", "*.ppt")
    files: list[Path] = []
    for pat in patterns:
        files.extend(directory.glob(pat))
    files = sorted({p.resolve(): p for p in files}.values(), key=lambda p: p.name.lower())
    if not files:
        click.echo("No supported files found.")
        return
    for path in files:
        result = service.ingest_file(path)
        click.echo(
            f"OK {path.name} -> {result['doc_id']} ({result['chunk_count']} chunks)"
        )


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
    default=ROOT / "evaluation" / "phase5_report.md",
    show_default=True,
)
@click.option(
    "--json-out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=ROOT / "evaluation" / "phase5_report.json",
    show_default=True,
)
@click.option(
    "--skip-generation/--no-skip-generation",
    default=False,
    help="仅跑 Recall@K（不生成答案 / 不算 RAGAS-style）。",
)
def eval_cmd(questions: Path, report: Path, json_out: Path, skip_generation: bool):
    """Phase5：Recall@K + RAGAS-style；写出 Markdown + JSON 报告。"""
    settings = get_settings()
    qa = QAService(settings)
    result = run_eval(
        questions,
        report,
        qa_service=qa,
        settings=settings,
        skip_generation=skip_generation,
        json_report_path=json_out,
    )
    click.echo(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    click.echo(f"Markdown report: {result['report_path']}")
    if result.get("json_report_path"):
        click.echo(f"JSON report: {result['json_report_path']}")


@cli.command("compare")
@click.argument("question")
@click.option(
    "--out",
    type=click.Path(dir_okay=False, path_type=Path),
    default=ROOT / "docs" / "retrieval_ablation.md",
    show_default=True,
)
def compare_cmd(question: str, out: Path):
    """对比仅 Dense vs Dense+重排，并写出 Markdown（Phase2）。"""
    qa = QAService(get_settings())
    data = qa.compare_rerank(question)
    lines = [
        "# 检索消融对比（Phase2 Reranker）",
        "",
        f"问题: **{data['question']}**",
        "",
        "## 基线：仅 Dense Top-K（无重排）",
        "",
        "```json",
        json.dumps(data["baseline_dense"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Dense 宽召回 + 重排 → Top-N",
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
