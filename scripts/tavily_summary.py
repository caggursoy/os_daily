#!/usr/bin/env python3
"""Search Tavily, summarize results with OpenAI, and save an email-body markdown.

Usage:
  - Set environment variables: TAVILY_API_KEY, OPENAI_API_KEY
  - Optional: TAVILY_API_URL (defaults to Tavily public endpoint), OPENAI_MODEL
  - Run: `python scripts/tavily_summary.py --query "open science"`

The script will create `summaries/YYYY-MM-DD.md` containing the generated
email-style markdown summary for today's date.
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import requests
import openai
import certifi
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv

load_dotenv()

LOG = logging.getLogger("tavily_summary")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parents[1]
SUMMARIES_DIR = ROOT / "summaries"
SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)


def tavily_search(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Perform a search using the Tavily API and return list of results.

    Each result is a dict with keys: 'title', 'snippet', 'url'.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise EnvironmentError("TAVILY_API_KEY is not set")

    base_url = os.environ.get("TAVILY_API_URL", "https://api.tavily.ai/v1/search")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"q": query, "size": max_results}

    # initial log is above; continue to prefer client
    # Determine CA bundle to use for TLS verification. Priority:
    # 1. TAVILY_CA_BUNDLE env var
    # 2. REQUESTS_CA_BUNDLE env var
    # 3. `certificates.pem` in the repository root (if present)
    LOG.info("Calling Tavily search for query: %s", query)

    # Prefer using the official tavily-python client if available
    try:
        from tavily import TavilyClient  # type: ignore

        client = TavilyClient(api_key)
        # allow configurable depth via env var
        search_depth = os.environ.get("TAVILY_SEARCH_DEPTH", "advanced")
        try:
            resp = client.search(query=query, search_depth=search_depth, size=max_results, exclude_domains=["facebook.com"])
        except TypeError:
            # Older/newer client may use different param names
            resp = client.search(query=query, search_depth=search_depth, exclude_domains=["facebook.com"])
        # normalize response to dict-like
        if hasattr(resp, "to_dict"):
            data = resp.to_dict()
        elif isinstance(resp, dict):
            data = resp
        else:
            data = {"results": getattr(resp, "results", [])}

        items = []
        for item in data.get("results", [])[:max_results]:
            if isinstance(item, dict):
                title = item.get("title", "")
                snippet = item.get("snippet") or item.get("summary") or item.get("text") or ""
                url = item.get("url") or item.get("link") or ""
            else:
                title = getattr(item, "title", "")
                snippet = getattr(item, "snippet", None) or getattr(item, "summary", "") or getattr(item, "text", "")
                url = getattr(item, "url", "")

            items.append({"title": (title or "").strip(), "snippet": (snippet or "").strip(), "url": (url or "").strip()})

        return items
    except Exception as e:  # fall back to raw HTTP if client not installed or call fails
        LOG.info("Tavily client unavailable or failed (%s); falling back to HTTP POST", e)

    # Fallback HTTP POST path (preserve previous behavior with CA bundle support)
    base_url = os.environ.get("TAVILY_API_URL", "https://api.tavily.ai/v1/search")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"q": query, "size": max_results}

    # Determine CA bundle to use for TLS verification. Priority:
    # 1. TAVILY_CA_BUNDLE env var
    # 2. REQUESTS_CA_BUNDLE env var
    # 3. certifi CA bundle
    ca_bundle_env = os.environ.get("TAVILY_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE")
    default_bundle = certifi.where()
    ca_bundle_path = None
    if ca_bundle_env:
        if Path(ca_bundle_env).exists():
            ca_bundle_path = ca_bundle_env
        else:
            LOG.warning("CA bundle path from env does not exist: %s; ignoring", ca_bundle_env)
    if ca_bundle_path is None and Path(default_bundle).exists():
        ca_bundle_path = str(default_bundle)

    verify_arg = ca_bundle_path if ca_bundle_path is not None else True
    LOG.info("Using CA bundle for TLS verification: %s", ca_bundle_path or "system default")

    # Allow overriding host for DNS troubleshooting
    api_host_override = os.environ.get("TAVILY_API_HOST")
    if api_host_override:
        parsed = urlparse(base_url)
        parsed = parsed._replace(netloc=api_host_override)
        base_url = urlunparse(parsed)

    # Basic retries with backoff for transient DNS/connectivity issues
    import time
    from requests.exceptions import ConnectionError as ReqConnErr

    attempts = int(os.environ.get("TAVILY_RETRIES", "3"))
    backoff = float(os.environ.get("TAVILY_BACKOFF", "1.0"))
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(base_url, headers=headers, json=payload, timeout=30, verify=verify_arg)
            r.raise_for_status()
            data = r.json()
            items = []
            for item in data.get("results", [])[:max_results]:
                title = item.get("title") or item.get("headline") or ""
                snippet = item.get("snippet") or item.get("summary") or item.get("text") or ""
                url = item.get("url") or item.get("link") or ""
                items.append({"title": title.strip(), "snippet": snippet.strip(), "url": url.strip()})
            return items
        except ReqConnErr as ce:
            LOG.warning("Connection attempt %d/%d failed: %s", attempt, attempts, ce)
            last_exc = ce
            # small diagnostic for DNS resolution failures
            try:
                import socket

                host = urlparse(base_url).hostname
                if host:
                    try:
                        addrs = socket.getaddrinfo(host, None)
                        LOG.debug("DNS lookup for %s returned: %s", host, addrs)
                    except Exception as dns_e:
                        LOG.debug("DNS lookup for %s failed: %s", host, dns_e)
            except Exception:
                pass
            time.sleep(backoff)
            backoff *= 2
            continue
        except Exception as e2:
            LOG.exception("Tavily HTTP request failed: %s", e2)
            raise

    # If we exhausted retries
    raise RuntimeError(f"Tavily API connection failed after {attempts} attempts: {last_exc}")


def build_search_context(results: List[Dict[str, str]], max_chars: int = 4000) -> str:
    if not results:
        return ""
    parts = ["Search results (from Tavily):"]
    for r in results:
        t = r.get("title", "")
        s = r.get("snippet", "")
        u = r.get("url", "")
        line = "".join([f"Title: {t}\n" if t else "", f"Snippet: {s}\n" if s else "", f"URL: {u}\n" if u else ""]) 
        parts.append(line.strip())
    blob = "\n\n".join(parts)
    if len(blob) > max_chars:
        blob = blob[: max_chars - 3] + "..."
    return blob + "\n\n"


def load_input_file(path: str, max_results: int = 10) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Load an example input JSON produced by other tools and map to internal results format.

    Returns (results, query) where results is a list of dicts with keys 'title','snippet','url'.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input JSON file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    query = data.get("query") if isinstance(data, dict) else None
    raw_results = data.get("results") if isinstance(data, dict) else None
    items: List[Dict[str, str]] = []
    if not raw_results:
        return items, query
    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("headline") or "").strip()
        snippet = (item.get("snippet") or item.get("content") or item.get("summary") or item.get("raw_content") or "").strip()
        url = (item.get("url") or item.get("link") or "").strip()
        items.append({"title": title, "snippet": snippet, "url": url})
    return items, query


def call_openai_summary(search_blob: str, query: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    system_prompt = (
        "You are an assistant that produces concise, professional email summaries of recent web findings. "
        "Given search results and a query, produce an email body in Markdown. "
        "Start with a short subject line, then a brief executive summary (3 bullets), then sections 'Policy', 'Tools', 'Research' if applicable. "
        "For each item include title, one-line summary, and source URL. "
        "If no items are relevant, return exactly: 'No significant items found in the past 48 hours.'"
    )
    user_message = f"Here's the search blob:\n\n{search_blob}\n\nProduce the email-body markdown as described."

    # Use OpenAI v1 client patterns if available
    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(api_key=api_key)
            LOG.info("Calling OpenAI model %s", model)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                temperature=0.7,
                max_tokens=1000,
            )
            print(resp)
            choice = resp.choices[0]
            # extract text robustly for different client shapes
            text = None
            # resp may be dict-like or object-like. Try common access patterns.
            # 1) dict shape: choice['message']['content']
            try:
                if isinstance(choice, dict):
                    text = choice.get("message", {}).get("content")
                else:
                    # object-like: choice.message.content or choice.message.get('content')
                    msg = getattr(choice, "message", None)
                    if msg is not None:
                        # msg might be a dict-like or object
                        if isinstance(msg, dict):
                            text = msg.get("content")
                        else:
                            # object with attributes or a mapping
                            content = getattr(msg, "content", None)
                            if content is None and hasattr(msg, "get"):
                                try:
                                    content = msg.get("content")
                                except Exception:
                                    content = None
                            text = content
            except Exception:
                text = None

            # 2) fallback shapes
            if not text:
                # sometimes the SDK stores assistant text as 'text'
                try:
                    text = choice.get("text") if isinstance(choice, dict) else getattr(choice, "text", None)
                except Exception:
                    text = None

            # 3) final fallback: search string repr for 'content=' patterns (very last resort)
            if not text:
                try:
                    s = str(choice)
                    # crude extraction for ChatCompletion(...) style strings
                    # look for message content between 'content="' and '"'
                    import re

                    m = re.search(r"content\s*=\s*\"(.*?)\"", s)
                    if m:
                        text = m.group(1)
                except Exception:
                    text = None

            return (text or "").strip()

    except Exception as e:
        LOG.debug("OpenAI v1 client failed: %s", e)

    # Fallback to legacy openai
    try:
        openai.api_key = api_key
        LOG.info("Calling legacy OpenAI ChatCompletion %s", model)
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
            temperature=0.0,
            max_tokens=1000,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        LOG.exception("OpenAI call failed: %s", e)
        raise


def write_summary_file(markdown: str, date: datetime.date) -> Path:
    filename = f"{date.isoformat()}.md"
    path = SUMMARIES_DIR / filename
    header = f"Subject: Open Science News Digest — {date.isoformat()}\n\n"
    content = header + markdown
    path.write_text(content, encoding="utf-8")
    LOG.info("Wrote summary to %s", path)
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--query", required=False, help="Search query to send to Tavily (optional when using --input-json)")
    p.add_argument("--input-json", required=False, help="Path to an input JSON file (use results inside instead of Tavily search)")
    p.add_argument("--max-results", type=int, default=8)
    args = p.parse_args()

    # If an input JSON is provided, use its results instead of calling Tavily.
    results: List[Dict[str, str]] = []
    file_query: Optional[str] = None
    if args.input_json:
        try:
            results, file_query = load_input_file(args.input_json, max_results=args.max_results)
            LOG.info("Loaded %d results from input JSON %s", len(results), args.input_json)
        except Exception as e:
            LOG.exception("Failed to load input JSON: %s", e)
            raise

    # Determine the query to use for the summarizer: CLI arg takes precedence,
    # then the input file's query. When neither is present and we will call
    # Tavily, require the CLI query.
    query = args.query or file_query
    if not query and not args.input_json:
        p.error("--query is required when not using --input-json")

    if not results:
        # No input JSON or it contained no results: perform Tavily search.
        results = tavily_search(query, max_results=args.max_results)
    search_blob = build_search_context(results)
    if search_blob:
        LOG.info("Using %d results in search context", len(results))
    else:
        LOG.info("No search results returned")

    summary = call_openai_summary(search_blob, args.query)
    today = datetime.date.today()
    out = write_summary_file(summary, today)
    print(f"Summary written to: {out}")


if __name__ == "__main__":
    main()
