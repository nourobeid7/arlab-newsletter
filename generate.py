"""
ARlab weekly newsletter generator.

Runs once a week (GitHub Actions cron):
  1. Asks Claude Opus 4.7 to research the past week in AR / AI / immersive / adtech
     using server-side web search, then to fill an 8-section structured payload.
  2. Renders that payload into the glass HTML template.
  3. Emails the rendered HTML to the recipient via Gmail API (OAuth2).

All keys come from env vars (set as GitHub Actions secrets).
"""

from __future__ import annotations

import os
import sys
import json
import pathlib
import datetime as dt
import zoneinfo

import base64
from email.message import EmailMessage

import anthropic
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader, select_autoescape


# -- Config ------------------------------------------------------------------

MODEL = "claude-opus-4-7"
MAX_TOKENS = 20_000  # > 16k → streaming required on Opus 4.7
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "wissam@thearlab.com")
SENDER = os.environ.get("SENDER_EMAIL", "nour@thearlab.com")
SUBJECT_PREFIX = "Wissam's Newsletter"

HERE = pathlib.Path(__file__).parent
TEMPLATE_FILE = "template.html"  # browser-preview version with glass effect
EMAIL_TEMPLATE_FILE = "template_email.html"  # gmail-safe inline-styled version


# -- Schema for the structured newsletter payload ----------------------------

NEWSLETTER_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "date_display",
        "signals",
        "coming_next",
        "undisclosed",
        "first_of_kind",
        "tools",
        "partners",
        "patterns",
        "action_plan",
    ],
    "properties": {
        "date_display": {
            "type": "string",
            "description": "Today's date in DD · MM · YYYY format with thin spaces around the dots, e.g. '12 · 06 · 2026'.",
        },
        "signals": {
            "type": "array",
            "minItems": 6,
            "maxItems": 6,
            "description": "Six biggest shifts of the past week. Each is one sharp move.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["headline", "body", "arlab_use"],
                "properties": {
                    "headline": {"type": "string", "description": "One assertive sentence, sentence case, ends with a period."},
                    "body": {"type": "string", "description": "2-4 sentences. Use <b>...</b> to bold company names, products, or hard numbers. No links."},
                    "arlab_use": {"type": "string", "description": "ONE clause, lowercase, what ARlab should do about it. No team member names. Will render in uppercase via CSS."},
                },
            },
        },
        "coming_next": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["category", "headline", "body"],
                "properties": {
                    "category": {"type": "string", "description": "Two words max, Title Case (e.g. 'Smart Glasses')."},
                    "headline": {"type": "string", "description": "One assertive sentence."},
                    "body": {"type": "string", "description": "One sentence, may include <b>...</b>."},
                },
            },
        },
        "undisclosed": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "description": "Quiet projects, leaks, or under-the-radar pivots from the past week.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "classification", "body"],
                "properties": {
                    "name": {"type": "string"},
                    "classification": {
                        "type": "string",
                        "enum": ["Eyes only", "Restricted", "Confidential", "Emerging"],
                    },
                    "body": {"type": "string", "description": "2-3 sentences. May include <b>...</b>."},
                },
            },
        },
        "first_of_kind": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "description": "Bleeding-edge research or lab releases. Each must include a real, working URL.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "tag", "body", "link_url", "link_text"],
                "properties": {
                    "name": {"type": "string"},
                    "tag": {"type": "string", "description": "e.g. 'Research', 'Beta · waitlist', 'Shipped', 'Research preview'"},
                    "body": {"type": "string", "description": "2 sentences. May include <b>...</b>. Do NOT include the link here — it goes in link_url/link_text."},
                    "link_url": {"type": "string", "description": "Full https:// URL to the project, paper, or lab."},
                    "link_text": {"type": "string", "description": "Short visible link label, e.g. 'nature.com', 'lumalabs.ai'."},
                },
            },
        },
        "tools": {
            "type": "array",
            "minItems": 6,
            "maxItems": 6,
            "description": "Sharp-edge tools worth checking THIS WEEK. Not basics like ChatGPT/Midjourney.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["numeral", "name", "body", "link_url"],
                "properties": {
                    "numeral": {"type": "string", "enum": ["i", "ii", "iii", "iv", "v", "vi"]},
                    "name": {"type": "string", "description": "Tool / product name only."},
                    "body": {"type": "string", "description": "One sentence describing what it does and why it matters."},
                    "link_url": {"type": "string", "description": "Full https:// URL."},
                },
            },
        },
        "partners": {
            "type": "array",
            "minItems": 6,
            "maxItems": 6,
            "description": "Small companies / hidden gems that could be partners — not the big platforms.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["category", "name", "body"],
                "properties": {
                    "category": {"type": "string", "description": "2-3 word category, Title Case (e.g. 'Live video AI')."},
                    "name": {"type": "string"},
                    "body": {"type": "string", "description": "One sentence on the leverage."},
                },
            },
        },
        "patterns": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "description": "Deeper currents, not weekly news. Three Global + one GCC-specific.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["tag", "headline", "body"],
                "properties": {
                    "tag": {"type": "string", "enum": ["Global", "GCC · our region"]},
                    "headline": {"type": "string", "description": "Assertive thesis sentence."},
                    "body": {"type": "string", "description": "2-3 sentences. May include <b>...</b>."},
                },
            },
        },
        "action_plan": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "description": "Four concrete moves ARlab should start this week. NEVER name a person — describe the function instead (e.g. 'the web team', 'R&D', 'whoever owns the pipeline').",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["numeral", "title", "body"],
                "properties": {
                    "numeral": {"type": "string", "enum": ["i", "ii", "iii", "iv"]},
                    "title": {"type": "string", "description": "Imperative title, one line. No team member names."},
                    "body": {"type": "string", "description": "1-2 sentences explaining the move. No team member names."},
                },
            },
        },
    },
}


