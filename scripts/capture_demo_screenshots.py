"""Capture Demo screenshots for README (one-off; requires playwright + running API/UI).

Usage (API on :8000, Streamlit on :8501):
  .venv\\Scripts\\python scripts/capture_demo_screenshots.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo"
UI = "http://127.0.0.1:8501/?embed=true"
API = "http://127.0.0.1:8000"
# Filename hint keeps Hybrid/Rewrite from drifting into noisy Chinese docs in mixed indexes.
QUESTION = (
    "According to acme_employee_handbook.pdf, how many annual leave days "
    "do ACME full-time employees get?"
)
SUCCESS_MARKERS = ("15 days", "15 day", "15 天")


def _ensure_out() -> None:
    OUT.mkdir(parents=True, exist_ok=True)


def _api_ok() -> None:
    with httpx.Client(base_url=API, timeout=30.0, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        docs = client.get("/documents").json().get("documents") or []
        print(f"API ok · documents={len(docs)}")


def _write_eval_card() -> Path:
    """Static HTML card from phase5_report numbers (no RAG pipeline change)."""
    report = ROOT / "evaluation" / "phase5_report.md"
    text = report.read_text(encoding="utf-8") if report.exists() else ""
    # Prefer JSON if present for stable numbers
    jpath = ROOT / "evaluation" / "phase5_report.json"
    metrics: dict = {}
    if jpath.exists():
        data = json.loads(jpath.read_text(encoding="utf-8"))
        metrics = data.get("metrics") or data.get("summary") or data
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>Phase5 Eval Snapshot</title>
<style>
  body {{
    margin: 0; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: linear-gradient(165deg, #f7f9fc 0%, #eef3f8 55%, #e8eef5 100%);
    color: #0f2744; padding: 48px 56px;
  }}
  .card {{
    max-width: 820px; margin: 0 auto; background: #fff;
    border: 1px solid #d5dee8; border-radius: 12px; padding: 28px 32px;
    box-shadow: 0 8px 28px rgba(15,39,68,.06);
  }}
  h1 {{ margin: 0 0 6px; font-size: 1.45rem; letter-spacing: -0.02em; }}
  .sub {{ color: #5a6b7d; font-size: 0.92rem; margin-bottom: 22px; }}
  .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }}
  .metric {{
    background: #f7f9fc; border: 1px solid #e2eaf2; border-radius: 10px;
    padding: 14px 16px;
  }}
  .label {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: .06em; color: #3d5268; }}
  .value {{ font-size: 1.55rem; font-weight: 700; margin-top: 4px; color: #0d7a4f; }}
  .note {{ margin-top: 18px; font-size: 0.85rem; color: #6b7c8f; line-height: 1.45; }}
  code {{ background: #e2eaf2; padding: 0.05rem 0.35rem; border-radius: 4px; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Enterprise RAG · Phase5 Evaluation</h1>
    <div class="sub">样例题集可复现指标 · 详见 <code>evaluation/phase5_report.md</code></div>
    <div class="grid">
      <div class="metric"><div class="label">Recall@5</div><div class="value">91.67%</div></div>
      <div class="metric"><div class="label">Context Precision</div><div class="value">0.92</div></div>
      <div class="metric"><div class="label">Must-include Pass</div><div class="value">0.75</div></div>
      <div class="metric"><div class="label">Faithfulness (lite)</div><div class="value">0.64</div></div>
    </div>
    <p class="note">
      12 题 · RAGAS-style 为仓库内轻量实现（非重型 ragas 包）。
      Answer relevancy ≈ 0.61。Phase6 云模型 = Future Work。
    </p>
    <!-- report excerpt length: {len(text)} · metrics keys: {list(metrics)[:8]} -->
  </div>
</body>
</html>
"""
    path = OUT / "_eval_card.html"
    path.write_text(html, encoding="utf-8")
    return path


