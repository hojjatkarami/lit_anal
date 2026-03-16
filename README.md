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

Install dependencies:

```bash

pip install -e ".[dev]"
export PATH="$HOME/.local/bin:$PATH"
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

Optional:

- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`
- `EXTRACTION_WRITE_MARKDOWN` (default `true`)
- `EXTRACTION_MARKDOWN_DIR` (default `./data/extractions`)

## 2) Database

SQLite is file-based, so no separate server/database creation is required.

Run migrations:

```bash
alembic upgrade head
```

## 3) Run the app

```bash
python3.11 -m streamlit run app/ui/main.py --server.address 0.0.0.0 --server.port 8501
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

- Current MVP uses sequential batch execution with progress indicators.
- PDF extraction is text-only for MVP (no figure reasoning).
- If evidence is missing, model responses should produce `insufficient_evidence`.
