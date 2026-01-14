#!/usr/bin/env python3
"""Run the `sys_prompt.md` on a schedule and publish the result as a GitHub Issue.

Usage:
  - Set environment variables in a `.env` file or system env:
      OPENAI_API_KEY, GITHUB_TOKEN, GITHUB_REPO (owner/repo)
  - Optional: LANGSMITH_API_KEY to log runs to LangSmith (if available).
  - Run once: `python scripts/run_sys_prompt_agent.py --once`
  - Run scheduler: `python scripts/run_sys_prompt_agent.py`

This script uses APScheduler to schedule a job at 06:00 in the
`Europe/Paris` timezone on weekdays (Mon-Fri). That matches CET/CEST
behavior so the job runs at 06:00 local time in Central Europe.
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import time
from pathlib import Path

import requests
import openai
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Load .env from the repository root (or the current working directory)
load_dotenv()

LOG = logging.getLogger("sys_prompt_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _log_env_presence() -> None:
    # Log presence/absence of key environment variables without printing secrets
    model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
    openai_key_set = bool(os.environ.get("OPENAI_API_KEY"))
    gh_token_set = bool(os.environ.get("GITHUB_TOKEN"))
    gh_repo = os.environ.get("GITHUB_REPO")
    LOG.info(
        "Env: OPENAI_API_KEY=%s OPENAI_MODEL=%s GITHUB_TOKEN=%s GITHUB_REPO=%s",
        "set" if openai_key_set else "unset",
        model,
        "set" if gh_token_set else "unset",
        gh_repo or "unset",
    )


_log_env_presence()


ROOT = Path(__file__).resolve().parents[1]
SYS_PROMPT_PATH = ROOT / "sys_prompt.md"


def read_sys_prompt() -> str:
    if not SYS_PROMPT_PATH.exists():
        raise FileNotFoundError(f"{SYS_PROMPT_PATH} not found")
    return SYS_PROMPT_PATH.read_text(encoding="utf-8")


def call_openai_system(prompt_text: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")

    model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

    system_message = prompt_text
    user_message = (
        "Produce the Open Science News Digest for the past 48 hours" " as described in the system prompt."
    )

    # Try OpenAI v1 client patterns first (openai>=1.0.0).
    # There are multiple ways the package may expose the client, so try them safely.
    client = None
    last_exc: Exception | None = None
    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(api_key=api_key)
        else:
            # Some installs may expose class under top-level import
            try:
                from openai import OpenAI as OpenAIClass

                client = OpenAIClass(api_key=api_key)
            except Exception as e:
                last_exc = e
                client = None

        if client is not None:
            LOG.info("Calling OpenAI model %s via OpenAI v1 client", model)
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                max_tokens=1500,
            )

            # v1 returns 'choices' with a 'message' field. The message may be a mapping
            # or an object depending on the client. Try multiple access patterns.
            try:
                choice = response.choices[0]
            except Exception:
                raise

            def _extract_text_from_choice(ch):
                # 1) Try subscription/dict-like access
                try:
                    return ch["message"]["content"]
                except Exception:
                    pass

                # 2) Try attribute access on choice -> message -> content
                try:
                    msg = getattr(ch, "message", None)
                    if msg is not None:
                        try:
                            return msg["content"]
                        except Exception:
                            pass
                        try:
                            return getattr(msg, "content", None)
                        except Exception:
                            pass
                except Exception:
                    pass

                # 3) Try dict-like get on ch (if it behaves like mapping)
                try:
                    if isinstance(ch, dict):
                        m = ch.get("message")
                        if isinstance(m, dict):
                            return m.get("content")
                except Exception:
                    pass

                # 4) Older fallback fields
                try:
                    return ch["text"]
                except Exception:
                    pass
                try:
                    return getattr(ch, "text", None)
                except Exception:
                    pass

                return None

            text = _extract_text_from_choice(choice) or ""
            text = (text or "").strip()
            if text:
                return text
            # If we didn't get usable text, raise to allow fallback or a clear error
            raise RuntimeError("OpenAI v1 client returned no content in choices[0].message")
    except Exception as e:
        last_exc = e
        LOG.debug("OpenAI v1 client attempt failed: %s", e)

    # Fallback: try legacy (pre-1.0) openai API if available in the installed package.
    try:
        if hasattr(openai, "ChatCompletion"):
            LOG.info("Falling back to legacy OpenAI API (ChatCompletion)")
            openai_api_key = os.environ.get("OPENAI_API_KEY")
            if openai_api_key:
                openai.api_key = openai_api_key
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                max_tokens=1500,
            )
            text = response["choices"][0]["message"]["content"].strip()
            return text
    except Exception as e:
        last_exc = e
        LOG.debug("Legacy OpenAI API attempt failed: %s", e)

    # If we reach here, we couldn't call OpenAI with available installation.
    msg = (
        "OpenAI client could not be initialized. "
        "Please ensure you have either openai>=1.0.0 or the legacy openai client installed. "
    )
    if last_exc is not None:
        msg += f"Last error: {last_exc!r}"
    raise RuntimeError(msg)


def create_github_issue(repo: str, token: str, title: str, body: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {"title": title, "body": body}
    r = requests.post(url, json=data, headers=headers, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub API error {r.status_code}: {r.text}")
    return r.json()


def build_issue_title(now: datetime.date) -> str:
    return f"Open Science News Digest — {now.isoformat()}"


def sanitize_digest_for_issue(body: str, issue_date: datetime.date) -> str:
    """Sanitize the generated digest body.

    - Replace any top-level heading dates (e.g., 'Open Science News Digest — YYYY-MM-DD' or
      other dates in the main title) with the canonical `issue_date`.
    - If the digest includes an explicit line like 'Date: ...' at the top, ensure it matches
      `issue_date` or replace it with 'Date: unknown' if the generated date is not ISO-like.
    """
    from datetime import date
    import re

    iso = issue_date.isoformat()

    # Replace common title forms that include a date
    body = re.sub(r"Open Science News Digest\s*[—-]\s*\d{4}-\d{2}-\d{2}",
                  f"Open Science News Digest — {iso}",
                  body)

    # Replace standalone 'Date: ...' at the top (first 5 lines)
    lines = body.splitlines()
    for i in range(min(6, len(lines))):
        m = re.match(r"^Date:\s*(.*)$", lines[i])
        if m:
            candidate = m.group(1).strip()
            # If candidate is an ISO date, normalize to the issue date
            try:
                parsed = date.fromisoformat(candidate)
                # Use issue_date instead of whatever the model inserted
                lines[i] = f"Date: {iso}"
            except Exception:
                # Not ISO — avoid trusting it; set to unknown
                lines[i] = "Date: unknown"
            break

    return "\n".join(lines)


def job_once() -> None:
    LOG.info("Job started")
    prompt_text = read_sys_prompt()
    try:
        digest = call_openai_system(prompt_text)
    except Exception as e:
        LOG.exception("OpenAI call failed: %s", e)
        return

    # Post to GitHub if configured
    gh_token = os.environ.get("GITHUB_TOKEN")
    gh_repo = os.environ.get("GITHUB_REPO")
    title = build_issue_title(datetime.date.today())

    if gh_token and gh_repo:
        try:
            # Sanitize digest to prevent date hallucinations in headings
            digest = sanitize_digest_for_issue(digest, datetime.date.today())
            issue = create_github_issue(gh_repo, gh_token, title, digest)
            LOG.info("Created GitHub issue: %s", issue.get("html_url"))
        except Exception as e:
            LOG.exception("Failed to create GitHub issue: %s", e)
    else:
        LOG.info("GITHUB_TOKEN or GITHUB_REPO not set — skipping GitHub publishing")

        # LangSmith logging removed by user request.


def main(run_once: bool = False) -> None:
    if run_once:
        job_once()
        return

    # Schedule: weekdays at 06:00 Europe/Paris (CET/CEST)
    tz = pytz.timezone("Europe/Paris")
    scheduler = BackgroundScheduler()
    trigger = CronTrigger(day_of_week="mon-fri", hour=6, minute=0, timezone=tz)
    scheduler.add_job(job_once, trigger, id="sys_prompt_weekday_job")
    scheduler.start()
    LOG.info("Scheduler started — job scheduled Mon-Fri 06:00 Europe/Paris")

    try:
        while True:
            time.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        LOG.info("Shutting down scheduler")
        scheduler.shutdown()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Run job once and exit")
    args = p.parse_args()
    main(run_once=args.once)