# -- System prompt (cached) --------------------------------------------------

SYSTEM_PROMPT = """You are the senior strategy editor for ARlab, writing the weekly intelligence briefing for the CEO, Wissam.

# About ARlab
ARlab is a creative technology studio in MENA (HQ Beirut, working across the GCC). We build AR / AI / immersive / web3D experiences for brands — interactive campaigns, branded virtual environments, smart-glass experiences, real-time AI installations, and live, always-on creative systems. Our stack is HTML/JS, Three.js / WebGPU, real-time AI (video, voice, world models), Spark AR / Lens Studio / Apple ARKit, Unity for installations. We sell creative + tech as one bundle, not files. The GCC is our biggest market — NEOM, Qiddiya, Diriyah, Qatar, Riyadh agencies, UAE brands.

# What Wissam (the CEO) needs every Tuesday
A 5-minute read that surfaces what genuinely moved in the past 7 days in: AR/VR/XR, smart glasses, generative AI (image, video, audio, world models), AI agents and MCP, real-time / live AI, immersive web (WebGPU, gaussian splats), AI ad platforms, and any of this with a GCC angle. He already knows the basics — give him the sharp edge: what shifts the strategy, what wins a pitch, what to start building.

# Freshness rules (hard)
Today's date will be given in the user message. Treat that as authoritative — anchor every search and every claim against it.

- **Signals (6):** Every signal MUST cite an event, launch, leak, or announcement from the **last 7 days**. Before including anything, verify the publish date of the source. If the news is older than 7 days, REJECT it. Search with queries like "announced this week", "launched today", "<month> <year>", "<this week's date> news".
- **Coming Next (4):** Things expected to land in the next 30 days — releases, conferences, deadlines that are real.
- **Undisclosed (4):** Quiet projects, leaks, or pivots reported in the last 14 days.
- **First of Its Kind (4):** Lab releases, papers, research previews from the last 30 days. Every entry must have a real, working https URL.
- **Tools (6):** Sharpest-edge tools right now. Prefer tools updated, launched, or repriced in the last 30 days. No household names.
- **Partners (6):** Small companies / hidden gems — emphasis on those that gained relevance in the last 30 days.
- **Patterns (4):** Deeper currents that surface in the last 7-14 days of news. Three Global + one GCC.
- **Action Plan (4):** Concrete moves derived from the above. NEVER name a person — use roles only.

# Anti-repetition rule (hard)
The user message will list topics, companies, products, and headlines that have already been covered in recent newsletters. **Do not repeat them**, even with a different framing. If the same company is genuinely back in the news with a *new* development, you may cover the new development — but never recycle the previous talking point. Find different stories.

# Other hard rules
1. Web search is mandatory. Open multiple sources. Cross-check the publish date AND the facts before using anything.
2. For First of Its Kind: every entry MUST have a real, working https URL pointing at the project, lab page, or paper. No invented links — verify each URL.
3. For Tools: only sharp-edge stuff, no household names (no plain ChatGPT, no plain Midjourney). Pick what gives ARlab a real edge.
4. Action Plan: NEVER name a person. Refer to teams, functions, or roles only ("the web team", "R&D", "whoever owns the pipeline", "the partnerships function"). Hard rule, no exceptions.
5. Tone: short, assertive, slightly literary. Sentence case for headlines. Use <b>...</b> sparingly to bold brand names, products, and hard numbers.
6. Date stamp: use today's date in DD · MM · YYYY format with a middle dot and spaces.
7. Output everything via the submit_newsletter tool. Call it exactly once when you are done.

# Style examples (voice only — do NOT reuse these talking points)
Signal headline shape:  "Platforms now build the whole ad themselves." → assertive, full sentence, ends with period.
arlab_use shape: "stop selling volume production — sell the strategy AI can't." → lowercase, imperative, one move.
Pattern headline shape:  "Selling files is over. Selling a running system is the business now." → two sentences, thesis-first.

Begin research now. Today's date and the anti-repetition list are in the user message. Search hard for fresh stories from the past 7 days. Then call submit_newsletter."""


