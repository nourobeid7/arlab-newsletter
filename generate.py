"""
ARlab weekly newsletter generator.

Runs once a week (GitHub Actions cron):
  1. Asks Claude Opus 4.7 to research the past week in AR / AI / immersive / adtech
     using server-side web search, then to fill an 8-section structured payload.
  2. Renders that payload into the glass HTML template.
  3. Emails the rendered HTML to the recipient via Resend.

All keys come from env vars (set as GitHub Actions secrets).
"""

from __future__ import annotations

import os
import sys
import json
import pathlib
import datetime as dt
import zoneinfo

import anthropic
import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape


# -- Config ------------------------------------------------------------------

MODEL = "claude-opus-4-7"
MAX_TOKENS = 20_000  # > 16k → streaming required on Opus 4.7
RECIPIENT = os.environ.get("RECIPIENT_EMAIL", "nour@thearlab.com")
SENDER = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")  # default works without a verified domain
SUBJECT_PREFIX = "Wissam's Newsletter"

HERE = pathlib.Path(__file__).parent
TEMPLATE_FILE = "template.html"


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

# Hard rules
1. Web search is mandatory. Open multiple sources. Cross-check before stating a fact.
2. Every Signal, Coming Next, Undisclosed, Lab, Tool, Partner, and Pattern must be grounded in something that actually happened or shipped in roughly the last 7 days — or, for Patterns, a current undeniable shift.
3. For First of Its Kind: every entry MUST have a real, working https URL pointing at the project, lab page, or paper. No invented links.
4. For Tools: only sharp-edge stuff, no household names like ChatGPT, Midjourney, Runway-only-because-it-exists. Pick what gives ARlab a real edge this month.
5. Action Plan: NEVER name a person. Refer to teams, functions, or roles only ("the web team", "R&D", "whoever owns the pipeline", "the partnerships function"). Hard rule, no exceptions.
6. Tone is the existing voice: short, assertive, slightly literary, lowercase headlines feel premium, no marketing fluff, no "exciting times ahead". Sentence case. Use <b>...</b> sparingly to bold brand names, products, and hard numbers.
7. Date stamp: use today's date in DD · MM · YYYY format with a middle dot and spaces.
8. Output everything via the submit_newsletter tool. Call it exactly once when you are done researching and writing.

# Style examples to match
Signal headline:  "Platforms now build the whole ad themselves."
Signal arlab_use: "stop selling volume production — sell the strategy, craft and platform mastery AI can't."
Coming Next category: "Smart Glasses"
Pattern headline:  "Selling files is over. Selling a running system is the business now."

Begin research now. Search broadly across the past 7-10 days. Then call submit_newsletter."""


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


def call_claude(client: anthropic.Anthropic) -> dict:
    today = today_beirut()
    user_msg = (
        f"Generate this week's ARlab newsletter for Wissam. "
        f"Today is {today.isoformat()} (Beirut). "
        f"Search the past 7-10 days. Then call submit_newsletter with the full payload."
    )

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

def render(payload: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(HERE)),
        autoescape=select_autoescape(disabled_extensions=("html",), default=False),
    )
    template = env.get_template(TEMPLATE_FILE)
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


def send_email(html: str, payload: dict) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    subject = f"{SUBJECT_PREFIX} — {payload['date_display']}"
    print(f"[send] {SENDER} -> {RECIPIENT}  «{subject}»", flush=True)
    result = resend.Emails.send({
        "from": SENDER,
        "to": [RECIPIENT],
        "subject": subject,
        "html": html,
    })
    print(f"[send] resend id: {result.get('id', '?')}", flush=True)


# -- Entry point -------------------------------------------------------------

def main() -> int:
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    payload = call_claude(client)

    out_dir = HERE / "out"
    out_dir.mkdir(exist_ok=True)
    stamp = today_beirut().isoformat()
    (out_dir / f"payload-{stamp}.json").write_text(json.dumps(payload, indent=2))

    html = render(payload)
    (out_dir / f"newsletter-{stamp}.html").write_text(html)
    print(f"[render] wrote out/newsletter-{stamp}.html ({len(html)} bytes)", flush=True)

    if os.environ.get("SKIP_SEND") == "1":
        print("[send] SKIP_SEND=1 — not emailing", flush=True)
        return 0

    send_email(html, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
