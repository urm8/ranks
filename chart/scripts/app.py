"""HTTP server for ranks.urm8.org.

Serves the latest pre-computed snapshot written by parser.py (a separate
CronJob) from Postgres. This process never scrapes sources itself; see
parser.py for the parsing step.
"""

from __future__ import annotations

import html
import json
import os
import socket
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get("PORT", "8080"))
CACHE_SECONDS = int(os.environ.get("RANKS_CACHE_SECONDS", "300"))
TOP_VISIBLE = 5

_PAGE_HEAD = '<!doctype html>\n<html lang="en">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>AI Model Ranks</title>\n  <script src="https://js.puter.com/v2/"></script>\n  <style>\n    :root {\n      --bg: #ffffff;\n      --ink: #0a0a0a;\n      --muted: #737373;\n      --soft: #fafafa;\n      --card: #ffffff;\n      --line: #e5e5e5;\n      --line-strong: #d4d4d4;\n      --accent: #2563eb;\n      --accent-soft: #eff6ff;\n      --code: #171717;\n    }\n    * { box-sizing: border-box; }\n    body {\n      margin: 0;\n      color: var(--ink);\n      background: var(--bg);\n      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;\n    }\n    main { width: 100%; max-width: 72rem; margin: 0 auto; padding: 1rem 1.5rem 4rem; }\n    .eyebrow { color: var(--muted); font-size: 13px; font-weight: 500; letter-spacing: .01em; }\n    h1 { max-width: 58rem; margin: .75rem 0 1rem; font-size: clamp(2.25rem, 6vw, 4.5rem); line-height: 1; letter-spacing: -.055em; font-weight: 650; }\n    h2 { margin: 0; font-size: clamp(1.75rem, 4vw, 2.8rem); line-height: 1.06; letter-spacing: -.04em; font-weight: 650; }\n    h3 { margin: 1.65rem 0 .75rem; font-size: .9rem; line-height: 1.3; font-weight: 650; letter-spacing: -.01em; color: var(--ink); }\n    p { color: var(--muted); font-size: 1rem; line-height: 1.7; max-width: 50rem; }\n    a { color: var(--ink); text-decoration-color: var(--line-strong); text-underline-offset: 3px; }\n    a:hover { text-decoration-color: currentColor; }\n    nav { display: flex; flex-wrap: wrap; gap: .5rem; margin: 1.5rem 0 1.75rem; }\n    nav a, .bench { padding: .45rem .7rem; border: 1px solid var(--line); border-radius: 999px; background: var(--card); color: var(--ink); text-decoration: none; font-size: .82rem; font-weight: 500; }\n    nav a:hover, .bench:hover { border-color: var(--ink); }\n    .category, .chat-panel { scroll-margin-top: 1rem; }\n    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: .75rem; margin: 1.5rem 0; }\n    .stat, .category, .source { background: var(--card); border: 1px solid var(--line); }\n    .stat { padding: 1rem; border-radius: .75rem; }\n    .stat b { display: block; font-size: 1.55rem; line-height: 1.1; letter-spacing: -.03em; }\n    .stat span { color: var(--muted); font-size: .78rem; line-height: 1.4; }\n    .category { margin-top: 1.25rem; padding: 1.5rem; border-radius: .9rem; }\n    .category-head { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr); gap: 1rem; align-items: start; }\n    .benchmarks { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }\n    .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: .75rem; background: var(--card); }\n    .benchmark-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .85rem; }\n    .benchmark-card { border: 1px solid var(--line); border-radius: .75rem; padding: 1rem; background: var(--soft); }\n    .benchmark-title { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }\n    .benchmark-title h4 { margin: 0; font-size: 1rem; line-height: 1.35; font-weight: 600; }\n    .benchmark-title span { color: var(--muted); font-size: .72rem; font-weight: 600; text-transform: uppercase; }\n    .benchmark-card p { font-size: .9rem; margin: .55rem 0 .7rem; line-height: 1.55; }\n    .benchmark-card ol { list-style: none; padding: 0; margin: 0; display: grid; gap: .45rem; }\n    .benchmark-card li { display: grid; grid-template-columns: auto 1fr auto; gap: .5rem; align-items: baseline; padding: .55rem; border-radius: .55rem; background: var(--card); border: 1px solid var(--line); }\n    .benchmark-card li small { grid-column: 2 / span 2; color: var(--muted); font-size: .75rem; line-height: 1.45; }\n    .benchmark-card li em { color: var(--accent); font-style: normal; font-weight: 600; }\n    .benchmark-links { display: flex; gap: .75rem; margin-top: .7rem; font-size: .82rem; font-weight: 500; }\n    table { width: 100%; border-collapse: collapse; min-width: 920px; }\n    th, td { padding: .8rem .9rem; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; font-size: .9rem; }\n    th { color: var(--muted); font-size: .72rem; line-height: 1.2; font-weight: 650; letter-spacing: .04em; text-transform: uppercase; }\n    td span { display: block; color: var(--muted); font-size: .75rem; margin-top: .2rem; }\n    tr:last-child td { border-bottom: 0; }\n    .rank { color: var(--accent); font-weight: 650; }\n    .badge { display: inline-block; padding: .2rem .5rem; border-radius: 999px; border: 1px solid var(--line-strong); font-size: .72rem; font-weight: 600; color: var(--muted); }\n    .sources { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem; margin-top: 1.4rem; }\n    .source { display: block; min-height: 92px; padding: 1rem; border-radius: .75rem; text-decoration: none; box-shadow: none; }\n    .source:hover { border-color: var(--ink); }\n    .source b, .source span { display: block; }\n    .source span { color: var(--muted); margin-top: .5rem; font-size: .75rem; line-height: 1.4; }\n    .source.fail { opacity: .68; }\n    .note { margin-top: 1.1rem; font-size: .88rem; }\n    .chat-panel { display: grid; grid-template-columns: minmax(0, .9fr) minmax(320px, 1.1fr); gap: 1rem; margin: 1.75rem 0; padding: 1.5rem; border-radius: .9rem; background: var(--soft); border: 1px solid var(--line); color: var(--ink); }\n    .chat-panel p { color: var(--muted); }\n    .chat-box { border: 1px solid var(--line); border-radius: .75rem; background: var(--card); overflow: hidden; }\n    .chat-log { max-height: 360px; overflow: auto; padding: .85rem; display: grid; gap: .6rem; }\n    .msg { padding: .7rem .8rem; border-radius: .65rem; line-height: 1.5; white-space: pre-wrap; font-size: .92rem; }\n    .msg.user { margin-left: 12%; background: var(--accent-soft); border: 1px solid #bfdbfe; }\n    .msg.assistant { margin-right: 8%; background: var(--soft); border: 1px solid var(--line); }\n    .msg.error { background: #fef2f2; border: 1px solid #fecaca; }\n    .chat-form { display: grid; grid-template-columns: 1fr auto; gap: .65rem; padding: .75rem; border-top: 1px solid var(--line); }\n    .chat-form textarea { resize: vertical; min-height: 74px; padding: .7rem; border: 1px solid var(--line-strong); border-radius: .65rem; background: var(--card); color: var(--ink); font: .9rem/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }\n    .chat-form textarea:focus { outline: 2px solid var(--accent-soft); border-color: var(--accent); }\n    .chat-form button { border: 1px solid var(--ink); border-radius: .65rem; padding: 0 1rem; background: var(--ink); color: var(--bg); font-weight: 600; cursor: pointer; }\n    .chat-form button:hover { background: var(--bg); color: var(--ink); }\n    .chat-form button:disabled { opacity: .55; cursor: wait; }\n    .chat-note { margin: 0; padding: 0 .85rem .85rem; font-size: .75rem; }\n    @media (prefers-color-scheme: dark) {\n      :root {\n        --bg: #111111;\n        --ink: #f5f5f5;\n        --muted: #a3a3a3;\n        --soft: #171717;\n        --card: #111111;\n        --line: #262626;\n        --line-strong: #404040;\n        --accent: #60a5fa;\n        --accent-soft: #172554;\n        --code: #f5f5f5;\n      }\n      .msg.user { border-color: #1d4ed8; }\n      .msg.error { background: #450a0a; border-color: #7f1d1d; }\n    }\n    @media (max-width: 820px) {\n      main { padding-top: 1.25rem; }\n      .stats, .sources, .category-head, .chat-panel, .benchmark-grid { grid-template-columns: 1fr; }\n      .chat-form { grid-template-columns: 1fr; }\n      .benchmarks { justify-content: flex-start; }\n    }\n  \n    .rank-row.row-collapsed { display: none !important; }\n    .expandable[data-expanded="1"] li.rank-row.row-collapsed { display: grid !important; }\n    table .expandable[data-expanded="1"] tr.rank-row.row-collapsed { display: table-row !important; }\n    .expand-toggle {\n      margin: 0.75rem 0 0.25rem;\n      border: 1px solid var(--line);\n      background: var(--bg);\n      color: var(--ink);\n      padding: 0.45rem 0.8rem;\n      font: inherit;\n      cursor: pointer;\n      border-radius: 0.55rem;\n    }\n    .expand-toggle:hover { border-color: var(--ink); }\n    ol > .expandable { display: grid; gap: .45rem; }\n\n  </style>\n</head>\n<body>\n  <main>\n    <header>\n      <div class="eyebrow">ranks.urm8.org / refreshed '
_PAGE_AFTER_H1 = '</div>\n      <h1>Model ranks by job, benchmark family, and price.</h1>\n      <p>Each category now contains the public benchmarks that rate that type of work. Every benchmark card links to the source and shows its model ranking; category summaries below consolidate price/value using OpenRouter prices when available.</p>\n    </header>\n    <nav aria-label="Page sections">\n      <a href="#model-assistant" data-scroll-target="model-assistant">Assistant</a>\n      '
_PAGE_NOTES = '\n    <p class="note">Value is quality score divided by estimated request cost for the category token cycle. Benchmark cards show a normalized 0-100 score (from seed labels, numeric scores, or rank order) plus the original label when useful; different benchmarks are still not directly interchangeable. Benchmark rankings also drop models whose release/created date is older than one year.</p>\n    <p class="note">Model coverage: pricing/context for any model id under a tracked vendor slug (see TRACKED_VENDOR_PREFIXES) is pulled live from OpenRouter on every refresh, so newly released models appear automatically in "Newly Listed / Not Yet Ranked" above before anyone hand-curates a quality score for them.</p>\n    <section class="sources">'
_PAGE_FOOTER = '</section>\n    <p class="note">Raw data: <a href="/api/data">/api/data</a>. Force refresh: <a href="/api/data?refresh=1">/api/data?refresh=1</a>.</p>\n  </main>\n  <script>\n    const chatLog = document.getElementById(\'chat-log\');\n    const chatForm = document.getElementById(\'chat-form\');\n    const chatInput = document.getElementById(\'chat-input\');\n    const chatContext = JSON.parse(document.getElementById(\'ranks-chat-context\').textContent);\n    const chatHistory = [];\n\n    document.querySelectorAll(\'a[data-scroll-target]\').forEach((link) => {\n      link.addEventListener(\'click\', (event) => {\n        event.preventDefault();\n        const target = document.getElementById(link.dataset.scrollTarget);\n        if (!target) return;\n        target.scrollIntoView({ behavior: \'smooth\', block: \'start\' });\n        history.replaceState(null, \'\', location.pathname + location.search);\n      });\n    });\n\n    function addMessage(role, text) {\n      const node = document.createElement(\'div\');\n      node.className = `msg ${role}`;\n      node.textContent = text;\n      chatLog.appendChild(node);\n      chatLog.scrollTop = chatLog.scrollHeight;\n      return node;\n    }\n\n    function responseText(result) {\n      if (typeof result === \'string\') return result;\n      if (result?.message?.content) return result.message.content;\n      if (result?.text) return result.text;\n      return JSON.stringify(result);\n    }\n\n    chatForm.addEventListener(\'submit\', async (event) => {\n      event.preventDefault();\n      const question = chatInput.value.trim();\n      if (!question) return;\n      addMessage(\'user\', question);\n      chatHistory.push({ role: \'user\', content: question });\n      chatInput.value = \'\';\n      const button = chatForm.querySelector(\'button\');\n      button.disabled = true;\n      const pending = addMessage(\'assistant\', \'Thinking with DeepSeek...\');\n      const system = `You are the ranks.urm8.org model-selection assistant. Only help choose models by workflow and estimate spend. Use the supplied JSON as the source of truth. Explain benchmark/category tradeoffs, best-value vs top-quality options, and cost estimates. If the user gives request volume or token counts, calculate daily and monthly spend. If details are missing, ask for workflow, daily requests, input tokens, output tokens, and quality-vs-cost preference. Keep answers concise and practical. Data: ${JSON.stringify(chatContext)}`;\n      try {\n        const result = await puter.ai.chat([\n          { role: \'system\', content: system },\n          ...chatHistory.slice(-8),\n        ], {\n          model: \'deepseek-chat\',\n          temperature: 0.2,\n          max_tokens: 900,\n        });\n        const text = responseText(result);\n        pending.textContent = text;\n        chatHistory.push({ role: \'assistant\', content: text });\n      } catch (error) {\n        pending.className = \'msg error\';\n        pending.textContent = `Puter/DeepSeek error: ${error?.message || error}`;\n      } finally {\n        button.disabled = false;\n        chatInput.focus();\n      }\n    });\n  \n    document.querySelectorAll(\'[data-expand-toggle]\').forEach((button) => {\n      button.addEventListener(\'click\', () => {\n        const root = button.closest(\'.expandable\');\n        if (!root) return;\n        const expanded = root.getAttribute(\'data-expanded\') === \'1\';\n        const total = root.querySelectorAll(\'.rank-row\').length;\n        const hidden = Math.max(0, total - 5);\n        if (expanded) {\n          root.setAttribute(\'data-expanded\', \'0\');\n          button.textContent = `Show all ${total} (+${hidden} more)`;\n        } else {\n          root.setAttribute(\'data-expanded\', \'1\');\n          button.textContent = \'Show top 5\';\n        }\n      });\n    });\n\n  </script>\n</body>\n</html>'


