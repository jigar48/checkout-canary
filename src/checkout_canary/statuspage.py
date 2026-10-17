"""Render the static HTML status page from the run history. No external assets or scripts."""

import html
import shutil
from datetime import UTC, datetime
from pathlib import Path

from checkout_canary import __version__
from checkout_canary.history import SCREENSHOT_DIR, SHOW_RUNS, History, HistoryEntry

REPO_URL = "https://github.com/jigar48/checkout-canary"

_CSS = """
:root{--bg:#f6f7f9;--fg:#1b1f24;--muted:#5b6670;--card:#fff;--line:#d9dee3;
--ok:#1a7f37;--okbg:#dcf5e3;--bad:#b42318;--badbg:#fde4e1;--none:#6b7280;--nonebg:#e8eaed}
@media (prefers-color-scheme:dark){:root{--bg:#12161a;--fg:#e8eaed;--muted:#9aa5b1;--card:#1b2127;
--line:#2f3841;--ok:#56d364;--okbg:#14301c;--bad:#ff8a80;--badbg:#3a1714;--none:#9aa5b1;--nonebg:#262d34}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:760px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.4rem;margin:0 0 4px}
.note{color:var(--muted);margin:0 0 20px}
.banner{border-radius:12px;padding:20px;margin:16px 0;border:2px solid}
.banner h2{margin:0 0 4px;font-size:1.6rem}
.banner p{margin:0}
.banner.ok{background:var(--okbg);border-color:var(--ok);color:var(--ok)}
.banner.bad{background:var(--badbg);border-color:var(--bad);color:var(--bad)}
.banner.none{background:var(--nonebg);border-color:var(--none);color:var(--none)}
.banner p,.banner h2{color:var(--fg)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:16px 0}
.card h3{margin:0 0 8px;font-size:1.05rem}
.strip{display:flex;flex-wrap:wrap;gap:4px;list-style:none;padding:0;margin:8px 0}
.strip li{width:18px;height:28px;border-radius:4px}
.strip li.ok{background:var(--ok)}.strip li.bad{background:var(--bad)}
.strip li span{position:absolute;left:-9999px}
.muted{color:var(--muted)}
.warn{display:none;background:var(--badbg);border:1px solid var(--bad);border-radius:8px;padding:10px;margin:12px 0}
table{width:100%;border-collapse:collapse;font-size:.95rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.tag{display:inline-block;border-radius:6px;padding:0 8px;font-weight:600;font-size:.85rem}
.tag.ok{background:var(--okbg);color:var(--ok)}.tag.bad{background:var(--badbg);color:var(--bad)}
img.shot{max-width:100%;border:1px solid var(--line);border-radius:8px}
a{color:inherit}
footer{color:var(--muted);font-size:.85rem;margin-top:28px}
"""

_JS = """
(function(){
  var t=document.getElementById('last-check');
  if(!t){return;}
  var mins=Math.round((Date.now()-new Date(t.getAttribute('datetime')).getTime())/60000);
  var ago=t.parentNode.querySelector('.ago');
  if(ago&&mins>=0){ago.textContent=' ('+(mins<2?'just now':mins<120?mins+' minutes ago':Math.round(mins/60)+' hours ago')+')';}
  if(mins>180){var w=document.getElementById('stale');if(w){w.style.display='block';}}
})();
"""


def _fmt(started_at: str) -> str:
    moment = datetime.fromisoformat(started_at).astimezone(UTC)
    return moment.strftime("%d %b %Y, %H:%M UTC")


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _safe_link(url: str | None) -> str | None:
    return url if url and url.startswith(("https://", "http://")) else None


def _banner(latest: HistoryEntry | None) -> str:
    if latest is None:
        return (
            '<section class="banner none"><h2>No checks yet</h2>'
            "<p>The first check has not run. This page updates after every check.</p></section>"
        )
    if latest.passed:
        return (
            '<section class="banner ok"><h2>All good: checkout is working</h2>'
            "<p>The last check walked through the shop up to the payment step and everything worked."
            "</p></section>"
        )
    return (
        '<section class="banner bad"><h2>Problem: checkout is NOT working</h2>'
        "<p>The last check could not complete the journey. Details and a screenshot are below."
        "</p></section>"
    )


