"""Send the derivative "3D & AI team" tools-only digest.

Reads the most recent history/*.json payload, renders it through
template_tools_digest.html, and emails the tools-only slice via Gmail OAuth
to a dedicated recipient list.

Env vars (all required):
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
  SENDER_EMAIL         (defaults to nour@thearlab.com)
  TOOLS_TO_EMAILS      (comma-separated; TO list)
  TOOLS_CC_EMAILS      (comma-separated; CC list)

Optional:
  SKIP_SEND=1          (render only, do not email)
  DIGEST_DATE=YYYY-MM-DD (force a specific payload date; default = latest)
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from jinja2 import Environment, FileSystemLoader, select_autoescape


HERE = pathlib.Path(__file__).parent
HISTORY = HERE / "history"
OUT = HERE / "out"
TEMPLATE_FILE = "template_tools_digest.html"

DEFAULT_TO = "ahmad@thearlab.com,shadi@thearlab.com,mike@thearlab.com"
DEFAULT_CC = "dalia@thearlab.com,wissam@thearlab.com"
SENDER_DEFAULT = "nour@thearlab.com"
SUBJECT = "3D & AI team — tools to check this week"


def latest_payload() -> tuple[str, dict]:
    stamp = os.environ.get("DIGEST_DATE", "").strip()
    if stamp:
        p = HISTORY / f"{stamp}.json"
        if not p.exists():
            raise SystemExit(f"[digest] payload not found: {p}")
        return stamp, json.loads(p.read_text())
    candidates = sorted(HISTORY.glob("*.json"), reverse=True)
    if not candidates:
        raise SystemExit("[digest] no history payloads found")
    p = candidates[0]
    return p.stem, json.loads(p.read_text())


def render(payload: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(HERE)),
        autoescape=select_autoescape(disabled_extensions=("html",), default=False),
    )
    template = env.get_template(TEMPLATE_FILE)
    return template.render(
        date=payload.get("date_display", ""),
        tools=payload.get("tools", []),
    )


def send(html: str, payload: dict) -> None:
    sender = os.environ.get("SENDER_EMAIL", SENDER_DEFAULT)
    to_list = [r.strip() for r in os.environ.get("TOOLS_TO_EMAILS", DEFAULT_TO).split(",") if r.strip()]
    cc_list = [c.strip() for c in os.environ.get("TOOLS_CC_EMAILS", DEFAULT_CC).split(",") if c.strip()]

    if not to_list:
        raise SystemExit("[digest] no recipients in TOOLS_TO_EMAILS")

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GMAIL_REFRESH_TOKEN"],
        client_id=os.environ["GMAIL_CLIENT_ID"],
        client_secret=os.environ["GMAIL_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    cc_str = ", ".join(cc_list)
    cc_log = f" cc={cc_str}" if cc_str else ""
    msg = EmailMessage()
    msg["To"] = ", ".join(to_list)
    if cc_str:
        msg["Cc"] = cc_str
    msg["From"] = sender
    msg["Subject"] = SUBJECT
    msg.set_content("This email is best viewed as HTML. " + payload.get("date_display", ""))
    msg.add_alternative(html, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    print(f"[digest] {sender} -> {', '.join(to_list)}{cc_log}  «{SUBJECT}» (date: {payload.get('date_display','?')})", flush=True)
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"[digest] gmail id: {sent.get('id', '?')}", flush=True)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    stamp, payload = latest_payload()
    tools = payload.get("tools", [])
    if not tools:
        print(f"[digest] payload {stamp} has no tools section — skipping", file=sys.stderr)
        return 0

    html = render(payload)
    out_path = OUT / f"tools-digest-{stamp}.html"
    out_path.write_text(html)
    print(f"[digest] rendered {out_path.name} ({len(html)} bytes, {len(tools)} tools)", flush=True)

    if os.environ.get("SKIP_SEND") == "1":
        print("[digest] SKIP_SEND=1 — not emailing", flush=True)
        return 0

    send(html, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
