"""
IngestionAgent: takes raw user input (plain text, a URL, an image, or audio)
and normalizes it into clean claim text that SearchAgent can work with.
"""

import time

import re

import requests

from app.agents.url_extractor import extract_article_text
from app.config import settings


def _looks_like_url(value: str) -> bool:
    return value.strip().startswith(("http://", "https://"))


def _fallback_query_from_url(url: str) -> str:
    """
    When a URL can't be scraped (blocked, JS-rendered, paywalled), searching
    on the raw URL string returns nothing useful. Instead, pull readable
    words out of the URL's path slug -- most news URLs encode the headline
    there, e.g. /brics-not-against-anyone-pm-modi-s-big-message-to-west/.
    """
    from urllib.parse import urlparse

    path = urlparse(url).path
    # Take the longest hyphenated/underscored path segment -- that's almost
    # always the actual headline slug, not an id or category folder.
    segments = [seg for seg in path.split("/") if seg]
    slug = max(segments, key=len) if segments else ""
    words = re.split(r"[-_]+", slug)
    # Drop pure-alphanumeric id fragments (e.g. "ar-AA2c4FEn") and numbers
    words = [w for w in words if len(w) > 2 and not re.fullmatch(r"[a-zA-Z0-9]{6,}", w)]
    query = " ".join(words).strip()
    return query or url


def ingest_text_or_url(raw_input: str) -> dict:
    """
    Returns {"claim_text": str, "direct_source": dict | None}.

    For a URL: scrapes it directly so it's ALWAYS used as evidence (even if
    it fails to scrape, it's still returned so the caller can surface it),
    and uses its title as the search query for corroborating sources --
    instead of the old approach of re-searching on a generated text blob,
    which often returned zero useful matches.
    """
    raw_input = raw_input.strip()
    if _looks_like_url(raw_input):
        extraction = extract_article_text(raw_input, max_chars=3000)
        if extraction["success"]:
            title = extraction["title"] or raw_input
            direct_source = {
                "url": raw_input,
                "title": title,
                "text": extraction["text"],
                "snippet": extraction["text"][:200],
                "from_cache": False,
            }
            # Use the title (not the full body) as the search query --
            # short, specific queries return far better corroborating results.
            return {"claim_text": title, "direct_source": direct_source}

        # Scraping failed (blocked, JS-rendered, paywalled, etc.) -- still
        # surface the URL itself as a source (with no body text) so the user
        # sees it was considered, and fall back to a search query built from
        # the URL's slug words instead of the raw URL (which search engines
        # can't do much with).
        fallback_query = _fallback_query_from_url(raw_input)
        direct_source = {
            "url": raw_input,
            "title": fallback_query if fallback_query != raw_input else raw_input,
            "text": "",
            "snippet": "",
            "from_cache": False,
        }
        return {"claim_text": fallback_query, "direct_source": direct_source}

    return {"claim_text": raw_input, "direct_source": None}


def ingest_image(image_bytes: bytes, filename: str) -> str:
    """
    Sends the image to a HuggingFace image-captioning / OCR model and returns
    extracted text/description to use as the claim.
    """
    if not settings.huggingface_api_key:
        return ""
    try:
        resp = requests.post(
            "https://api-inference.huggingface.co/models/nlpconnect/vit-gpt2-image-captioning",
            headers={"Authorization": f"Bearer {settings.huggingface_api_key}"},
            data=image_bytes,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        if isinstance(result, list) and result:
            return result[0].get("generated_text", "")
        return ""
    except requests.RequestException:
        return ""


def ingest_audio(audio_bytes: bytes, filename: str) -> str:
    """
    Sends audio to AssemblyAI for transcription and returns the transcript
    text to use as the claim. Polls until the transcript is actually done
    (AssemblyAI transcribes asynchronously -- a single immediate check
    almost always catches it mid-"processing" and returns nothing).
    """
    if not settings.assemblyai_api_key:
        return ""
    headers = {"authorization": settings.assemblyai_api_key}
    try:
        upload_resp = requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=audio_bytes,
            timeout=60,
        )
        upload_resp.raise_for_status()
        audio_url = upload_resp.json()["upload_url"]

        transcript_resp = requests.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=headers,
            json={"audio_url": audio_url},
            timeout=30,
        )
        transcript_resp.raise_for_status()
        transcript_id = transcript_resp.json()["id"]

        poll_url = f"https://api.assemblyai.com/v2/transcript/{transcript_id}"
        # Poll every 2s for up to ~60s -- plenty for a short claim recording.
        for _ in range(30):
            time.sleep(2)
            poll_resp = requests.get(poll_url, headers=headers, timeout=30)
            poll_resp.raise_for_status()
            data = poll_resp.json()
            status = data.get("status")
            if status == "completed":
                return data.get("text", "") or ""
            if status == "error":
                return ""
        return ""  # timed out waiting -- caller falls back to a placeholder
    except requests.RequestException:
        return ""
