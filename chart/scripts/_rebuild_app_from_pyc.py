#!/usr/bin/env python3
"""Rebuild app.py from app.cpython-312.pyc HTML chunks + expand-top-5 UI."""

from __future__ import annotations

import marshal
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYC = ROOT / "__pycache__" / "app.cpython-312.pyc"
OUT = ROOT / "app.py"
TOP_VISIBLE = 5

LOGIC = r'''
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
TOP_VISIBLE = __TOP_VISIBLE__

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
'''


def find(c: types.CodeType, name: str) -> types.CodeType | None:
    if c.co_name == name:
        return c
    for x in c.co_consts:
        if isinstance(x, types.CodeType):
            got = find(x, name)
            if got:
                return got
    return None


def main() -> None:
    code = marshal.loads(PYC.read_bytes()[16:])
    rp = find(code, "render_page")
    assert rp is not None
    consts = {i: x for i, x in enumerate(rp.co_consts) if isinstance(x, str)}
    head = consts[3]
    after_h1 = consts[5]
    notes = consts[22]
    footer = consts[23]

    expand_css = """
    .rank-row.row-collapsed { display: none !important; }
    .expandable[data-expanded="1"] li.rank-row.row-collapsed { display: grid !important; }
    table .expandable[data-expanded="1"] tr.rank-row.row-collapsed { display: table-row !important; }
    .expand-toggle {
      margin: 0.75rem 0 0.25rem;
      border: 1px solid var(--line);
      background: var(--bg);
      color: var(--ink);
      padding: 0.45rem 0.8rem;
      font: inherit;
      cursor: pointer;
      border-radius: 0.55rem;
    }
    .expand-toggle:hover { border-color: var(--ink); }
    ol > .expandable { display: grid; gap: .45rem; }
"""
    head = head.replace("</style>", expand_css + "\n  </style>", 1)
    expand_js = """
    document.querySelectorAll('[data-expand-toggle]').forEach((button) => {
      button.addEventListener('click', () => {
        const root = button.closest('.expandable');
        if (!root) return;
        const expanded = root.getAttribute('data-expanded') === '1';
        const total = root.querySelectorAll('.rank-row').length;
        const hidden = Math.max(0, total - 5);
        if (expanded) {
          root.setAttribute('data-expanded', '0');
          button.textContent = `Show all ${total} (+${hidden} more)`;
        } else {
          root.setAttribute('data-expanded', '1');
          button.textContent = 'Show top 5';
        }
      });
    });
"""
    footer = footer.replace("</script>", expand_js + "\n  </script>", 1)

    doc = '''"""HTTP server for ranks.urm8.org.

Serves the latest pre-computed snapshot written by parser.py (a separate
CronJob) from Postgres. This process never scrapes sources itself; see
parser.py for the parsing step.
"""
'''
    body = LOGIC.replace("__TOP_VISIBLE__", str(TOP_VISIBLE))
    # Insert PAGE constants after imports block start — actually prepend constants after docstring in LOGIC
    # LOGIC already starts with from __future__; inject constants after TOP_VISIBLE line area via prepend
    constants = (
        "_PAGE_HEAD = "
        + repr(head)
        + "\n_PAGE_AFTER_H1 = "
        + repr(after_h1)
        + "\n_PAGE_NOTES = "
        + repr(notes)
        + "\n_PAGE_FOOTER = "
        + repr(footer)
        + "\n\n"
    )
    # Place constants after TOP_VISIBLE assignment
    marker = f"TOP_VISIBLE = {TOP_VISIBLE}\n"
    if marker not in body:
        raise SystemExit("TOP_VISIBLE marker missing")
    body = body.replace(marker, marker + "\n" + constants, 1)
    OUT.write_text(doc + body)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