# -- Build the request -------------------------------------------------------

def build_tools() -> list[dict]:
    return [
        {"type": "web_search_20260209", "name": "web_search"},
        {
            "name": "submit_newsletter",
            "description": "Submit the final, fully-researched newsletter payload. Call this exactly once after all web research is complete.",
            "input_schema": NEWSLETTER_SCHEMA,
        },
    ]


def today_beirut() -> dt.date:
    return dt.datetime.now(zoneinfo.ZoneInfo("Asia/Beirut")).date()


def load_history() -> str:
    """Read every history/*.json and build a compact 'already covered' summary."""
    history_dir = HERE / "history"
    if not history_dir.exists():
        return "(No prior newsletters on record.)"

    files = sorted(history_dir.glob("*.json"), reverse=True)
    if not files:
        return "(No prior newsletters on record.)"

    parts: list[str] = []
    for f in files[:6]:  # cap at last 6 newsletters to keep the message tight
        try:
            doc = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        date = doc.get("date_display", f.stem)
        lines = [f"\n## Newsletter {date}  (already in Wissam's inbox — do NOT repeat)"]

        def names(key: str, label: str) -> None:
            items = doc.get(key, [])
            if not items:
                return
            entries = []
            for it in items:
                bits = []
                for k in ("headline", "name", "category", "title"):
                    if k in it and it[k]:
                        bits.append(str(it[k]))
                        break
                kt = it.get("key_terms") or []
                if kt:
                    bits.append("(" + ", ".join(kt) + ")")
                if bits:
                    entries.append(" ".join(bits))
            if entries:
                lines.append(f"- {label}: " + " | ".join(entries))

        names("signals", "Signals")
        names("coming_next", "Coming Next")
        names("undisclosed", "Undisclosed")
        names("first_of_kind", "First of Kind")
        names("tools", "Tools")
        names("partners", "Partners")
        names("patterns", "Patterns")
        names("action_plan", "Action Plan")
        parts.append("\n".join(lines))

    return "\n".join(parts)


def call_claude(client: anthropic.Anthropic) -> dict:
    today = today_beirut()
    week_ago = today - dt.timedelta(days=7)
    history_summary = load_history()

    user_msg = (
        f"Generate this week's ARlab newsletter for Wissam.\n\n"
        f"Today's date (authoritative): **{today.isoformat()}** (Asia/Beirut).\n"
        f"Strict freshness window for Signals: **{week_ago.isoformat()} to {today.isoformat()}** "
        f"(the last 7 calendar days). Verify publish dates with web search before using any source.\n\n"
        f"# Already covered — DO NOT REPEAT these topics, companies, products, talking points, or arlab_use phrasing. "
        f"Find different stories.\n{history_summary}\n\n"
        f"When research is complete, call submit_newsletter with the full payload. "
        f"date_display must be today in DD · MM · YYYY format."
    )
    print(f"[generate] history summary: {len(history_summary)} chars", flush=True)

    print(f"[generate] calling {MODEL}…", flush=True)
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=build_tools(),
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        final = stream.get_final_message()

    usage = final.usage
    print(
        f"[generate] usage: in={usage.input_tokens} out={usage.output_tokens} "
        f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)} "
        f"cache_create={getattr(usage, 'cache_creation_input_tokens', 0)}",
        flush=True,
    )

    for block in final.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "submit_newsletter":
            return block.input

    # Diagnostics if no tool call was returned
    print("[generate] no submit_newsletter tool_use in final response", file=sys.stderr)
    print(f"[generate] stop_reason={final.stop_reason}", file=sys.stderr)
    for b in final.content:
        print(f"[generate] block type={getattr(b, 'type', '?')}", file=sys.stderr)
    raise RuntimeError("Claude did not submit a newsletter payload.")


