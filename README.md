# ARlab weekly newsletter

Auto-generates Wissam's intelligence briefing every Tuesday at 09:00 Beirut and emails it.

## Pipeline

1. **`generate.py`** asks Claude Opus 4.7 to web-search the past week in AR / AI / immersive / adtech and return a structured 8-section payload via a tool call.
2. The payload is rendered into the glass HTML template (`template.html`) with Jinja2.
3. The HTML is emailed via Resend.

## Secrets (GitHub Actions)

- `ANTHROPIC_API_KEY`
- `RESEND_API_KEY`

Optional repo variables:

- `RECIPIENT_EMAIL` — defaults to `nour@thearlab.com`
- `SENDER_EMAIL` — defaults to `onboarding@resend.dev` (works with no domain). Switch to a verified ARlab address once the domain is verified in Resend.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
export RESEND_API_KEY=...
export SKIP_SEND=1   # render only, don't email
python generate.py
open out/newsletter-*.html
```

## Schedule

`cron: "0 6 * * 2"` — Tuesday 06:00 UTC = 09:00 Beirut (UTC+3 year-round, no DST).
