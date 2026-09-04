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
# LLM may say "15 days" or "15 annual leave days" — accept either shape.
SUCCESS_MARKERS = ("15 days", "15 day", "15 天", "15 annual", "15 annual leave")


def _ensure_out() -> None:
    OUT.mkdir(parents=True, exist_ok=True)


def _api_ok() -> None:
    with httpx.Client(base_url=API, timeout=30.0, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        docs = client.get("/documents").json().get("documents") or []
        print(f"API ok · documents={len(docs)}")


def _pct(rate: float) -> str:
    return f"{rate * 100:.2f}%"


def _load_readme_aligned_rows() -> tuple[list[dict[str, str]], str]:
    """Rows matching README Retrieval Evaluation table (prefer candidate_k summary)."""
    # Fallback = README documented numbers
    defaults = [
        {"name": "Hybrid@10", "recall": "83.33%", "strict": "62.07%", "hl": False},
        {"name": "Hybrid@20", "recall": "83.33%", "strict": "62.07%", "hl": False},
        {"name": "Hybrid@30", "recall": "83.33%", "strict": "62.07%", "hl": False},
        {
            "name": "Hybrid@20 + Reranker",
            "recall": "86.67%",
            "strict": "75.86%",
            "hl": True,
        },
    ]
    summary_path = ROOT / "evaluation" / "phase5" / "candidate_k" / "summary.json"
    if not summary_path.exists():
        return defaults, "docs/eval.md · README fallback"
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    configs = data.get("configs") or []
    by_key = {str(c.get("key") or ""): c for c in configs}
    order = [
        ("hybrid10", "Hybrid@10", False),
        ("hybrid20", "Hybrid@20", False),
        ("hybrid30", "Hybrid@30", False),
        ("hybrid20_rerank", "Hybrid@20 + Reranker", True),
    ]
    rows: list[dict[str, str]] = []
    for key, label, hl in order:
        c = by_key.get(key)
        if not c:
            continue
        rows.append(
            {
                "name": label,
                "recall": _pct(float(c.get("recall_at_k") or 0)),
                "strict": _pct(float(c.get("strict_citation_page_hit_rate") or 0)),
                "hl": hl,
            }
        )
    if len(rows) < 4:
        return defaults, "docs/eval.md · README fallback"
    return rows, "evaluation/phase5/candidate_k · 30 题"


def _write_eval_card() -> Path:
    """Static HTML card aligned with README Retrieval Evaluation table."""
    rows, source = _load_readme_aligned_rows()
    trs = []
    for r in rows:
        cls = ' class="hl"' if r.get("hl") else ""
        trs.append(
            f"<tr{cls}><td>{r['name']}</td>"
            f"<td>{r['recall']}</td><td>{r['strict']}</td></tr>"
        )
    table_body = "\n      ".join(trs)
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
  .sub {{ color: #5a6b7d; font-size: 0.92rem; margin-bottom: 18px; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 0.98rem;
  }}
  th, td {{
    text-align: left; padding: 12px 14px; border-bottom: 1px solid #e2eaf2;
  }}
  th {{
    font-size: 0.72rem; text-transform: uppercase; letter-spacing: .05em;
    color: #3d5268; background: #f7f9fc;
  }}
  tr.hl td {{
    font-weight: 700; color: #0d7a4f; background: #f0faf5;
  }}
  .note {{ margin-top: 18px; font-size: 0.85rem; color: #6b7c8f; line-height: 1.5; }}
  code {{ background: #e2eaf2; padding: 0.05rem 0.35rem; border-radius: 4px; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Enterprise RAG · Phase5 Evaluation</h1>
    <div class="sub">来源 <code>{source}</code></div>
    <table>
      <thead>
        <tr><th>Configuration</th><th>Recall@5</th><th>Strict Citation</th></tr>
      </thead>
      <tbody>
      {table_body}
      </tbody>
    </table>
    <p class="note">
      30 题离线召回（Top-5 计分）；Strict Citation = <code>(filename, page)</code> 同时匹配。
      Hybrid@10/20/30 召回质量相同；加入 Reranker 后 Recall@5 83.33%→86.67%，
      严格引用 62.07%→75.86%。默认服务：Hybrid@20 + Reranker(Top-5)。详见 <code>docs/eval.md</code>。
    </p>
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


def _screenshot_answer_trace(page) -> Path:
    """Capture full Answer Trace stack from the sidebar (query → retrieve → rerank → gen → conf)."""
    page.set_viewport_size({"width": 900, "height": 2400})
    time.sleep(0.5)
    # Hide chrome above Trace; expand scroll containers so panels are not clipped
    page.evaluate(
        """() => {
      const sidebar = document.querySelector('[data-testid="stSidebar"]');
      if (!sidebar) return false;
      let title = null;
      for (const e of sidebar.querySelectorAll('p, div, span, h1, h2, h3, h4')) {
        if ((e.textContent || '').trim() === '回答轨迹') {
          title = e;
          break;
        }
      }
      if (!title) return false;

      // Walk up to a block that is a direct vertical section, then hide previous siblings
      let block = title;
      for (let i = 0; i < 8 && block.parentElement; i++) {
        const parent = block.parentElement;
        if (parent === sidebar || parent.getAttribute('data-testid') === 'stSidebarContent') {
          break;
        }
        // Prefer the Streamlit block/container that owns the Trace section
        if (
          parent.className &&
          String(parent.className).includes('stVerticalBlock') &&
          parent.parentElement
        ) {
          block = parent;
        } else {
          block = parent;
        }
      }

      // Hide everything in the sidebar vertical flow before the Trace title's ancestor chain
      const hideBefore = (root, stopEl) => {
        const kids = [...root.children];
        let found = false;
        for (const kid of kids) {
          if (kid.contains(stopEl) || kid === stopEl) {
            found = true;
            // Within this kid, hide earlier siblings of the path to stopEl
            if (kid !== stopEl) hideBefore(kid, stopEl);
            break;
          }
          kid.style.setProperty('display', 'none', 'important');
        }
        return found;
      };
      hideBefore(sidebar, title);

      // Unclip overflow so full Trace paints
      const all = [sidebar, ...sidebar.querySelectorAll('*')];
      for (const el of all) {
        const s = getComputedStyle(el);
        if (s.overflowY === 'auto' || s.overflowY === 'scroll' || s.overflow === 'auto') {
          el.style.setProperty('overflow', 'visible', 'important');
          el.style.setProperty('max-height', 'none', 'important');
          el.style.setProperty('height', 'auto', 'important');
        }
      }
      sidebar.style.setProperty('overflow', 'visible', 'important');
      sidebar.style.setProperty('height', 'auto', 'important');
      sidebar.style.setProperty('max-height', 'none', 'important');
      // Collapse main app area so viewport focuses sidebar
      const main = document.querySelector('[data-testid="stAppViewContainer"] section.main');
      if (main) main.style.setProperty('display', 'none', 'important');
      return true;
    }"""
    )
    time.sleep(0.8)
    path = OUT / "03_answer_trace.png"
    # Measure Trace content after hide/expand
    box = page.evaluate(
        """() => {
      const sidebar = document.querySelector('[data-testid="stSidebar"]');
      if (!sidebar) return null;
      let title = null;
      for (const e of sidebar.querySelectorAll('p, div, span')) {
        if ((e.textContent || '').trim() === '回答轨迹') { title = e; break; }
      }
      const sb = sidebar.getBoundingClientRect();
      const panels = [...sidebar.querySelectorAll('h4, [data-testid="stExpander"], .wk-panel')];
      let bottom = title ? title.getBoundingClientRect().bottom : sb.bottom;
      for (const el of panels) {
        const r = el.getBoundingClientRect();
        if (r.height > 0) bottom = Math.max(bottom, r.bottom);
      }
      // Also include last visible text nodes' containers
      const texts = ['置信度', '生成', '重排', '检索', '查询分析', '原始 Trace'];
      for (const t of texts) {
        for (const e of sidebar.querySelectorAll('p, h4, div, span')) {
          if ((e.textContent || '').trim().startsWith(t) || (e.textContent || '').trim() === t) {
            bottom = Math.max(bottom, e.getBoundingClientRect().bottom);
          }
        }
      }
      const top = title ? Math.max(0, title.getBoundingClientRect().y - 12) : Math.max(0, sb.y);
      return {
        x: Math.max(0, sb.x),
        y: top,
        width: Math.min(Math.max(sb.width, 360), window.innerWidth - Math.max(0, sb.x)),
        height: Math.min(Math.max(bottom - top + 32, 600), 2300),
      };
    }"""
    )
    if isinstance(box, dict) and float(box.get("width") or 0) > 10 and float(box.get("height") or 0) > 10:
        page.screenshot(
            path=str(path),
            clip={
                "x": float(box["x"]),
                "y": float(box["y"]),
                "width": float(box["width"]),
                "height": float(box["height"]),
            },
        )
    else:
        page.locator('[data-testid="stSidebar"]').first.screenshot(path=str(path))
    print(f"wrote {path.relative_to(ROOT)}")
    # Reload to restore UI for subsequent steps
    page.set_viewport_size({"width": 1440, "height": 900})
    return path


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

        # 3) Trace: sidebar panels (查询分析 → 检索 → 重排 → 生成 → 置信度)
        _screenshot_answer_trace(page)

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
