<div align="center">
  <img src="https://raw.githubusercontent.com/Hey-Salad/.github/main/HeySalad%20Logo%20%2B%20Tagline%20Black.svg" alt="HeySalad" height="72" />

  # Salad Scout

  **Ask the web. Get a briefing you can trust.**

  Food intelligence for HeySalad, built on **Tavily** + **Nebius Token Factory** + **Nebius AI Cloud**.
</div>

---

## What it does

Type a question about food, menus or markets. Salad Scout:

1. **Searches the live web** with **Tavily** — real sources, not model memory.
2. **Ranks those sources** with **Nebius Token Factory embeddings** — cosine similarity against your question, so the cricket scores drop out and the trade data floats up.
3. **Writes a cited briefing** with a **Nebius Token Factory** chat model — streamed token by token, every claim carrying a `[1]` you can click.
4. **Files the briefing** to **Nebius AI Cloud Object Storage** — a permanent, shareable JSON record of what was asked, what was read and what was said.

Every stage reports itself in the UI, so you can see exactly which service did what — and how long it took.

## Quick start

```bash
git clone https://github.com/Hey-Salad/NebiusLondonHack.git
cd NebiusLondonHack
./setkeys.sh
```

`setkeys.sh` prompts for your two API keys with the input hidden, writes them
into `.env` without disturbing anything else, and starts the app. Press Enter at
a prompt to keep the key already there. After that, `./run.sh` on its own is
enough.

Then open **http://localhost:8000**.

`run.sh` builds the virtualenv and installs dependencies on first run. To do it by hand:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload
```

## Keys you need

| Variable | Where to get it | Required |
|---|---|---|
| `TAVILY_API_KEY` | [app.tavily.com](https://app.tavily.com) → API Keys | Yes |
| `NEBIUS_API_KEY` | [tokenfactory.nebius.com](https://tokenfactory.nebius.com) → API Keys | Yes |
| `NEBIUS_MODEL` | Any chat model on your account — blank picks one for you | No |
| `NEBIUS_EMBEDDING_MODEL` | Defaults to `BAAI/bge-en-icl` | No |
| `NEBIUS_STORAGE_*` | [console.nebius.com](https://console.nebius.com) → Object Storage | No |

Leave the storage block blank and the app runs happily without it — the archive step just reports itself as skipped.

## How the three services fit together

```
       your question
            │
            ▼
   ┌─────────────────┐
   │  Tavily /search │   live web sources + snippets
   └────────┬────────┘
            ▼
   ┌──────────────────────────────┐
   │  Token Factory /embeddings   │   cosine rerank, keep the best N
   └────────┬─────────────────────┘
            ▼
   ┌──────────────────────────────┐
   │ Token Factory /chat/completions │ streamed, cited briefing
   └────────┬─────────────────────┘
            ▼
   ┌──────────────────────────────┐
   │ Nebius AI Cloud Object Storage │ briefing archived as JSON
   └──────────────────────────────┘
```

Token Factory is OpenAI-compatible, so `app/tokenfactory.py` is plain REST against
`https://api.tokenfactory.nebius.com/v1` — swap `base_url` and it speaks to any
OpenAI-shaped endpoint.

## API

| Endpoint | What it does |
|---|---|
| `GET /` | The app |
| `GET /api/health` | Which integrations are configured |
| `GET /api/models` | Live model list from your Token Factory account |
| `POST /api/research` | Runs the pipeline, streams Server-Sent Events |
| `GET /docs` | OpenAPI docs (FastAPI) |

Stream events: `stage` (pipeline progress), `sources` (ranked sources), `delta`
(answer tokens), `done` (usage + archive location), `error`.

```bash
curl -N -X POST http://localhost:8000/api/research \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is driving harissa demand in UK retail?","max_results":8,"keep":6}'
```

## Deploying to Vercel

The repo is Vercel-ready: `pyproject.toml` points the Python runtime at
`app.main:app`, and streaming is on by default for Python functions, so the
SSE pipeline works unchanged.

1. [Import the repo](https://vercel.com/new) from GitHub.
2. Add the environment variables in **Settings → Environment Variables**:
   `TAVILY_API_KEY` and `NEBIUS_API_KEY` (plus the `NEBIUS_STORAGE_*` block if
   you want the archive step).
3. Deploy. Pushes to `main` redeploy automatically.

## Deploying to Nebius AI Cloud

```bash
docker build -t salad-scout .
docker run -p 8000:8000 --env-file .env salad-scout
```

Push the image to your registry and run it on a Nebius AI Cloud VM or container
service. Inference stays on Token Factory, so the app container needs no GPU —
a small CPU instance is plenty.

## Tests

No API keys needed — the suite stubs both upstreams:

```bash
.venv/bin/python tests/test_pipeline.py
```

It covers the happy path, the embedding-failure fallback (the run degrades to
Tavily's own ordering rather than dying), and the archive step. `tests/stub_upstream.py`
stands in for both APIs if you want to click through the real UI offline:

```bash
.venv/bin/python tests/stub_upstream.py &
TAVILY_API_KEY=stub TAVILY_URL=http://127.0.0.1:8099/search \
NEBIUS_API_KEY=stub NEBIUS_BASE_URL=http://127.0.0.1:8099/v1 \
  .venv/bin/uvicorn app.main:app --port 8000
```

## Layout

```
app/
  config.py        env-backed settings
  tavily.py        Tavily search client
  tokenfactory.py  Nebius Token Factory: models, embeddings, streaming chat
  storage.py       Nebius AI Cloud Object Storage (lazy boto3)
  pipeline.py      the four-stage orchestration
  main.py          FastAPI routes + SSE
web/index.html     the whole front end, HeySalad brand
tests/             offline pipeline test + upstream stub
```

---

<div align="center">
  <strong>HeySalad®</strong> — love your food<br />
  Built for the Nebius London Hack
</div>
