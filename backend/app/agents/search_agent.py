"""
SearchAgent: queries external search sources for candidate URLs, then scrapes
the top N results for full article text (instead of relying on short
snippets), using the rolling cache to avoid redundant re-scraping.
"""

from typing import List
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from app.agents.url_extractor import extract_article_text
from app.cache import scrape_cache
from app.config import settings


def _search_serpapi(query: str, num: int = 10) -> List[dict]:
    if not settings.serpapi_key:
        return []
    try:
        resp = requests.get(
            "https://serpapi.com/search",
            params={"q": query, "api_key": settings.serpapi_key, "num": num},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []

    results = []
    for item in data.get("organic_results", [])[:num]:
        results.append(
            {
                "url": item.get("link"),
                "title": item.get("title"),
                "snippet": item.get("snippet", ""),
            }
        )
    return [r for r in results if r["url"]]


def _search_newsapi(query: str, num: int = 10) -> List[dict]:
    if not settings.newsapi_key:
        return []
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": query, "pageSize": num, "sortBy": "relevancy"},
            headers={"X-Api-Key": settings.newsapi_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []

    results = []
    for item in data.get("articles", [])[:num]:
        results.append(
            {
                "url": item.get("url"),
                "title": item.get("title"),
                "snippet": item.get("description") or "",
            }
        )
    return [r for r in results if r["url"]]


def _clean_ddg_redirect(href: str) -> str:
    """DuckDuckGo's HTML results wrap outbound links in a redirect
    (//duckduckgo.com/l/?uddg=<encoded target>&...); unwrap it so we get
    the real article URL instead of a DDG-internal link."""
    if not href:
        return href
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg")
        if target:
            return unquote(target[0])
    return href


def _search_duckduckgo(query: str, num: int = 10) -> List[dict]:
    """
    Free, no-API-key general web search via DuckDuckGo's HTML results page.
    (Deliberately NOT api.duckduckgo.com/?format=json -- that's the Instant
    Answer API, meant for knowledge-panel widgets. It only returns loosely
    keyword-matched "related topics" for well-known entities, which is why
    it used to surface irrelevant noise like unrelated corporate homepages
    for ordinary news queries -- it was never actually searching the query.)
    """
    try:
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; FactCheckBot/1.0)"},
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException:
        return []

    results = []
    for result in soup.select("div.result")[:num]:
        link_tag = result.select_one("a.result__a")
        snippet_tag = result.select_one(".result__snippet")
        if not link_tag or not link_tag.get("href"):
            continue
        url = _clean_ddg_redirect(link_tag["href"])
        if not url.startswith("http"):
            continue
        results.append(
            {
                "url": url,
                "title": link_tag.get_text(strip=True),
                "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
            }
        )
    return results


def _search_wikipedia(query: str, num: int = 4) -> List[dict]:
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": num,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []

    results = []
    for item in data.get("query", {}).get("search", [])[:num]:
        title = item.get("title", "")
        results.append(
            {
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "title": title,
                "snippet": item.get("snippet", ""),
            }
        )
    return results


def _search_google_news_rss(query: str, num: int = 10) -> List[dict]:
    """
    Free, no-API-key news source: Google News' public RSS search feed.
    This is what makes it possible to reliably scrape more than 10
    corroborating sources even when SERPAPI_KEY / NEWSAPI_KEY aren't set.
    """
    try:
        resp = requests.get(
            f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en",
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")
    except Exception:
        return []

    results = []
    for item in soup.find_all("item")[:num]:
        link = item.find("link")
        title = item.find("title")
        description = item.find("description")
        url = link.get_text(strip=True) if link else None
        if url:
            results.append(
                {
                    "url": url,
                    "title": title.get_text(strip=True) if title else None,
                    "snippet": description.get_text(strip=True) if description else "",
                }
            )
    return results


def gather_candidate_urls(query: str) -> List[dict]:
    """Combine all sources, de-duplicated by URL, preserving order/priority."""
    combined: List[dict] = []
    seen = set()
    for fn in (
        _search_serpapi,
        _search_newsapi,
        _search_google_news_rss,
        _search_duckduckgo,
        _search_wikipedia,
    ):
        for item in fn(query):
            if item["url"] not in seen:
                seen.add(item["url"])
                combined.append(item)
    return combined


def scrape_top_results(candidates: List[dict], top_n: int = None) -> List[dict]:
    """
    Scrape the top N candidate URLs for full article text.
    Uses the rolling cache first -- if a URL was scraped recently, reuse it
    instead of hitting the network again.
    """
    top_n = top_n or settings.scrape_top_n
    scraped: List[dict] = []

    for candidate in candidates[:top_n]:
        url = candidate["url"]
        cached_text = scrape_cache.get(url)
        if cached_text is not None:
            scraped.append(
                {
                    "url": url,
                    "title": candidate.get("title"),
                    "text": cached_text,
                    "snippet": candidate.get("snippet", ""),
                    "from_cache": True,
                }
            )
            continue

        extraction = extract_article_text(url)
        if extraction["success"]:
            scrape_cache.set(url, extraction["text"])
            scraped.append(
                {
                    "url": url,
                    "title": extraction["title"] or candidate.get("title"),
                    "text": extraction["text"],
                    "snippet": candidate.get("snippet", ""),
                    "from_cache": False,
                }
            )
        else:
            # Fall back to the snippet if scraping fails -- still useful,
            # just not as rich.
            scraped.append(
                {
                    "url": url,
                    "title": candidate.get("title"),
                    "text": candidate.get("snippet", ""),
                    "snippet": candidate.get("snippet", ""),
                    "from_cache": False,
                }
            )
    return scraped


def run_search_agent(query: str) -> List[dict]:
    candidates = gather_candidate_urls(query)
    return scrape_top_results(candidates)
