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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import pytz

load_dotenv()

LOG = logging.getLogger("sys_prompt_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


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
    openai.api_key = api_key

    model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

    system_message = prompt_text
    user_message = (
        "Produce the Open Science News Digest for the past 48 hours" " as described in the system prompt."
    )

    LOG.info("Calling OpenAI model %s", model)
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
            issue = create_github_issue(gh_repo, gh_token, title, digest)
            LOG.info("Created GitHub issue: %s", issue.get("html_url"))
        except Exception as e:
            LOG.exception("Failed to create GitHub issue: %s", e)
    else:
        LOG.info("GITHUB_TOKEN or GITHUB_REPO not set — skipping GitHub publishing")

    # Optional LangSmith logging (best-effort)
    ls_api_key = os.environ.get("LANGSMITH_API_KEY")
    if ls_api_key:
        try:
            # Import lazily to avoid hard dependency for users who don't use LangSmith
            from langsmith import Client as LangSmithClient

            client = LangSmithClient(ls_api_key)
            client.create_run(name=title, inputs={"digest": digest})
            LOG.info("Logged run to LangSmith")
        except Exception:
            LOG.exception("LangSmith logging failed (optional)")


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
