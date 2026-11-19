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
<title>Wissam's Newsletter</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;1,9..144,400&family=Inter:wght@300;400;500&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  :root{
    --bg:#08080b;
    --txt:#f7f7fa;--txt2:#b2b2bb;--txt3:#76767f;
    --glass:rgba(255,255,255,0.045);--glass-h:rgba(255,255,255,0.08);
    --edge:rgba(255,255,255,0.1);--edge-h:rgba(255,255,255,0.24);
    --disp:'Fraunces',serif;--sans:'Inter',sans-serif;
  }
  html,body{background:var(--bg);color:var(--txt);font-family:var(--sans);font-weight:300;-webkit-font-smoothing:antialiased}

  /* Ambient */
  .amb{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
  .glow{position:absolute;border-radius:50%;filter:blur(130px)}
  .g1{width:560px;height:560px;top:-200px;left:18%;background:radial-gradient(circle,rgba(140,120,255,0.13),transparent 70%)}
  .g2{width:460px;height:460px;top:45%;left:-170px;background:radial-gradient(circle,rgba(90,170,255,0.09),transparent 70%)}
  .g3{width:500px;height:500px;top:65%;right:-190px;background:radial-gradient(circle,rgba(255,150,210,0.08),transparent 70%)}
  .grain{position:absolute;inset:0;opacity:0.5;mix-blend-mode:overlay;background-image:radial-gradient(rgba(255,255,255,0.04) 0.5px,transparent 0.5px);background-size:3px 3px}

  /* Shell */
  .shell{position:relative;z-index:1;display:grid;grid-template-columns:150px 1fr;gap:36px;max-width:1200px;margin:0 auto;padding:44px 32px 60px;min-height:100vh}

  /* Rail */
  .rail{position:sticky;top:44px;align-self:start;max-height:calc(100vh - 88px);overflow-y:auto;padding:2px 2px 24px 0;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,0.1) transparent}
  .rail::-webkit-scrollbar{width:3px}
  .rail::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:2px}

  .brand{padding:0 2px 26px 2px}
  .brand-k{font-size:8px;letter-spacing:0.38em;text-transform:uppercase;color:var(--txt3);margin-bottom:10px;font-weight:400}
  .brand-m{font-family:var(--disp);font-weight:300;font-size:22px;line-height:1;color:#fff;letter-spacing:-0.01em}
  .brand-m em{font-style:italic;font-weight:400}

  /* Small liquid glass month pill */
  .m-cell{margin-bottom:6px}
  .m-pill{display:inline-flex;align-items:baseline;gap:5px;font-family:var(--sans);font-size:9.5px;letter-spacing:0.22em;text-transform:uppercase;font-weight:400;color:var(--txt2);background:linear-gradient(135deg,rgba(255,255,255,0.055),rgba(255,255,255,0.015));border:1px solid var(--edge);border-radius:999px;padding:6px 12px;cursor:pointer;backdrop-filter:blur(18px) saturate(150%);-webkit-backdrop-filter:blur(18px) saturate(150%);transition:transform .22s cubic-bezier(.2,.8,.2,1),border-color .22s,background .22s,color .22s,box-shadow .22s;box-shadow:inset 0 1px 0 rgba(255,255,255,0.18),0 3px 10px rgba(0,0,0,0.22);font-variant-numeric:tabular-nums;white-space:nowrap}
  .m-pill:hover{border-color:var(--edge-h);color:var(--txt);transform:translateX(2px)}
  .m-pill .m-y{opacity:0.5;font-size:8px}
  .m-pill.on{background:#f7f7fa;color:#08080b;border-color:#f7f7fa;box-shadow:0 5px 16px rgba(255,255,255,0.1),inset 0 1px 0 rgba(255,255,255,0.5)}
  .m-pill.on:hover{transform:translateX(1px)}

  /* Nested weeks */
  .weeks-grp{display:none;padding:6px 0 4px 12px}
  .weeks-grp.on{display:block;animation:slide .3s cubic-bezier(.2,.8,.2,1)}
  @keyframes slide{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
  .w-pill{display:inline-flex;align-items:center;font-family:var(--sans);font-size:8.5px;letter-spacing:0.18em;text-transform:uppercase;font-weight:400;color:var(--txt2);background:var(--glass);border:1px solid var(--edge);border-radius:999px;padding:4px 10px;cursor:pointer;backdrop-filter:blur(14px) saturate(150%);-webkit-backdrop-filter:blur(14px) saturate(150%);transition:transform .2s,border-color .2s,background .2s,color .2s;margin:3px 0;font-variant-numeric:tabular-nums;box-shadow:inset 0 1px 0 rgba(255,255,255,0.12)}
  .w-pill:hover{border-color:var(--edge-h);color:var(--txt);transform:translateX(2px)}
  .w-pill.on{background:#f7f7fa;color:#08080b;border-color:#f7f7fa;box-shadow:0 4px 12px rgba(255,255,255,0.08)}
  .w-row{display:block}

  /* Stage */
  .stage{position:relative;min-width:0}
  .panel{display:none}
  .panel.on{display:block;animation:fade .4s ease}
  @keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

  /* Mobile: rail collapses on top */
  @media (max-width:820px){
    .shell{grid-template-columns:1fr;padding:24px 16px 36px;gap:18px}
    .rail{position:static;max-height:none;padding:0}
    .brand{padding:0 2px 18px}
    .m-cell{display:inline-block;margin:0 5px 5px 0}
    .weeks-grp{padding:6px 0 4px 0}
    .w-row{display:inline-block;margin-right:4px}
  }
</style>
</head>
<body>
<div class="amb"><div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div><div class="grain"></div></div>

<div class="shell">
  <aside class="rail">
    <div class="brand">
      <div class="brand-k">ARlab</div>
      <div class="brand-m">The <em>Newsletter</em></div>
    </div>
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
      // Toggle: if already open, close it and leave current panel alone.
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

    # Each month is a cell: month pill + hidden weeks group beneath it.
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

    # Panels (one per issue).
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
