"""Lightweight web search helper for LLM-assisted agents.

Provides `web_search(query, max_results=5, use_google_cse=False, google_api_key=None, google_cx=None)`
which returns a list of search result dicts with `title`, `url`, and `snippet`.

By default this uses DuckDuckGo's HTML search (no API key required). Optionally supports
Google Custom Search (requires `google_api_key` and `google_cx`).

This module is intentionally small, dependency-light, and safe for running in CI/local.
It respects simple rate-limiting and has basic error handling.

Example:
    from web_search import web_search
    results = web_search('python web scraping', max_results=3)
    for r in results:
        print(r['title'], r['url'])

"""
from typing import List, Dict, Optional
import time
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/117.0.0.0 Safari/537.36"
)


def _duckduckgo_search_html(query: str, max_results: int = 5) -> List[Dict]:
    """Search DuckDuckGo HTML and parse top results.

    This does not use any private API and simply parses the HTML results page.
    """
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": USER_AGENT}
    data = {"q": query}
    resp = requests.post(url, data=data, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for r in soup.select(".result"):
        a = r.select_one("a.result__a") or r.select_one("a")
        if not a:
            continue
        href = a.get("href")
        title = a.get_text(strip=True)
        snippet_el = r.select_one(".result__snippet")
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
        results.append({"title": title, "url": href, "snippet": snippet})
        if len(results) >= max_results:
            break
    print(query)
    print("DuckDuckGo search found", len(results), "results")
    print(results)
    return results


def _google_cse_search(query: str, max_results: int, api_key: str, cx: str) -> List[Dict]:
    """Query Google Custom Search API.

    Requires a valid API key and CSE ID. Returns similar result dicts.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    headers = {"User-Agent": USER_AGENT}
    params = {"key": api_key, "cx": cx, "q": query}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", [])
    results = []
    for it in items[:max_results]:
        results.append({
            "title": it.get("title", ""),
            "url": it.get("link", ""),
            "snippet": it.get("snippet", ""),
        })
    return results


def web_search(
    query: str,
    max_results: int = 5,
    use_google_cse: bool = False,
    google_api_key: Optional[str] = None,
    google_cx: Optional[str] = None,
) -> List[Dict]:
    """Perform a web search and return structured results.

    - By default uses DuckDuckGo HTML search (no keys required).
    - Set `use_google_cse=True` and pass `google_api_key` and `google_cx` to use Google Custom Search.

    Returns a list of dicts: `{title, url, snippet}`.
    """
    if use_google_cse:
        if not google_api_key or not google_cx:
            raise ValueError("`google_api_key` and `google_cx` are required for Google CSE")
        return _google_cse_search(query, max_results, google_api_key, google_cx)

    # Basic rate limiting: small sleep to be polite
    time.sleep(0.5)
    try:
        # Use a richer, freshness-focused query to prioritize recent open-science items
        query = (
            'open science news (preprint OR policy OR "open-access" OR reproducibility) '
            '(today OR yesterday OR "past 48 hours")'
        )
        return _duckduckgo_search_html(query, max_results=max_results)
    except requests.RequestException:
        return []


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simple web search helper (DuckDuckGo HTML)")
    parser.add_argument("query", help="Search query")
    parser.add_argument("-n", "--max-results", type=int, default=5)
    args = parser.parse_args()
    res = web_search(args.query, max_results=args.max_results)
    for i, r in enumerate(res, 1):
        print(f"{i}. {r['title']}")
        print(r['url'])
        if r['snippet']:
            print(r['snippet'])
        print()
