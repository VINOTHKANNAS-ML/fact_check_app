# Fake News Verifier Agent

Full-stack fake news / claim verification tool: FastAPI + JWT auth (with
guest mode) on the backend, React (Vite) on the frontend. Given a claim,
headline, or URL, it scrapes top matching articles, computes a 0-100 trust
score, maps that to a plain-language verdict (Real / Likely Real /
Unverified / Likely Fake / Fake), and generates an AI analysis grounded in
the scraped evidence.

## Project layout

```
factcheck-app/
  backend/
    app/
      agents/
        url_extractor.py       # BeautifulSoup article scraper (shared by URL tab + SearchAgent)
        search_agent.py        # SerpAPI/NewsAPI/DuckDuckGo/Wikipedia + scraping top N
        trust_scoring_agent.py # Heuristic 0-100 trust score
        groq_agent.py          # Groq AI Analysis summary, grounded in scraped text
        ingestion_agent.py     # Normalizes text/URL/image/audio input
      routes/
        auth_routes.py         # register/login (JWT)
        verify_routes.py       # /verify/text, /verify/image, /verify/audio, /verify/history
      auth.py                  # bcrypt hashing + JWT create/decode + optional/required user deps
      cache.py                 # Rolling FIFO cache (Option B) for scraped text -- never persisted
      config.py                # Settings loaded from .env
      database.py               
      models.py                # User, Verification (only short excerpts stored)
      schemas.py
      main.py                  # FastAPI app
    requirements.txt
    .env.example
  frontend/
    src/
      App.jsx                  # login/register + guest verify UI + history
      api.js
      main.jsx
      styles.css
    package.json
    vite.config.js
    index.html
```

## Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # then fill in your real API keys
uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive API docs.

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`. Set `VITE_API_BASE` in a `.env` file in
`frontend/` if your backend isn't on `localhost:8000`.

## How the pieces from the plan map to code

- **Guest mode**: `get_current_user_optional` in `auth.py` lets `/verify/*`
  routes work with or without a JWT. `rate_limit.py` applies a tighter limit
  to guests (by IP) than logged-in users (by user id) — see `GUEST_RATE_LIMIT`
  / `USER_RATE_LIMIT` in `.env`.
- **Scraping**: `search_agent.py` calls `gather_candidate_urls()` then
  `scrape_top_results()`, which reuses `url_extractor.py`'s BeautifulSoup
  logic to pull full article text for the top `SCRAPE_TOP_N` (default 3)
  results, instead of just search snippets.
- **Rolling cache**: `cache.py` implements the FIFO cache you asked for
  (Option B) — `OrderedDict` capped at `SCRAPE_CACHE_SIZE` (default 3),
  oldest entry evicted automatically. It's in-memory only, never written to
  disk or the database, and resets on every restart/redeploy by design.
- **What actually gets saved**: `verify_routes.py` only ever writes a short
  200-char excerpt + citation URL into the `Verification.sources` field —
  the full scraped text lives only in the rolling cache.
- **Trust scoring**: `trust_scoring_agent.py` is a transparent heuristic
  (source count, domain diversity, reputable-domain bonus, how many sources
  were fully scraped vs. fallback snippet) — swap in something fancier later
  if you want, but keep it explainable to users.
- **AI summary**: `groq_agent.py` builds a context block from the scraped
  excerpts and asks Groq (`llama-3.1-8b-instant`) to analyze the claim
  against *only* that evidence, citing sources by number.

## Free hosting (per the plan)

| Layer | Service |
|---|---|
| Frontend | Render Static Site |
| Backend | Render Web Service |
| Database | SQLite for demo (resets on redeploy) → swap to **Neon.tech** Postgres for persistence: just change `DATABASE_URL` in `.env`, `psycopg2-binary` is already in requirements.txt |
| Search | SerpAPI, NewsAPI, DuckDuckGo, Wikipedia (all free tier) |
| AI summary | Groq (free tier) |
| Image/audio | HuggingFace, AssemblyAI (free tier) |

## Notes / things to harden before real production use

- `SessionLocal`/table creation uses `Base.metadata.create_all()` for
  simplicity — switch to Alembic migrations once the schema is stable.
- The in-memory rate limiter (`rate_limit.py`) resets if the process
  restarts and doesn't share state across multiple workers/instances — fine
  for a single free-tier instance, swap for Redis if you scale out.
- CORS is wide open (`allow_origins=["*"]`) — lock this down to your actual
  frontend domain before going live.
- Audio transcription polls AssemblyAI once rather than until completion —
  fine for short clips, add proper polling/webhooks for longer audio.