EMPTY_DATA = {
    "generated_at": "never (parser has not run yet)",
    "sources": [],
    "models": {},
    "benchmarks": [],
    "categories": [],
    "emerging_models": [],
    "mentions": {},
    "estimation_basis": {"cycles": {}},
}

cache = {"expires_at": 0, "data": None}
cache_lock = threading.Lock()


def db_connect():
    import pg8000

    return pg8000.connect(
        user=os.environ.get("RANKS_DB_USER", "ranks"),
        password=os.environ.get("RANKS_DB_PASSWORD", ""),
        host=os.environ.get("RANKS_DB_HOST", "localhost"),
        port=int(os.environ.get("RANKS_DB_PORT", "5432")),
        database=os.environ.get("RANKS_DB_NAME", "ranks"),
    )


def fetch_snapshot():
    try:
        conn = db_connect()
    except Exception as exc:  # noqa: BLE001
        print(f"db connect failed: {exc}", flush=True)
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT data FROM ranks_snapshots ORDER BY generated_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        data = row[0]
        if isinstance(data, (bytes, bytearray)):
            data = data.decode("utf-8")
        if isinstance(data, str):
            return json.loads(data)
        return data
    except Exception as exc:  # noqa: BLE001
        print(f"snapshot query failed: {exc}", flush=True)
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
        return None