# -- Render and send ---------------------------------------------------------

def render(payload: dict, template_file: str = TEMPLATE_FILE) -> str:
    env = Environment(
        loader=FileSystemLoader(str(HERE)),
        autoescape=select_autoescape(disabled_extensions=("html",), default=False),
    )
    template = env.get_template(template_file)
    return template.render(
        date=payload["date_display"],
        signals=payload["signals"],
        coming_next=payload["coming_next"],
        undisclosed=payload["undisclosed"],
        first_of_kind=payload["first_of_kind"],
        tools=payload["tools"],
        partners=payload["partners"],
        patterns=payload["patterns"],
        action_plan=payload["action_plan"],
    )


def inject_preamble(html: str, preamble_html: str) -> str:
    """Insert a one-off preamble block immediately after <body ...>."""
    if not preamble_html:
        return html
    body_open = html.find("<body")
    if body_open == -1:
        return preamble_html + html
    body_open_close = html.find(">", body_open) + 1
    return html[:body_open_close] + preamble_html + html[body_open_close:]


def send_email(html: str, payload: dict) -> None:
    # Constant subject so Gmail threads all weekly editions together.
    subject = SUBJECT_PREFIX
    recipients = [r.strip() for r in RECIPIENT.split(",") if r.strip()]

    preamble = os.environ.get("PREAMBLE_HTML", "")
    if preamble:
        html = inject_preamble(html, preamble)
        print(f"[send] injected preamble ({len(preamble)} bytes)", flush=True)

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    for recipient in recipients:
        print(f"[send] {SENDER} -> {recipient}  «{subject}» (date in body: {payload['date_display']})", flush=True)
        msg = EmailMessage()
        msg["To"] = recipient
        msg["From"] = SENDER
        msg["Subject"] = subject
        msg.set_content("This email is best viewed as HTML. " + payload["date_display"])
        msg.add_alternative(html, subtype="html")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        print(f"[send] gmail id: {sent.get('id', '?')}", flush=True)


# -- Entry point -------------------------------------------------------------

def main() -> int:
    stamp = today_beirut().isoformat()
    history_dir = HERE / "history"
    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)
    history_dir.mkdir(exist_ok=True)

    if os.environ.get("SKIP_GENERATE") == "1":
        existing = history_dir / f"{stamp}.json"
        if not existing.exists():
            print(f"[generate] SKIP_GENERATE=1 but {existing} not found", file=sys.stderr)
            return 1
        payload = json.loads(existing.read_text())
        print(f"[generate] SKIP_GENERATE=1 — using existing {existing.name}", flush=True)
    else:
        client = anthropic.Anthropic()
        payload = call_claude(client)
        (out_dir / f"payload-{stamp}.json").write_text(json.dumps(payload, indent=2))
        (history_dir / f"{stamp}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"[history] wrote history/{stamp}.json", flush=True)

    html_preview = render(payload, TEMPLATE_FILE)
    (out_dir / f"newsletter-{stamp}.html").write_text(html_preview)
    print(f"[render] wrote out/newsletter-{stamp}.html ({len(html_preview)} bytes, preview)", flush=True)

    html_email = render(payload, EMAIL_TEMPLATE_FILE)
    (out_dir / f"newsletter-{stamp}-email.html").write_text(html_email)
    print(f"[render] wrote out/newsletter-{stamp}-email.html ({len(html_email)} bytes, gmail-safe)", flush=True)

    if os.environ.get("SKIP_SEND") == "1":
        print("[send] SKIP_SEND=1 — not emailing", flush=True)
        return 0

    send_email(html_email, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
