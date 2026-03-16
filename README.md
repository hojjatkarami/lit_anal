# Literature Analysis Synthesizer

MVP application for running question-driven literature synthesis over papers in a Zotero library.

## Stack

- Python 3.11+
- Streamlit UI
- SQLite + SQLAlchemy + Alembic
- Zotero API via `pyzotero`
- PDF extraction via `docling`
- Per-paper QA orchestration via `langgraph`
- LLM provider via OpenRouter (OpenAI-compatible API)
- Observability via Langfuse

## 1) Setup

Install `uv` if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

Create and activate a virtual environment using `uv`, then install all dependencies:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Create environment file:

```bash
cp .env.example .env
```

Fill required values in `.env`:

- `DATABASE_URL`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_MAX_CONCURRENT_REQUESTS` (default `10`, max `10`)
- `ZOTERO_API_KEY`
- `ZOTERO_LIBRARY_ID`
- `ZOTERO_LIBRARY_TYPE`
- `ZOTERO_MAX_CONCURRENT_REQUESTS` (default `4`)

Optional:

- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`
- `EXTRACTION_DIR` (default `./data/extractions`) — base directory; format files are written to `{EXTRACTION_DIR}/markdown/`, `html/`, `json/`, `doctags/`
- `EXTRACTION_WRITE_MARKDOWN` (default `true`)
- `EXTRACTION_WRITE_HTML` (default `true`)
- `EXTRACTION_WRITE_JSON` (default `true`)
- `EXTRACTION_WRITE_DOCTAGS` (default `true`)

## 2) Database

SQLite is file-based, so no separate server/database creation is required.

Run migrations:

```bash
alembic upgrade head
```

## 3) Run the app

```bash
streamlit run app/ui/main.py
```

## 4) Workflow

1. Open **Data Source** page and provide Zotero credentials.
2. Run **Scan & Index** to pull metadata and PDFs into local storage.
3. Open **Analysis** page, enter one or more research questions, and run synthesis.
4. Open **Results** page to inspect outputs and export CSV/JSON.

## Tests

Run:

```bash
pytest -q
```

## Notes

- Zotero indexing fetches attachments and downloads PDFs concurrently; database writes remain serialized.
- PDF extraction is text-only for MVP (no figure reasoning).
- If evidence is missing, model responses should produce `insufficient_evidence`.
