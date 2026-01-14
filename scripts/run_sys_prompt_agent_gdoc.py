#!/usr/bin/env python3
"""Run the Open Science digest and append it to a rolling Google Doc.

This script reuses the existing `run_sys_prompt_agent` logic to produce a digest
and then appends the digest to a Google Document if `GOOGLE_SERVICE_ACCOUNT_JSON`
and `GDOC_ID` are provided in the environment.

Setup:
 - Create a Google service account with `Docs API` access and download JSON key.
 - Set `GOOGLE_SERVICE_ACCOUNT_JSON` to the path of the JSON file, or the JSON
   content itself. Set `GDOC_ID` to the target Google Document ID.

Run:
 - `python scripts/run_sys_prompt_agent_gdoc.py --once`
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from google.oauth2 import service_account

from run_sys_prompt_agent import call_openai_system, read_sys_prompt, sanitize_digest_for_issue

# Load .env from the repository root (or the current working directory)
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("sys_prompt_agent_gdoc")


def load_service_account_creds() -> Optional[service_account.Credentials]:
    sa = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa:
        return None

    # If the env var appears to be a path, load file
    try:
        p = Path(sa)
        if p.exists():
            sa = p.read_text(encoding="utf-8")
    except Exception:
        pass

    info = json.loads(sa)
    creds = service_account.Credentials.from_service_account_info(info, scopes=[
        "https://www.googleapis.com/auth/documents"
    ])
    return creds


def append_to_gdoc(creds: service_account.Credentials, doc_id: str, content: str) -> None:
    service = build("docs", "v1", credentials=creds)
    # Append a header with date and the content as a paragraph
    requests = [
        {
            "insertText": {
                "location": {"index": 1},
                "text": content + "\n\n"
            }
        }
    ]
    result = service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    LOG.info("Appended content to Google Doc %s", doc_id)


def main(run_once: bool = False) -> None:
    prompt_text = read_sys_prompt()
    digest = call_openai_system(prompt_text)
    digest = sanitize_digest_for_issue(digest, __import__("datetime").date.today())

    gdoc_id = os.environ.get("GDOC_ID")
    print("GDOC_ID:", gdoc_id)
    creds = load_service_account_creds()
    if not (gdoc_id and creds):
        LOG.info("GDOC_ID or GOOGLE_SERVICE_ACCOUNT_JSON not set — skipping Google Doc append")
        print(digest)
        return

    append_to_gdoc(creds, gdoc_id, digest)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="Run once and exit")
    args = p.parse_args()
    main(run_once=args.once)