def _failure_card(latest: HistoryEntry | None) -> str:
    if latest is None or latest.passed:
        return ""
    parts = ['<section class="card"><h3>What went wrong</h3>']
    parts.append(f"<p>{_esc(latest.detail or 'The journey failed.')}</p>")
    if latest.screenshot:
        src = f"{SCREENSHOT_DIR}/{_esc(latest.screenshot)}"
        parts.append(
            f'<p><img class="shot" src="{src}" alt="Screenshot of the page at the moment of failure">'
            "</p>"
        )
    link = _safe_link(latest.run_url)
    if link:
        parts.append(f'<p><a href="{_esc(link)}">Open the run with full evidence</a></p>')
    parts.append("</section>")
    return "".join(parts)


def _strip(shown: list[HistoryEntry]) -> str:
    if not shown:
        return ""
    items = []
    for entry in shown:
        label = "passed" if entry.passed else "FAILED"
        cls = "ok" if entry.passed else "bad"
        items.append(
            f'<li class="{cls}" title="{_esc(_fmt(entry.started_at))}: {label}" '
            f'style="position:relative"><span>{_esc(_fmt(entry.started_at))}: {label}</span></li>'
        )
    return f'<ul class="strip" aria-label="Last {len(shown)} checks, oldest first">{"".join(items)}</ul>'


def _rows(shown: list[HistoryEntry]) -> str:
    rows = []
    for entry in reversed(shown):
        tag = (
            '<span class="tag ok">OK</span>'
            if entry.passed
            else '<span class="tag bad">FAILED</span>'
        )
        detail = "" if entry.passed else _esc(entry.detail or "")
        link = _safe_link(entry.run_url)
        if link:
            detail += f' <a href="{_esc(link)}">run</a>'
        seconds = entry.duration_ms / 1000
        rows.append(
            f"<tr><td>{_esc(_fmt(entry.started_at))}</td><td>{tag}</td>"
            f"<td>{seconds:.1f} s</td><td>{detail}</td></tr>"
        )
    return "".join(rows)


def render_status_page(
    history: History,
    title: str,
    note: str = "",
    generated_at: datetime | None = None,
) -> str:
    generated = (generated_at or datetime.now(UTC)).astimezone(UTC)
    shown = history.runs[-SHOW_RUNS:]
    latest = shown[-1] if shown else None
    passed = sum(1 for entry in shown if entry.passed)

    if latest:
        last_line = (
            f'<p>Last check: <time id="last-check" datetime="{_esc(latest.started_at)}">'
            f'{_esc(_fmt(latest.started_at))}</time><span class="ago"></span></p>'
            f'<p class="muted">Passed {passed} of the last {len(shown)} checks.</p>'
        )
        history_card = (
            f'<section class="card"><h3>Last {len(shown)} checks</h3>{_strip(shown)}'
            "<table><thead><tr><th>When</th><th>Result</th><th>Took</th><th>Details</th></tr>"
            f"</thead><tbody>{_rows(shown)}</tbody></table></section>"
        )
    else:
        last_line = ""
        history_card = ""

    note_html = f'<p class="note">{_esc(note)}</p>' if note else ""
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex">'
        f"<title>{_esc(title)}</title><style>{_CSS}</style></head><body><main>"
        f"<h1>{_esc(title)}</h1>{note_html}"
        f"{_banner(latest)}"
        '<div id="stale" class="warn">No check has run for over 3 hours. The monitor may have '
        "stopped (GitHub can pause scheduled workflows in inactive repositories).</div>"
        f"{last_line}{_failure_card(latest)}{history_card}"
        f"<footer>Generated {_esc(generated.strftime('%d %b %Y, %H:%M UTC'))} by "
        f'<a href="{REPO_URL}">checkout-canary</a> {__version__}. '
        "Checks stop before payment and never place orders.</footer>"
        f"</main><script>{_JS}</script></body></html>\n"
    )


def write_site(history: History, data_dir: Path, site_dir: Path, title: str, note: str) -> Path:
    """Write index.html and the screenshots the page refers to into site_dir."""
    site_dir.mkdir(parents=True, exist_ok=True)
    shown = history.runs[-SHOW_RUNS:]
    wanted = [entry.screenshot for entry in shown if entry.screenshot]
    if wanted:
        (site_dir / SCREENSHOT_DIR).mkdir(parents=True, exist_ok=True)
    for name in wanted:
        source = data_dir / SCREENSHOT_DIR / name
        if source.is_file():
            shutil.copyfile(source, site_dir / SCREENSHOT_DIR / name)
    index = site_dir / "index.html"
    index.write_text(render_status_page(history, title, note), encoding="utf-8")
    return index
