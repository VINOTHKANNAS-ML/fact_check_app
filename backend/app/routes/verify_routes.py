import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.agents.groq_agent import generate_summary
from app.agents.ingestion_agent import ingest_audio, ingest_image, ingest_text_or_url
from app.agents.search_agent import run_search_agent
from app.agents.trust_scoring_agent import score_to_verdict, score_trust
from app.auth import get_current_user_optional
from app.config import settings
from app.database import get_db
from app.models import User, Verification
from app.rate_limit import rate_limiter
from app.schemas import SourceOut, VerificationHistoryItem, VerifyRequest, VerifyResponse

router = APIRouter(prefix="/verify", tags=["verify"])


def _apply_rate_limit(request: Request, user: User | None) -> None:
    if user is not None:
        rate_limiter.check(f"user:{user.id}", settings.user_rate_limit)
    else:
        client_ip = request.client.host if request.client else "unknown"
        rate_limiter.check(f"guest:{client_ip}", settings.guest_rate_limit)


def _run_pipeline(claim_input: str, user: User | None, db: Session) -> VerifyResponse:
    ingestion = ingest_text_or_url(claim_input)
    claim_text = ingestion["claim_text"]
    direct_source = ingestion["direct_source"]

    corroborating = run_search_agent(claim_text)

    # Combine: the URL the user actually pasted (if any) always leads the
    # list, deduplicated against anything search turned up for the same URL.
    scraped_sources = []
    seen_urls = set()
    if direct_source is not None:
        scraped_sources.append(direct_source)
        seen_urls.add(direct_source["url"])
    for s in corroborating:
        if s["url"] not in seen_urls:
            scraped_sources.append(s)
            seen_urls.add(s["url"])

    trust_score = score_trust(claim_text, scraped_sources)
    verdict = score_to_verdict(trust_score)
    ai_summary = generate_summary(claim_text, scraped_sources)

    # Only a short excerpt/citation is persisted -- full scraped text stays
    # in the ephemeral rolling cache (app/cache.py) and is never written here.
    sources_out = [
        SourceOut(
            url=s["url"],
            title=s.get("title"),
            excerpt=(s.get("text") or "")[:200],
        )
        for s in scraped_sources
    ]

    record = Verification(
        user_id=user.id if user else None,
        query_text=claim_text,
        trust_score=trust_score,
        verdict=verdict,
        ai_summary=ai_summary,
        sources=json.dumps([s.model_dump() for s in sources_out]),
    )
    db.add(record)
    db.commit()

    return VerifyResponse(
        query=claim_text,
        trust_score=trust_score,
        verdict=verdict,
        ai_summary=ai_summary,
        sources=sources_out,
        scraped_sources_used=len(scraped_sources),
    )


@router.post("/text", response_model=VerifyResponse)
def verify_text(
    payload: VerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    _apply_rate_limit(request, user)
    return _run_pipeline(payload.query, user, db)


@router.post("/image", response_model=VerifyResponse)
def verify_image(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    _apply_rate_limit(request, user)
    image_bytes = file.file.read()
    claim_text = ingest_image(image_bytes, file.filename)
    if not claim_text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Couldn't extract a claim from that image. Check that "
                "HUGGINGFACE_API_KEY is set and the image is legible, then try again."
            ),
        )
    return _run_pipeline(claim_text, user, db)


@router.post("/audio", response_model=VerifyResponse)
def verify_audio(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    _apply_rate_limit(request, user)
    audio_bytes = file.file.read()
    claim_text = ingest_audio(audio_bytes, file.filename)
    if not claim_text.strip():
        raise HTTPException(
            status_code=422,
            detail=(
                "Couldn't transcribe that recording. Check that "
                "ASSEMBLYAI_API_KEY is set, the recording has audible speech, "
                "and try again."
            ),
        )
    return _run_pipeline(claim_text, user, db)


@router.get("/history", response_model=list[VerificationHistoryItem])
def get_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_optional),
):
    if user is None:
        return []  # guests have no persisted history
    records = (
        db.query(Verification)
        .filter(Verification.user_id == user.id)
        .order_by(Verification.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        VerificationHistoryItem(
            id=r.id,
            query_text=r.query_text,
            trust_score=r.trust_score,
            verdict=r.verdict,
            ai_summary=r.ai_summary,
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]
