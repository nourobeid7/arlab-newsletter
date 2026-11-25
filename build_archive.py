"""Build the single-page archive site served from docs/ via GitHub Pages.

Layout: sticky left rail of small liquid-glass month pills. Tapping a month
reveals its week pills nested right beneath it in the same rail. The selected
issue panel fills the right side.

URL hash deep-links to a date (#2026-11-10) and expands its month.
Idempotent. Run locally or in CI after a new issue lands.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "history"
DOCS = HERE / "docs"
TEMPLATE_FILE = "template.html"


MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

MONTHS_LONG = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def pretty_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{MONTHS[int(m)]} {int(d)}, {y}"


INDEX_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>ARlab Newsletter</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#070709;
    --text:#f0f0f0;--text2:#999;--text3:#666;
    --glass-blur:saturate(210%) blur(40px);
    --border:rgba(255,255,255,0.14);--border2:rgba(255,255,255,0.22);
    --accent-ar:#b8aef5;--accent-creator:#f0805a;--accent-ai:#5adab0;
  }
  html{background:#070709}
  body{color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh;-webkit-font-smoothing:antialiased;
    background:
      radial-gradient(900px 600px at 12% -10%, rgba(184,174,245,0.18), transparent 60%),
      radial-gradient(800px 600px at 95% 10%, rgba(90,218,176,0.14), transparent 55%),
      radial-gradient(900px 700px at 60% 110%, rgba(240,128,90,0.10), transparent 60%),
      #070709 !important;
    background-attachment:fixed !important;
  }

  /* Header — matches Intelligence + Marketing dashboards */
  .header{padding:22px 40px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:16px;background:rgba(10,10,10,0.4);backdrop-filter:var(--glass-blur);-webkit-backdrop-filter:var(--glass-blur);position:sticky;top:0;z-index:100}
  .header h1{font-family:'Space Grotesk',sans-serif;font-size:20px;font-weight:700;letter-spacing:-.5px;color:var(--text)}
  .header-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:flex-end}
  .arlab-badge{font-family:'Space Grotesk',sans-serif;font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--text3);border:1px solid var(--border);padding:5px 11px;border-radius:20px;background:transparent}
  .dash-link{font-family:'Space Grotesk',sans-serif;font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--text2);border:1px solid var(--border);padding:5px 11px;border-radius:20px;text-decoration:none;transition:border-color .15s,color .15s}
  .dash-link:hover{border-color:var(--border2);color:var(--text)}
  .nl-pill{font-family:'Space Grotesk',sans-serif;font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;padding:5px 12px;border-radius:20px;background:linear-gradient(135deg,rgba(184,174,245,0.22) 0%,rgba(90,218,176,0.16) 55%,rgba(240,128,90,0.20) 100%);color:#f0f0f0;border:1px solid rgba(255,255,255,0.22);box-shadow:inset 0 1px 0 rgba(255,255,255,0.16),inset 0 -1px 0 rgba(255,255,255,0.04),0 4px 14px rgba(0,0,0,0.25);backdrop-filter:var(--glass-blur);-webkit-backdrop-filter:var(--glass-blur);white-space:nowrap}

  /* Shell */
  .shell{position:relative;z-index:1;display:grid;grid-template-columns:168px 1fr;gap:32px;max-width:1300px;margin:0 auto;padding:28px 40px 60px;min-height:calc(100vh - 62px)}

  /* Rail */
  .rail{position:sticky;top:82px;align-self:start;max-height:calc(100vh - 110px);overflow-y:auto;padding:2px 2px 24px 0;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,0.1) transparent}
  .rail::-webkit-scrollbar{width:3px}
  .rail::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:2px}

  .rail-kick{font-family:'Space Grotesk',sans-serif;font-size:9px;font-weight:700;letter-spacing:.22em;text-transform:uppercase;color:var(--text3);margin-bottom:14px;padding:6px 11px;border:1px solid var(--border);border-radius:999px;display:inline-block;background:linear-gradient(145deg,rgba(255,255,255,0.055),rgba(255,255,255,0.015));backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:inset 0 1px 0 rgba(255,255,255,0.14)}

  /* Month pill — liquid glass, matches dashboard section-title aesthetic */
  .m-cell{margin-bottom:8px}
  .m-pill{display:inline-flex;align-items:baseline;gap:5px;font-family:'Space Grotesk',sans-serif;font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:var(--text2);background:linear-gradient(145deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02));border:1px solid var(--border);border-radius:999px;padding:7px 13px;cursor:pointer;backdrop-filter:blur(20px) saturate(150%);-webkit-backdrop-filter:blur(20px) saturate(150%);transition:transform .22s cubic-bezier(.2,.8,.2,1),border-color .22s,background .22s,color .22s,box-shadow .22s;box-shadow:inset 0 1px 0 rgba(255,255,255,0.18),0 3px 10px rgba(0,0,0,0.22);font-variant-numeric:tabular-nums;white-space:nowrap}
  .m-pill:hover{border-color:var(--border2);color:var(--text);transform:translateX(2px)}
  .m-pill .m-y{opacity:0.55;font-size:9px;font-weight:500}
  .m-pill.on{background:linear-gradient(135deg,rgba(184,174,245,0.28) 0%,rgba(90,218,176,0.18) 55%,rgba(240,128,90,0.22) 100%);color:#fff;border-color:rgba(255,255,255,0.35);box-shadow:inset 0 1px 0 rgba(255,255,255,0.3),0 6px 18px rgba(184,174,245,0.18)}
  .m-pill.on:hover{transform:translateX(1px)}

  /* Nested weeks */
  .weeks-grp{display:none;padding:8px 0 4px 10px}
  .weeks-grp.on{display:block;animation:slide .3s cubic-bezier(.2,.8,.2,1)}
  @keyframes slide{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
  .w-pill{display:inline-flex;align-items:center;font-family:'Space Grotesk',sans-serif;font-size:9px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:var(--text2);background:rgba(255,255,255,0.04);border:1px solid var(--border);border-radius:999px;padding:5px 11px;cursor:pointer;backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);transition:transform .2s,border-color .2s,background .2s,color .2s;margin:3px 0;font-variant-numeric:tabular-nums;box-shadow:inset 0 1px 0 rgba(255,255,255,0.12)}
  .w-pill:hover{border-color:var(--border2);color:var(--text);transform:translateX(2px)}
  .w-pill.on{background:#f0f0f0;color:#0a0a0a;border-color:#f0f0f0;box-shadow:0 4px 12px rgba(255,255,255,0.08)}
  .w-row{display:block}

  /* Stage */
  .stage{position:relative;min-width:0}
  .panel{display:none}
  .panel.on{display:block;animation:fade .4s ease}
  @keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

  /* Mobile */
  @media (max-width:820px){
    .header{padding:16px 20px 14px;flex-wrap:wrap;gap:10px}
    .header h1{font-size:17px}
    .shell{grid-template-columns:1fr;padding:20px 16px 36px;gap:18px}
    .rail{position:static;max-height:none;padding:0;top:auto}
    .rail-kick{margin-bottom:10px}
    .m-cell{display:inline-block;margin:0 5px 5px 0}
    .weeks-grp{padding:6px 0 4px 0}
    .w-row{display:inline-block;margin-right:4px}
  }
</style>
</head>
<body>
<header class="header">
  <h1>The Newsletter</h1>
  <div class="header-right">
    <a class="dash-link" href="https://nourobeid7.github.io/arlab-bundle-builder/" target="_blank" rel="noopener">&#8629; Intelligence Dashboard</a>
    <span class="arlab-badge">ARlab</span>
    <span class="nl-pill">Weekly Intelligence</span>
  </div>
</header>

<div class="shell">
  <aside class="rail">
    <div class="rail-kick">Archive</div>
__MONTH_CELLS__
  </aside>

  <main class="stage">
__PANELS__
  </main>
</div>

<script>
(function(){
  var monthPills = document.querySelectorAll('.m-pill');
  var weekGroups = document.querySelectorAll('.weeks-grp');
  var weekPills = document.querySelectorAll('.w-pill');
  var panels = document.querySelectorAll('.panel');

  function showMonth(ym){
    monthPills.forEach(function(p){ p.classList.toggle('on', p.dataset.ym === ym); });
    weekGroups.forEach(function(g){ g.classList.toggle('on', g.dataset.ym === ym); });
  }

  function showWeek(iso, scrollStage){
    var ym = iso.slice(0, 7);
    showMonth(ym);
    var foundW = false;
    weekPills.forEach(function(w){ var on = w.dataset.iso === iso; w.classList.toggle('on', on); if(on) foundW = true; });
    panels.forEach(function(p){ p.classList.toggle('on', p.dataset.iso === iso); });
    if(foundW){
      history.replaceState(null, '', '#' + iso);
      if(scrollStage && window.innerWidth <= 820){
        var stage = document.querySelector('.stage');
        window.scrollTo({top: stage.offsetTop - 12, behavior: 'smooth'});
      }
    }
  }

  monthPills.forEach(function(p){
    p.addEventListener('click', function(){
      var ym = p.dataset.ym;
      if(p.classList.contains('on')){
        p.classList.remove('on');
        weekGroups.forEach(function(g){ if(g.dataset.ym === ym) g.classList.remove('on'); });
        return;
      }
      var firstIso = p.dataset.firstIso;
      showMonth(ym);
      if(firstIso) showWeek(firstIso, false);
    });
  });
  weekPills.forEach(function(w){
    w.addEventListener('click', function(){ showWeek(w.dataset.iso, true); });
  });

  var hash = location.hash.replace('#','');
  var initial = (hash && document.querySelector('.w-pill[data-iso="'+hash+'"]')) ? hash
              : (weekPills[0] && weekPills[0].dataset.iso);
  if(initial) showWeek(initial, false);

  window.addEventListener('hashchange', function(){
    var iso = location.hash.replace('#','');
    if(iso) showWeek(iso, true);
  });
})();
</script>
</body>
</html>
"""


