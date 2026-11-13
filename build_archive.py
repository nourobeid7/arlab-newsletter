"""Build the single-page archive site served from docs/ via GitHub Pages.

Renders every history/YYYY-MM-DD.json through template.html, concatenates them
into one HTML page, and emits:

  docs/index.html -- hero + date-pill tabs + inline panels for all issues

Tabs swap panels on click; URL hash deep-links (#2026-11-10).
Idempotent. Run locally or in CI after a new issue lands.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "history"
DOCS = HERE / "docs"
TEMPLATE_FILE = "template.html"


MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pretty_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{MONTHS[int(m)]} {int(d)}, {y}"


def short_date(iso: str) -> str:
    _, m, d = iso.split("-")
    return f"{MONTHS[int(m)]} {int(d)}"


INDEX_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Wissam's Newsletter</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;1,9..144,400&family=Inter:wght@300;400;500&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#08080b;
    --txt:#f7f7fa;--txt2:#b2b2bb;--txt3:#76767f;
    --glass:rgba(255,255,255,0.045);--glass-h:rgba(255,255,255,0.08);
    --edge:rgba(255,255,255,0.12);--edge-h:rgba(255,255,255,0.26);
    --disp:'Fraunces',serif;--sans:'Inter',sans-serif;
  }
  html,body{background:var(--bg);color:var(--txt);font-family:var(--sans);font-weight:300;-webkit-font-smoothing:antialiased}

  .top{position:relative;overflow:hidden;padding:0 20px}
  .top-bg{position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden}
  .glow{position:absolute;border-radius:50%;filter:blur(110px)}
  .g1{width:460px;height:460px;top:-120px;left:50%;transform:translateX(-50%);background:radial-gradient(circle,rgba(140,120,255,0.13),transparent 70%)}
  .g2{width:380px;height:380px;top:280px;left:-140px;background:radial-gradient(circle,rgba(90,170,255,0.10),transparent 70%)}
  .grain{position:absolute;inset:0;opacity:0.5;mix-blend-mode:overlay;background-image:radial-gradient(rgba(255,255,255,0.04) 0.5px,transparent 0.5px);background-size:3px 3px}

  .hero{position:relative;z-index:1;max-width:780px;margin:0 auto;min-height:280px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:70px 16px 24px}
  .pill{font-size:9px;letter-spacing:0.28em;text-transform:uppercase;color:var(--txt);background:var(--glass);border:1px solid var(--edge);border-radius:30px;padding:7px 16px;margin-bottom:22px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:inset 0 1px 0 rgba(255,255,255,0.22),0 4px 18px rgba(0,0,0,0.3)}
  .kick{font-size:9.5px;letter-spacing:0.46em;text-transform:uppercase;color:var(--txt2);margin-bottom:22px;font-weight:400}
  .mast{font-family:var(--disp);font-weight:300;font-size:58px;line-height:0.96;color:#fff;letter-spacing:-0.01em}
  .mast em{font-style:italic;font-weight:400}
  .sub{font-family:var(--disp);font-style:italic;font-size:16px;color:var(--txt2);margin-top:20px;max-width:460px;line-height:1.4}

  .tabs-wrap{position:relative;z-index:1;max-width:980px;margin:14px auto 0;padding:14px 20px 36px}
  .tabs{display:flex;flex-wrap:wrap;gap:7px;justify-content:center}
  .tab{font-family:var(--sans);font-size:10px;letter-spacing:0.22em;text-transform:uppercase;font-weight:400;color:var(--txt2);background:var(--glass);border:1px solid var(--edge);border-radius:30px;padding:8px 14px;cursor:pointer;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);transition:transform .25s,border-color .25s,background .25s,color .25s;white-space:nowrap;font-variant-numeric:tabular-nums}
  .tab:hover{border-color:var(--edge-h);color:var(--txt);transform:translateY(-1px)}
  .tab.on{background:#f7f7fa;color:#08080b;border-color:#f7f7fa;box-shadow:0 10px 30px rgba(255,255,255,0.08)}
  .tab.on:hover{transform:none}
  .tab .tab-y{opacity:0.55;margin-left:6px;font-size:9px;letter-spacing:0.2em}

  .stage{position:relative}
  .panel{display:none}
  .panel.on{display:block;animation:fade .4s ease}
  @keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

  .foot{text-align:center;font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:var(--txt3);padding:50px 20px 60px}
</style>
</head>
<body>
<div class="top">
  <div class="top-bg"><div class="glow g1"></div><div class="glow g2"></div><div class="grain"></div></div>
  <div class="hero">
    <div class="pill">For Wissam</div>
    <div class="kick">ARlab Intelligence</div>
    <div class="mast">The <em>Newsletter</em></div>
    <div class="sub">Every weekly brief — pick a date.</div>
  </div>
  <div class="tabs-wrap"><div class="tabs">__TABS__</div></div>
</div>

<div class="stage">
__PANELS__
</div>

<div class="foot">ARlab · __TOTAL__ issues</div>

<script>
(function(){
  var tabs = document.querySelectorAll('.tab');
  var panels = document.querySelectorAll('.panel');
  function show(iso, scroll){
    var found = false;
    tabs.forEach(function(t){ var on = t.dataset.iso === iso; t.classList.toggle('on', on); if(on) found = true; });
    panels.forEach(function(p){ p.classList.toggle('on', p.dataset.iso === iso); });
    if(found){
      history.replaceState(null, '', '#' + iso);
      if(scroll){
        var stage = document.querySelector('.stage');
        window.scrollTo({top: stage.offsetTop - 20, behavior: 'smooth'});
      }
    }
  }
  tabs.forEach(function(t){ t.addEventListener('click', function(){ show(t.dataset.iso, true); }); });
  var initial = location.hash.replace('#','') || (tabs[0] && tabs[0].dataset.iso);
  if(initial) show(initial, false);
  window.addEventListener('hashchange', function(){
    var iso = location.hash.replace('#','');
    if(iso) show(iso, true);
  });
})();
</script>
</body>
</html>
"""