def get_data(force=False):
    now = time.time()
    with cache_lock:
        cached = cache.get("data")
        expires_at = cache.get("expires_at") or 0
        if cached is not None and not force and now < expires_at:
            return cached
    data = fetch_snapshot()
    if data is None:
        data = EMPTY_DATA
    with cache_lock:
        cache["data"] = data
        cache["expires_at"] = time.time() + CACHE_SECONDS
    return data


def money(value):
    if value is None:
        return "unknown"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if num == 0:
        return "$0"
    return f"${num:,.3f}"


def integer(value):
    if value is None:
        return "unknown"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "unknown"


def format_source_instant(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def source_cards(data):
    cards = []
    for source in data.get("sources") or []:
        ok = source.get("ok")
        state = "ok" if ok else "fail"
        status = source.get("status")
        elapsed = source.get("elapsed_ms")
        elapsed_label = f"{elapsed}ms" if elapsed is not None else "?ms"
        status_bit = f"HTTP {status}" if status is not None else "unavailable"
        err = source.get("error")
        detail = f"{status_bit} in {elapsed_label}"
        if err:
            detail = f"{detail} · {err}"
        fetched = format_source_instant(source.get("fetched_at"))
        source_date = format_source_instant(source.get("source_date"))
        when_bits = []
        if fetched:
            when_bits.append(f"fetched {fetched}")
        if source_date:
            when_bits.append(f"source date {source_date}")
        when = " · ".join(when_bits)
        if when:
            detail = f"{detail} · {when}"
        href = source.get("browse_url") or source.get("url") or "#"
        cards.append(
            "\n            <a class=\"source "
            + html.escape(state)
            + '" href="'
            + html.escape(str(href))
            + '" rel="noreferrer">\n              <b>'
            + html.escape(str(source.get("name") or "source"))
            + "</b>\n              <span>"
            + html.escape(detail)
            + "</span>\n            </a>\n            "
        )
    return "".join(cards)


def chat_context_json(data):
    categories = []
    for cat in data.get("categories") or []:
        details = []
        for b in cat.get("benchmark_details") or []:
            rankings = [
                {
                    "model": row.get("model"),
                    "score": row.get("score"),
                    "normalized_score": row.get("normalized_score"),
                    "pricing": row.get("pricing"),
                }
                for row in (b.get("rankings") or [])
            ]
            details.append(
                {
                    "name": b.get("name"),
                    "measures": b.get("measures"),
                    "url": b.get("url"),
                    "rankings": rankings,
                }
            )
        categories.append(
            {
                "id": cat.get("id"),
                "title": cat.get("title"),
                "cycle": cat.get("cycle"),
                "benchmark_details": details,
                "value_ranked": [
                    {
                        "name": r.get("name"),
                        "id": r.get("id"),
                        "quality": r.get("quality"),
                        "value": r.get("value"),
                        "cycle_cost": r.get("cycle_cost"),
                    }
                    for r in (cat.get("value_ranked") or [])
                ],
                "quality_ranked": [
                    {
                        "name": r.get("name"),
                        "id": r.get("id"),
                        "quality": r.get("quality"),
                        "cycle_cost": r.get("cycle_cost"),
                    }
                    for r in (cat.get("quality_ranked") or [])
                ],
            }
        )
    emerging = [
        {
            "name": row.get("name"),
            "vendor": row.get("vendor"),
            "input": row.get("input"),
            "output": row.get("output"),
            "context": row.get("context"),
            "discovered": row.get("discovered") or "auto-discovered from OpenRouter",
            "note": "priced but not yet quality-ranked",
        }
        for row in (data.get("emerging_models") or [])
    ]
    return json.dumps(
        {
            "generated_at": data.get("generated_at"),
            "emerging_models": emerging,
            "categories": categories,
        },
        ensure_ascii=True,
    )


def _expandable(body_html: str, total: int) -> str:
    if total <= TOP_VISIBLE:
        return body_html
    hidden = total - TOP_VISIBLE
    return (
        '<div class="expandable" data-expanded="0">'
        + body_html
        + '<button type="button" class="expand-toggle" data-expand-toggle>'
        + f"Show all {total} (+{hidden} more)"
        + "</button></div>"
    )


def model_rows(rows, mode):
    rows = list(rows or [])
    if mode == "value":
        rows = sorted(
            rows,
            key=lambda r: (
                -float(r["value"]) if isinstance(r.get("value"), (int, float)) else 0.0
            ),
        )
    else:
        rows = sorted(
            rows,
            key=lambda r: (
                -float(r["quality"])
                if isinstance(r.get("quality"), (int, float))
                else 0.0
            ),
        )
    rendered = []
    for index, row in enumerate(rows, start=1):
        score = row["value"] if mode == "value" else row["quality"]
        score_label = f"{score:,.1f}" if score is not None else "unknown"
        quality = row.get("quality")
        quality_label = f"{quality}" if quality is not None else "unknown"
        hidden = " row-collapsed" if index > TOP_VISIBLE else ""
        rendered.append(
            "\n            <tr class=\"rank-row"
            + hidden
            + '">\n              <td class="rank">#'
            + str(index)
            + "</td>\n              <td><strong>"
            + html.escape(str(row["name"]))
            + "</strong><span>"
            + html.escape(str(row["vendor"]))
            + " · "
            + html.escape(str(row["id"]))
            + "</span></td>\n              <td>"
            + quality_label
            + "</td>\n              <td>"
            + score_label
            + "</td>\n              <td>"
            + money(row.get("input"))
            + " / "
            + money(row.get("output"))
            + "</td>\n              <td>"
            + money(row.get("cycle_cost"))
            + "</td>\n              <td>"
            + integer(row.get("context"))
            + '</td>\n              <td><span>'
            + html.escape(str(row.get("price_source") or "seed"))
            + "</span>"
            + html.escape(str(row.get("note") or ""))
            + "</td>\n            </tr>\n            "
        )
    return _expandable("".join(rendered), len(rows))


def benchmark_links(category):
    bits = []
    for b in category.get("benchmarks") or []:
        bits.append(
            '<a class="bench" href="'
            + html.escape(str(b.get("url") or "#"))
            + '" rel="noreferrer">'
            + html.escape(str(b.get("name") or ""))
            + "</a>"
        )
    return " ".join(bits)


def benchmark_ranking_rows(benchmark):
    rankings = list(benchmark.get("rankings") or [])
    rankings = sorted(
        rankings,
        key=lambda r: (
            -float(r["normalized_score"])
            if isinstance(r.get("normalized_score"), (int, float))
            else 0.0,
            int(r.get("rank") or 10**9),
        ),
    )
    rows = []
    for index, row in enumerate(rankings, start=1):
        pricing = row.get("pricing") or {}
        normalized = row.get("normalized_score")
        if normalized is None:
            score_label = str(row.get("score") or "")
        else:
            raw = row.get("score")
            if raw in (None, "", "parsed") or str(raw).replace(".", "", 1).isdigit():
                score_label = f"{normalized:g}/100"
            else:
                score_label = f"{normalized:g}/100 · {raw}"
        hidden = " row-collapsed" if index > TOP_VISIBLE else ""
        rows.append(
            "\n            <li class=\"rank-row"
            + hidden
            + '">\n              <span class="rank">#'
            + str(int(row.get("rank") or index))
            + "</span>\n              <strong>"
            + html.escape(str(row.get("model") or ""))
            + "</strong>\n              <em>"
            + html.escape(score_label)
            + "</em>\n              <small>"
            + money(pricing.get("input"))
            + "/"
            + money(pricing.get("output"))
            + " per 1M · "
            + html.escape(str(row.get("note") or ""))
            + "</small>\n            </li>\n            "
        )
    return _expandable("".join(rows), len(rankings))


def benchmark_cards(category):
    cards = []
    for benchmark in category.get("benchmark_details") or []:
        status = benchmark.get("source_status") or {}
        if status.get("ok"):
            state = "ok"
        elif status.get("seed"):
            state = "seed"
        else:
            state = "fail"
        if status.get("seed"):
            status_text = "seeded"
        elif status.get("status") is not None:
            status_text = f"HTTP {status.get('status')}"
        else:
            status_text = "unavailable"
        github = benchmark.get("github")
        github_link = (
            '<a href="'
            + html.escape(str(github))
            + '" rel="noreferrer">GitHub</a>'
            if github
            else ""
        )
        cards.append(
            '\n            <article class="benchmark-card '
            + html.escape(state)
            + '">\n              <div class="benchmark-title">\n                <h4><a href="'
            + html.escape(str(benchmark.get("url") or "#"))
            + '" rel="noreferrer">'
            + html.escape(str(benchmark.get("name") or ""))
            + "</a></h4>\n                <span>"
            + html.escape(status_text)
            + "</span>\n              </div>\n              <p>"
            + html.escape(str(benchmark.get("measures") or ""))
            + "</p>\n              <ol>"
            + benchmark_ranking_rows(benchmark)
            + '</ol>\n              <div class="benchmark-links"><a href="'
            + html.escape(str(benchmark.get("url") or "#"))
            + '" rel="noreferrer">Overview</a>'
            + github_link
            + "</div>\n            </article>\n            "
        )
    return "".join(cards)


def category_sections(data):
    sections = []
    for category in data.get("categories") or []:
        cycle = category.get("cycle") or {}
        sections.append(
            '\n            <section class="category" id="'
            + html.escape(str(category.get("id") or ""))
            + '">\n              <div class="category-head">\n                <div>\n                  <p class="eyebrow">'
            + html.escape(str(category.get("id") or ""))
            + " · "
            + integer(cycle.get("input"))
            + "/"
            + integer(cycle.get("output"))
            + " token cycle</p>\n                  <h2>"
            + html.escape(str(category.get("title") or ""))
            + "</h2>\n                  <p>"
            + html.escape(str(category.get("summary") or ""))
            + '</p>\n                </div>\n                <div class="benchmarks">'
            + benchmark_links(category)
            + "</div>\n              </div>\n              <h3>Benchmarks In This Category</h3>\n              <div class=\"benchmark-grid\">"
            + benchmark_cards(category)
            + "</div>\n              <h3>Best Value Per Dollar</h3>\n              <div class=\"table-wrap\">\n                <table>\n                  <thead><tr><th></th><th>Model</th><th>Quality</th><th>Value</th><th>Input / output per 1M</th><th>Cycle cost</th><th>Context</th><th>Notes</th></tr></thead>\n                  <tbody>"
            + model_rows(category.get("value_ranked") or [], "value")
            + '</tbody>\n                </table>\n              </div>\n              <h3>Top Quality</h3>\n              <div class="table-wrap compact">\n                <table>\n                  <thead><tr><th></th><th>Model</th><th>Quality</th><th>Score</th><th>Input / output per 1M</th><th>Cycle cost</th><th>Context</th><th>Notes</th></tr></thead>\n                  <tbody>'
            + model_rows(category.get("quality_ranked") or [], "quality")
            + "</tbody>\n                </table>\n              </div>\n            </section>\n            "
        )
    return "".join(sections)


def emerging_model_rows(rows):
    rendered = []
    for row in rows or []:
        discovered = row.get("discovered") or "auto-discovered"
        badge = "priced, not yet ranked"
        sources = ", ".join(row.get("catalog_sources") or []) or (
            row.get("price_source") or "seed pricing"
        )
        release = row.get("release_date") or "—"
        rendered.append(
            "\n            <tr>\n              <td><strong>"
            + html.escape(str(row.get("name") or ""))
            + "</strong><span>"
            + html.escape(str(row.get("vendor") or ""))
            + " · "
            + html.escape(str(row.get("id") or ""))
            + "</span></td>\n              <td>"
            + money(row.get("input"))
            + " / "
            + money(row.get("output"))
            + "</td>\n              <td>"
            + integer(row.get("context"))
            + "</td>\n              <td>"
            + html.escape(str(release))
            + '</td>\n              <td><span class="badge">'
            + html.escape(badge)
            + "</span> "
            + html.escape(str(discovered))
            + " · "
            + html.escape(sources)
            + "</td>\n            </tr>\n            "
        )
    return "".join(rendered)


def emerging_models_section(data):
    rows = data.get("emerging_models") or []
    if not rows:
        return ""
    return (
        '\n    <section class="category" id="new-models">\n      <div class="category-head">\n        <div>\n          <p class="eyebrow">catalog · priced, quality pending</p>\n          <h2>Newly Listed / Not Yet Ranked</h2>\n          <p>Models discovered from live pricing catalogs that do not yet have a quality score in this dashboard.</p>\n        </div>\n      </div>\n      <div class="table-wrap">\n        <table>\n          <thead><tr><th>Model</th><th>Input / output per 1M</th><th>Context</th><th>Release</th><th>Notes</th></tr></thead>\n          <tbody>'
        + emerging_model_rows(rows)
        + "</tbody>\n        </table>\n      </div>\n    </section>\n    "
    )


def chat_panel(data):
    return (
        '\n    <section class="chat-panel" id="model-assistant">\n      <div>\n        <p class="eyebrow">DeepSeek assistant via Puter.js</p>\n        <h2>Ask which model fits your workflow.</h2>\n        <p>Ask about planning, research, RAG, writing, terminal work, code, chat, or monthly spend. The assistant uses this page\'s category and pricing data, then estimates request and monthly costs.</p>\n      </div>\n      <div class="chat-box">\n        <div id="chat-log" class="chat-log" aria-live="polite"></div>\n        <form id="chat-form" class="chat-form">\n          <textarea id="chat-input" rows="3" placeholder="Tell me your workflow, rough daily request count, and whether you care more about quality or cost."></textarea>\n          <button type="submit">Ask DeepSeek</button>\n        </form>\n        <p class="chat-note">Uses Puter.js user-pays AI. No API key is stored by this site.</p>\n      </div>\n      <script id="ranks-chat-context" type="application/json">'
        + chat_context_json(data)
        + "</script>\n    </section>\n    "
    )


def render_page(data):
    generated = html.escape(str(data.get("generated_at") or "unknown"))
    cats = data.get("categories") or []
    nav_bits = []
    for c in cats:
        cid = html.escape(str(c.get("id") or ""))
        title = html.escape(str(c.get("title") or c.get("id") or ""))
        nav_bits.append(
            f'<a href="#{cid}" data-scroll-target="{cid}">{title}</a>'
        )
    nav = "".join(nav_bits)
    if data.get("emerging_models"):
        nav += '<a href="#new-models" data-scroll-target="new-models">New Models</a>'
    sources = data.get("sources") or []
    ok = sum(1 for s in sources if s.get("ok"))
    models = data.get("models") or {}
    emerging = data.get("emerging_models") or []
    benchmarks = data.get("benchmarks") or []
    stats = (
        '\n    </nav>\n    <section class="stats">\n      <div class="stat"><b>'
        + str(len(cats))
        + "</b><span>workload categories</span></div>\n      <div class=\"stat\"><b>"
        + str(len(benchmarks))
        + "</b><span>benchmarks tracked</span></div>\n      <div class=\"stat\"><b>"
        + f"{ok}/{len(sources)}"
        + "</b><span>sources fetched</span></div>\n      <div class=\"stat\"><b>"
        + str(len(models))
        + "</b><span>priced model records</span></div>\n      <div class=\"stat\"><b>"
        + str(len(emerging))
        + "</b><span>new / not yet ranked</span></div>\n    </section>\n    "
    )
    return (
        _PAGE_HEAD
        + generated
        + _PAGE_AFTER_H1
        + nav
        + stats
        + chat_panel(data)
        + category_sections(data)
        + emerging_models_section(data)
        + _PAGE_NOTES
        + source_cards(data)
        + _PAGE_FOOTER
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[ranks-app] {self.address_string()} {fmt % args}", flush=True)

    def send_payload(self, status, content_type, payload):
        body = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        qs = parse_qs(parsed.query or "")
        if path == "/api/data":
            force = qs.get("refresh", ["0"])[0] in {"1", "true", "yes"}
            data = get_data(force=force)
            self.send_payload(200, "application/json; charset=utf-8", json.dumps(data))
            return
        if path in {"/", "/index.html"}:
            data = get_data(force=False)
            self.send_payload(200, "text/html; charset=utf-8", render_page(data))
            return
        self.send_payload(404, "text/plain; charset=utf-8", "not found")


def main():
    class Server(ThreadingHTTPServer):
        allow_reuse_address = True
        daemon_threads = True

    socket.setdefaulttimeout(5)
    server = Server(("0.0.0.0", PORT), Handler)
    print(f"serving ranks dashboard on :{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
