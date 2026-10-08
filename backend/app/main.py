from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routes import auth_routes, verify_routes

# Creates tables on startup if they don't exist (fine for SQLite/demo;
# for Postgres/Neon in production, prefer real migrations e.g. Alembic).
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fake News Verifier Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your actual frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(verify_routes.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "fake-news-verifier-agent-api"}


@app.get("/health")
def health():
    return {"status": "healthy"}