def main() -> None:
    DOCS.mkdir(exist_ok=True)

    # Clear any stale per-issue subpages from the previous layout.
    issues_dir = DOCS / "issues"
    if issues_dir.exists():
        for p in issues_dir.glob("*.html"):
            p.unlink()
        try:
            issues_dir.rmdir()
        except OSError:
            pass

    env = Environment(
        loader=FileSystemLoader(str(HERE)),
        autoescape=select_autoescape(disabled_extensions=("html",), default=False),
    )
    template = env.get_template(TEMPLATE_FILE)

    issues: list[tuple[str, dict]] = []
    for p in sorted(HISTORY.glob("*.json")):
        try:
            payload = json.loads(p.read_text())
        except Exception as exc:
            print(f"[skip] {p.name}: {exc}")
            continue
        issues.append((p.stem, payload))

    if not issues:
        print("no history/*.json found — nothing to build")
        return

    issues_newest_first = sorted(issues, key=lambda t: t[0], reverse=True)

    tabs_html_parts: list[str] = []
    panels_html_parts: list[str] = []
    for iso, payload in issues_newest_first:
        y, m, d = iso.split("-")
        label = f'{MONTHS[int(m)]} {int(d)}<span class="tab-y">{y[2:]}</span>'
        tabs_html_parts.append(
            f'<button class="tab" type="button" data-iso="{iso}" aria-label="{pretty_date(iso)}">{label}</button>'
        )

        body = template.render(
            date=payload.get("date_display", iso),
            signals=payload.get("signals", []),
            coming_next=payload.get("coming_next", []),
            undisclosed=payload.get("undisclosed", []),
            first_of_kind=payload.get("first_of_kind", []),
            tools=payload.get("tools", []),
            partners=payload.get("partners", []),
            patterns=payload.get("patterns", []),
            action_plan=payload.get("action_plan", []),
        )
        panels_html_parts.append(f'<div class="panel" data-iso="{iso}">\n{body}\n</div>')
        print(f"[panel] {iso}")

    index = (
        INDEX_SHELL
        .replace("__TABS__", "\n".join(tabs_html_parts))
        .replace("__PANELS__", "\n".join(panels_html_parts))
        .replace("__TOTAL__", str(len(issues)))
    )
    (DOCS / "index.html").write_text(index)
    print(f"[index] docs/index.html ({len(issues)} issues · {len(index):,} bytes)")


if __name__ == "__main__":
    main()