def main() -> None:
    DOCS.mkdir(exist_ok=True)

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

    by_month: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for iso, payload in issues_newest_first:
        by_month[iso[:7]].append((iso, payload))

    months_sorted = sorted(by_month.keys(), reverse=True)

    month_cell_parts: list[str] = []
    for ym in months_sorted:
        y, m = ym.split("-")
        label_short = MONTHS[int(m)]
        label_long = MONTHS_LONG[int(m)]
        first_iso = by_month[ym][0][0]
        weeks = []
        for iso, _ in by_month[ym]:
            _, mm, d = iso.split("-")
            label = f'{MONTHS[int(mm)]} {int(d)}'
            weeks.append(
                f'      <div class="w-row"><button class="w-pill" type="button" data-iso="{iso}" aria-label="{pretty_date(iso)}">{label}</button></div>'
            )
        month_cell_parts.append(
            f'    <div class="m-cell">\n'
            f'      <button class="m-pill" type="button" data-ym="{ym}" data-first-iso="{first_iso}" '
            f'aria-label="{label_long} 20{y[2:]}">{label_short}<span class="m-y">&rsquo;{y[2:]}</span></button>\n'
            f'      <div class="weeks-grp" data-ym="{ym}">\n' + "\n".join(weeks) + "\n      </div>\n"
            f'    </div>'
        )

    panels_html_parts: list[str] = []
    for iso, payload in issues_newest_first:
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
        panels_html_parts.append(f'    <div class="panel" data-iso="{iso}">\n{body}\n    </div>')
        print(f"[panel] {iso}")

    index = (
        INDEX_SHELL
        .replace("__MONTH_CELLS__", "\n".join(month_cell_parts))
        .replace("__PANELS__", "\n".join(panels_html_parts))
    )
    (DOCS / "index.html").write_text(index)
    print(f"[index] docs/index.html ({len(issues_newest_first)} issues, {len(months_sorted)} months, {len(index):,} bytes)")


if __name__ == "__main__":
    main()