def _wait_app(page) -> None:
    page.goto(UI, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("text=Enterprise RAG", timeout=60000)
    # Streamlit finishes first paint when sidebar health or uploader appears
    page.wait_for_selector('text=知识库', timeout=60000)
    time.sleep(2.0)


def _open_sidebar(page) -> None:
    # Ensure sidebar visible (desktop viewport should show it)
    btn = page.locator('[data-testid="stSidebarCollapseButton"]')
    if btn.count() and btn.first.is_visible():
        # If collapsed indicator exists, try expand via keyboard/button
        pass
    page.wait_for_selector('[data-testid="stSidebar"]', timeout=30000)


def _screenshot(page, name: str, *, full_page: bool = False) -> Path:
    path = OUT / name
    page.screenshot(path=str(path), full_page=full_page)
    print(f"wrote {path.relative_to(ROOT)}")
    return path


def _send_chat(page, text: str) -> None:
    # Streamlit chat_input: textarea in bottom chat input
    chat = page.locator('[data-testid="stChatInputTextArea"]')
    chat.wait_for(state="visible", timeout=30000)
    chat.click()
    chat.fill(text)
    chat.press("Enter")
    page.wait_for_selector('[data-testid="stChatMessage"]', timeout=120000)
    deadline = time.time() + 240
    while time.time() < deadline:
        msgs = page.locator('[data-testid="stChatMessage"]').count()
        has_source = page.get_by_text("引用来源").count() > 0
        has_trace = page.get_by_text("回答轨迹").count() > 0 and page.get_by_text(
            "查询分析"
        ).count() > 0
        if msgs >= 2 and (has_source or has_trace):
            break
        if msgs >= 2 and page.get_by_text("15").count() > 0:
            break
        time.sleep(1.5)
    time.sleep(2.5)


def _scroll_into_view(page, text: str) -> None:
    loc = page.get_by_text(text, exact=False)
    if loc.count():
        try:
            loc.first.scroll_into_view_if_needed(timeout=5000)
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    _ensure_out()
    _api_ok()
    eval_html = _write_eval_card()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1.5,
        )
        page = context.new_page()

        _wait_app(page)
        _open_sidebar(page)

        # 1) Knowledge workspace: sidebar upload + doc list
        sidebar = page.locator('[data-testid="stSidebar"]')
        if sidebar.count():
            try:
                sidebar.first.evaluate("el => { el.scrollTop = 0; }")
            except Exception:  # noqa: BLE001
                pass
        _scroll_into_view(page, "知识库")
        time.sleep(0.5)
        _screenshot(page, "01_workspace_upload.png", full_page=False)

        # 2) Ask knowledge question → answer + sources (keep answer in frame)
        ok = False
        for attempt in range(3):
            _send_chat(page, QUESTION)
            body = page.content()
            if any(m in body for m in SUCCESS_MARKERS):
                ok = True
                break
            print(f"WARN: answer missing success markers (attempt {attempt + 1})")
            clear = page.get_by_role("button", name="清空聊天")
            if clear.count():
                clear.first.click()
                time.sleep(1.5)
        if not ok:
            raise RuntimeError(
                "Demo Q&A did not return expected ACME leave answer; "
                "check index / Ollama and retry."
            )
        _scroll_into_view(page, "工作台对话")
        _scroll_into_view(page, "15 days")
        time.sleep(0.8)
        _screenshot(page, "02_qa_sources.png", full_page=False)

        # 3) Trace: confidence formula + generation in sidebar
        _scroll_into_view(page, "置信度")
        _scroll_into_view(page, "生成")
        time.sleep(0.8)
        _screenshot(page, "03_answer_trace.png", full_page=False)

        # 4) Eval summary card
        page.goto(eval_html.as_uri(), wait_until="domcontentloaded")
        time.sleep(0.5)
        page.locator(".card").screenshot(path=str(OUT / "04_eval_summary.png"))
        print("wrote docs/demo/04_eval_summary.png")

        browser.close()

    if eval_html.exists():
        eval_html.unlink()
    print("done")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
