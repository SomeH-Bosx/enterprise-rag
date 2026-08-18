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
from src.eval.runner import run_eval, run_rerank_ablation, refresh_ablation_reports_from_json, run_candidate_k_ablation
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
@click.option(
    "--rerank-ablation",
    is_flag=True,
    default=False,
    help="公平 Hybrid@20 消融：同一候选集上比较 RRF Top-5 vs Rerank Top-5（只测召回）。",
)
@click.option(
    "--candidate-k-ablation",
    is_flag=True,
    default=False,
    help="Hybrid@10/20/30 与 Hybrid@20+Rerank 的 candidate 宽度消融（只测召回，写入 candidate_k/）。",
)
def eval_cmd(
    questions: Path,
    report: Path,
    json_out: Path,
    skip_generation: bool,
    rerank_ablation: bool,
    candidate_k_ablation: bool,
):
    """Phase5：Recall@K + RAGAS-style；写出 Markdown + JSON 报告。"""
    if rerank_ablation and candidate_k_ablation:
        raise click.UsageError("Use either --rerank-ablation or --candidate-k-ablation, not both.")
    settings = get_settings()
    qa = QAService(settings)
    if candidate_k_ablation:
        result = run_candidate_k_ablation(
            questions,
            qa_service=qa,
            settings=settings,
        )
        click.echo(json.dumps(result["summary"]["recommendation"], ensure_ascii=False, indent=2))
        click.echo(f"Summary Markdown: {result['summary']['summary_path']}")
        if result["summary"].get("json_summary_path"):
            click.echo(f"Summary JSON: {result['summary']['json_summary_path']}")
        return
    if rerank_ablation:
        out_dir = ROOT / "evaluation" / "phase5"
        result = run_rerank_ablation(
            questions,
            qa_service=qa,
            settings=settings,
            report_a=out_dir / "recall_hybrid20.md",
            json_a=out_dir / "recall_hybrid20.json",
            report_b=out_dir / "recall_hybrid20_rerank.md",
            json_b=out_dir / "recall_hybrid20_rerank.json",
        )
        click.echo(
            json.dumps(
                {
                    "candidates_identical": result["candidates_identical"],
                    "A_hybrid20": result["A"]["metrics"],
                    "B_hybrid20_rerank": result["B"]["metrics"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        click.echo(f"A Markdown: {result['A']['report_path']}")
        click.echo(f"A JSON: {result['A'].get('json_report_path')}")
        click.echo(f"B Markdown: {result['B']['report_path']}")
        click.echo(f"B JSON: {result['B'].get('json_report_path')}")
        return
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
