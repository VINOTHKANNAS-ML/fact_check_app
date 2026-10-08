"""
Calls Groq to generate the AI Analysis summary, now grounded in the full
scraped article text instead of just the raw claim.
"""

from typing import List

from groq import Groq

from app.config import settings

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def build_context_block(scraped_sources: List[dict], max_chars_per_source: int = 1500) -> str:
    blocks = []
    for i, source in enumerate(scraped_sources, start=1):
        text = source.get("text", "")[:max_chars_per_source]
        blocks.append(f"Source {i} ({source.get('url')}):\n{text}")
    return "\n\n".join(blocks)


def generate_summary(query: str, scraped_sources: List[dict]) -> str:
    if not settings.groq_api_key:
        return (
            "AI summary unavailable (GROQ_API_KEY not configured). "
            f"Found {len(scraped_sources)} source(s) related to the claim."
        )

    context = build_context_block(scraped_sources)
    system_prompt = (
        "You are a fact-checking assistant. Given a claim and excerpts from "
        "real articles found about it, write a concise, neutral analysis of "
        "whether the claim appears supported, contradicted, or unclear based "
        "ONLY on the provided source excerpts. Do not invent facts not present "
        "in the sources. Cite sources by number, e.g. (Source 1). Keep it under "
        "150 words."
    )
    user_prompt = f"Claim: {query}\n\nSource excerpts:\n{context}"

    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001
        return f"AI summary generation failed: {exc}"
