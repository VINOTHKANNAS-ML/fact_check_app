"""
Shared article-scraping logic. Originally built for a URL-paste tab; reused
by SearchAgent so search results get scraped for full text, not just snippets.
"""

import requests
from bs4 import BeautifulSoup

from app.config import settings

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FactCheckBot/1.0; "
        "+https://example.com/bot-info)"
    )
}

# Tags that are never part of the actual article body
NOISE_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "iframe", "noscript"]


def extract_article_text(url: str, max_chars: int = 6000) -> dict:
    """
    Fetches a URL and extracts the main readable text.
    Returns {"url", "title", "text", "success", "error"}.
    Keeps only a bounded amount of text (max_chars) -- this is evidence
    gathering for grounding the AI summary, not full reproduction/storage.
    """
    result = {"url": url, "title": None, "text": "", "success": False, "error": None}
    try:
        resp = requests.get(
            url, headers=HEADERS, timeout=settings.scrape_timeout_seconds
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        result["error"] = str(exc)
        return result

    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception:
        soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(NOISE_TAGS):
        tag.decompose()

    title_tag = soup.find("title")
    result["title"] = title_tag.get_text(strip=True) if title_tag else None

    # Prefer <article>, fall back to largest text block in <body>
    article = soup.find("article")
    if article is not None:
        text = article.get_text(separator=" ", strip=True)
    else:
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)

    text = " ".join(text.split())  # collapse whitespace
    if not text or len(text) < 150:
        # Too short to be real article content -- likely a JS-rendered shell
        # page (common on aggregators like MSN) that requests/BeautifulSoup
        # can't execute. Treat as a failed extraction so the caller falls
        # back to a search-based query instead of an empty/near-empty claim.
        result["error"] = "No substantial extractable article text found"
        return result

    result["text"] = text[:max_chars]
    result["success"] = True
    return result
