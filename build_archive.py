"""Build the static archive site served from docs/ via GitHub Pages.

Reads every history/YYYY-MM-DD.json, renders each issue through template.html,
and emits:
  docs/index.html                   -- Wissam-shaped archive landing page
  docs/issues/YYYY-MM-DD.html       -- one standalone page per issue

Idempotent. Run locally or in CI after a new issue lands.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html import unescape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
HISTORY = HERE / "history"
DOCS = HERE / "docs"
ISSUES = DOCS / "issues"
TEMPLATE_FILE = "template.html"


ISSUE_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>__TITLE__ — Wissam's Newsletter</title>
<style>
  html,body{margin:0;padding:0;background:#08080b}
  .topnav{position:fixed;top:14px;left:14px;z-index:50;font-family:'Inter',sans-serif;font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:#f7f7fa;background:rgba(255,255,255,0.045);border:1px solid rgba(255,255,255,0.12);border-radius:30px;padding:8px 14px;text-decoration:none;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);transition:border-color .3s,background .3s}
  .topnav:hover{border-color:rgba(255,255,255,0.26);background:rgba(255,255,255,0.08)}
</style>
</head>
<body>
<a class="topnav" href="../index.html">← Index</a>
__BODY__
</body>
</html>
"""


INDEX_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Wissam's Newsletter — Archive</title>
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
  .wrap{max-width:780px;margin:0 auto;padding:0 24px 80px;position:relative;overflow:hidden}
  .bgwrap{position:absolute;inset:0;z-index:0;pointer-events:none;overflow:hidden}
  .glow{position:absolute;border-radius:50%;filter:blur(110px)}
  .g1{width:460px;height:460px;top:-120px;left:50%;transform:translateX(-50%);background:radial-gradient(circle,rgba(140,120,255,0.13),transparent 70%)}
  .g2{width:380px;height:380px;top:820px;left:-140px;background:radial-gradient(circle,rgba(90,170,255,0.10),transparent 70%)}
  .g3{width:420px;height:420px;top:1700px;right:-160px;background:radial-gradient(circle,rgba(255,150,210,0.08),transparent 70%)}
  .grain{position:absolute;inset:0;opacity:0.5;mix-blend-mode:overlay;background-image:radial-gradient(rgba(255,255,255,0.04) 0.5px,transparent 0.5px);background-size:3px 3px}
  .layer{position:relative;z-index:1}

  .hero{min-height:380px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:60px 16px 20px}
  .pill{font-size:9px;letter-spacing:0.28em;text-transform:uppercase;color:var(--txt);background:var(--glass);border:1px solid var(--edge);border-radius:30px;padding:7px 16px;margin-bottom:22px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:inset 0 1px 0 rgba(255,255,255,0.22),0 4px 18px rgba(0,0,0,0.3)}
  .kick{font-size:9.5px;letter-spacing:0.46em;text-transform:uppercase;color:var(--txt2);margin-bottom:22px;font-weight:400}
  .mast{font-family:var(--disp);font-weight:300;font-size:60px;line-height:0.96;color:#fff;letter-spacing:-0.01em}
  .mast em{font-style:italic;font-weight:400}
  .sub{font-family:var(--disp);font-style:italic;font-size:17px;color:var(--txt2);margin-top:22px;max-width:460px;line-height:1.4}
  .seal{margin-top:26px;display:flex;align-items:center;gap:16px}
  .seal-l,.seal-r{width:48px;height:1px;background:var(--edge)}
  .seal-t{font-size:9px;letter-spacing:0.3em;color:var(--txt2);text-transform:uppercase}

  .sec{margin:60px 0 18px}
  .sec-rule{display:flex;align-items:baseline;gap:12px}
  .sec-no{font-family:var(--disp);font-style:italic;font-size:16px;color:var(--txt2)}
  .sec-t{font-family:var(--disp);font-weight:300;font-size:25px;color:var(--txt)}
  .sec-t em{font-style:italic}
  .sec-l{flex:1;height:1px;background:var(--edge)}
  .sec-k{font-size:8.5px;letter-spacing:0.28em;text-transform:uppercase;color:var(--txt3);margin-top:8px;margin-left:28px;font-weight:400}

  a.card{display:block;text-decoration:none;color:inherit;margin-bottom:12px}
  .glass{position:relative;background:linear-gradient(135deg,rgba(255,255,255,0.07),rgba(255,255,255,0.02));backdrop-filter:blur(22px) saturate(150%);-webkit-backdrop-filter:blur(22px) saturate(150%);border:1px solid var(--edge);border-radius:24px;padding:22px 24px;box-shadow:inset 0 1px 0 rgba(255,255,255,0.25),inset 0 -1px 0 rgba(255,255,255,0.05),0 14px 40px rgba(0,0,0,0.4);transition:transform .4s cubic-bezier(.2,.8,.2,1),box-shadow .4s,border-color .4s}
  a.card:hover .glass{transform:translateY(-3px);border-color:var(--edge-h);box-shadow:inset 0 1px 0 rgba(255,255,255,0.35),0 20px 50px rgba(0,0,0,0.5)}

  .card-top{display:flex;align-items:baseline;justify-content:space-between;gap:16px;margin-bottom:10px}
  .card-date{font-family:var(--disp);font-weight:400;font-size:22px;color:var(--txt);letter-spacing:0.02em}
  .card-tag{font-size:8px;letter-spacing:0.22em;text-transform:uppercase;color:var(--txt3);white-space:nowrap;border:1px solid var(--edge);border-radius:30px;padding:4px 10px}
  .card-teaser{font-family:var(--disp);font-style:italic;font-weight:300;font-size:16.5px;line-height:1.35;color:var(--txt2)}
  .card-arrow{font-size:9px;letter-spacing:0.22em;text-transform:uppercase;color:var(--txt);margin-top:14px}

  .pills{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
  .pill-s{font-family:var(--sans);font-size:9px;letter-spacing:0.18em;text-transform:uppercase;color:var(--txt2);background:var(--glass);border:1px solid var(--edge);border-radius:30px;padding:5px 11px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);white-space:nowrap}

  .featured .glass{padding:32px 28px}
  .featured .card-date{font-size:30px}
  .featured .card-teaser{font-size:20px;color:var(--txt);line-height:1.3}
  .featured .card-tag{color:var(--txt);background:var(--glass)}
  .featured .pill-s{color:var(--txt);font-size:10px;padding:6px 13px}

  .foot{margin-top:70px;padding-top:28px;border-top:1px solid var(--edge);text-align:center;font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:var(--txt3)}
</style>
</head>
<body>
<div class="wrap">
  <div class="bgwrap">
    <div class="glow g1"></div><div class="glow g2"></div><div class="glow g3"></div>
    <div class="grain"></div>
  </div>
  <div class="layer">

    <div class="hero">
      <div class="pill">Index</div>
      <div class="kick">ARlab Intelligence</div>
      <div class="mast">Wissam's<br><em>Newsletter</em></div>
      <div class="sub">Every weekly brief, in one quiet room.</div>
      <div class="seal"><span class="seal-l"></span><span class="seal-t">__TOTAL__ issues · updated __UPDATED__</span><span class="seal-r"></span></div>
    </div>

    <div style="margin:50px 0 0">
    __FEATURED__
    __CARDS__
    </div>

    <div class="foot">ARlab · for Wissam</div>
  </div>
</div>
</body>
</html>
"""


MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pretty_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{MONTHS[int(m)]} {int(d)}, {y}"


def pick_teaser(payload: dict) -> str:
    sigs = payload.get("signals") or []
    if sigs and isinstance(sigs[0], dict):
        return sigs[0].get("headline") or ""
    return ""


_BRAND_RE = re.compile(r"<b>(.*?)</b>", re.I | re.S)
_WS_RE = re.compile(r"\s+")


def pick_pills(payload: dict, max_pills: int = 4) -> list[str]:
    """Extract 3-4 distinct brand/product names from the week's signals to scan by."""
    text_blobs: list[str] = []
    for sig in payload.get("signals") or []:
        if isinstance(sig, dict):
            text_blobs.append(sig.get("headline") or "")
            text_blobs.append(sig.get("body") or "")
    text = " ".join(text_blobs)

    months = {"january","february","march","april","may","june","july",
              "august","september","october","november","december"}
    out: list[str] = []
    seen: set[str] = set()
    for raw in _BRAND_RE.findall(text):
        s = _WS_RE.sub(" ", unescape(raw)).strip().rstrip(".,;:")
        if not s or not re.match(r"[A-Za-z]", s):
            continue  # skip bare numbers like "$3.4B" or "1.7GW"
        if len(s) > 28 or len(s.split()) > 4:
            continue  # skip long phrases and compound descriptions
        if "," in s or "/" in s or re.search(r"\d{4}", s):
            continue  # skip comma lists, "A/B" lumps, or dates with years
        low = s.lower()
        if low in seen:
            continue
        # must look like a proper name: first word capitalized or all-caps acronym,
        # and not just a common word (e.g. "two paired Mac Studios")
        first = s.split()[0]
        if not (first[0].isupper() and (first.isupper() or first[1:].islower() or len(first) <= 3)):
            continue
        if low.split()[0] in months:
            continue
        seen.add(low)
        out.append(s)
        if len(out) >= max_pills:
            break
    return out


def render_card(iso: str, payload: dict, featured: bool = False) -> str:
    tag = "Latest" if featured else "Issue"
    wrap_class = "card featured" if featured else "card"
    teaser = pick_teaser(payload)
    pills = pick_pills(payload, max_pills=5 if featured else 3)
    pills_html = (
        '<div class="pills">' + "".join(f'<span class="pill-s">{p}</span>' for p in pills) + "</div>"
        if pills else ""
    )
    arrow = "" if featured else '<div class="card-arrow">Read →</div>'
    return (
        f'<a class="{wrap_class}" href="issues/{iso}.html">'
        f'<div class="glass">'
        f'<div class="card-top"><div class="card-date">{pretty_date(iso)}</div>'
        f'<div class="card-tag">{tag}</div></div>'
        f'<div class="card-teaser">{teaser}</div>'
        f'{pills_html}'
        f'{arrow}'
        f'</div></a>'
    )


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    ISSUES.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(HERE)),
        autoescape=select_autoescape(disabled_extensions=("html",), default=False),
    )
    template = env.get_template(TEMPLATE_FILE)

    issues: list[tuple[str, dict]] = []
    for p in sorted(HISTORY.glob("*.json")):
        iso = p.stem  # YYYY-MM-DD
        try:
            payload = json.loads(p.read_text())
        except Exception as exc:
            print(f"[skip] {p.name}: {exc}")
            continue
        issues.append((iso, payload))

    if not issues:
        print("no history/*.json found — nothing to build")
        return

    for iso, payload in issues:
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
        page = ISSUE_SHELL.replace("__TITLE__", pretty_date(iso)).replace("__BODY__", body)
        (ISSUES / f"{iso}.html").write_text(page)
        print(f"[issue] docs/issues/{iso}.html")

    issues_newest_first = sorted(issues, key=lambda t: t[0], reverse=True)
    latest_iso, latest_payload = issues_newest_first[0]
    featured_html = render_card(latest_iso, latest_payload, featured=True)

    rest_cards = "\n".join(
        render_card(iso, p) for iso, p in issues_newest_first[1:]
    )

    cards_body = rest_cards or '<div style="color:#76767f;font-size:12px;text-align:center;padding:20px">No prior issues yet.</div>'
    index = (
        INDEX_SHELL
        .replace("__TOTAL__", str(len(issues)))
        .replace("__UPDATED__", pretty_date(date.today().isoformat()))
        .replace("__FEATURED__", featured_html)
        .replace("__CARDS__", cards_body)
    )
    (DOCS / "index.html").write_text(index)
    print(f"[index] docs/index.html ({len(issues)} issues)")


if __name__ == "__main__":
    main()
