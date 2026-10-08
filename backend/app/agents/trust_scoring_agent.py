"""
TrustScoringAgent: computes a 0-100 trust score for the claim based on the
richer scraped content (not just snippets), source count, and source variety.

This is a transparent, explainable heuristic scorer -- swap in something more
sophisticated later if you want, but keep it explainable.
"""

from typing import List
from urllib.parse import urlparse

REPUTABLE_DOMAINS = {
    "wikipedia.org",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "npr.org",
    "nature.com",
    "who.int",
    "un.org",
    # Major Indian national outlets and wire services
    "ndtv.com",
    "thehindu.com",
    "indianexpress.com",
    "hindustantimes.com",
    "timesofindia.indiatimes.com",
    "ptinews.com",
    "aninews.in",
    "pib.gov.in",
    "gov.in",
    "livemint.com",
    "business-standard.com",
    "moneycontrol.com",
    # International wires / broadcasters
    "cnn.com",
    "theguardian.com",
    "aljazeera.com",
    "bloomberg.com",
    "wsj.com",
    "nytimes.com",
}

# Aggregator/syndication sites -- they republish other outlets' content, so
# they shouldn't count as an independent corroborating source on their own.
AGGREGATOR_DOMAINS = {"msn.com", "news.google.com", "yahoo.com"}


def _domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc[4:] if netloc.startswith("www.") else netloc
    except Exception:
        return ""


def score_trust(query: str, scraped_sources: List[dict]) -> float:
    if not scraped_sources:
        return 10.0  # very low confidence -- nothing corroborating the claim

    # Sources that actually have body text vs. empty (failed-scrape) entries
    usable_sources = [s for s in scraped_sources if s.get("text")]
    if not usable_sources:
        return 15.0  # a source was cited but nothing could be read from it

    score = 35.0  # baseline once we have at least one *usable* source

    unique_domains = {_domain(s["url"]) for s in usable_sources}
    non_aggregator_domains = {
        d for d in unique_domains if not any(agg in d for agg in AGGREGATOR_DOMAINS)
    }

    # Corroboration: more independent, non-aggregator domains = more confidence
    score += min(len(non_aggregator_domains) * 12, 36)

    # A single hit from a well-known, reputable outlet is itself strong
    # evidence -- don't require multiple sources to reward that.
    reputable_hits = sum(
        1 for d in unique_domains if any(rep in d for rep in REPUTABLE_DOMAINS)
    )
    score += min(reputable_hits * 15, 30)

    # Sources with substantial scraped body text (not just a snippet
    # fallback) count more -- deeper evidence, not just a headline match.
    fully_scraped = sum(1 for s in usable_sources if len(s.get("text", "")) > 500)
    score += min(fully_scraped * 4, 12)

    return round(min(score, 100.0), 1)


def score_to_verdict(score: float) -> str:
    """
    Maps the 0-100 trust score to a human-readable verdict label.
    Thresholds are intentionally conservative -- a low source count should
    never produce a confident "Real" or "Fake" verdict.
    """
    if score >= 80:
        return "Real"
    if score >= 60:
        return "Likely Real"
    if score >= 35:
        return "Unverified"
    if score >= 15:
        return "Likely Fake"
    return "Fake"
