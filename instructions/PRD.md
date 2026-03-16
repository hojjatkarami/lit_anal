# Product Requirements Document (PRD)

## 1. Product Overview

### 1.1 Product Name
Literature Analysis Synthesizer (working name)

### 1.2 Goal
Build an application that analyzes a set of academic papers, reads them carefully, and produces a structured synthesis based on user questions.

### 1.3 Problem Statement
Researchers often maintain large paper libraries in Zotero but struggle to systematically extract evidence, answer focused questions across papers, and keep citations traceable. Manual synthesis is slow and error-prone.

### 1.4 Target Users
- Researchers and graduate students
- Literature review authors
- Analysts synthesizing evidence from scientific PDFs

## 2. Scope

### 2.1 In Scope (MVP)
- Connect to a user-provided Zotero library folder
- Retrieve all available papers (PDFs + metadata when available)
- Parse each PDF and extract text and figures
- Accept a user prompt containing one or more questions
- Use an LLM workflow to answer each question per paper using extracted content
- Preserve references and evidence traceability
- Save outputs in a structured table where each row represents one paper
- Provide a Streamlit interface to run workflows and inspect results
- Store extracted content and synthesis outputs in SQLite
- Capture traces and observability metrics in Langfuse

### 2.2 Out of Scope (for MVP)
- Full reference manager replacement
- Multi-user auth/permission system
- Advanced collaborative editing
- Real-time incremental syncing from Zotero cloud API
- OCR quality optimization beyond Docling defaults

## 3. Success Criteria

### 3.1 Product Success Metrics
- Ingestion success rate: >= 95% of valid PDFs in selected Zotero folder
- Extraction success rate: >= 90% papers with usable extracted text
- End-to-end synthesis completion: >= 90% run success for typical folders (< 500 papers)
- Citation coverage: >= 95% answers include source references when evidence exists
- Median processing time: < 2 minutes per paper for extraction + Q&A generation (hardware-dependent)

### 3.2 User-Perceived Success
- User can ask a multi-question prompt and receive per-paper structured answers in one table
- User can trace each answer to source text/figure references
- User can export or query results for downstream writing

## 4. User Stories

1. As a researcher, I want to point the app to my Zotero folder so papers are discovered automatically.
2. As a researcher, I want all PDFs parsed into text and figures so no key evidence is missed.
3. As a researcher, I want to submit a list of questions and get one structured answer set per paper.
4. As a researcher, I want references attached to each answer so I can verify claims.
5. As a researcher, I want results persisted in a table for filtering, comparison, and export.
6. As an operator, I want observability traces to debug failures and monitor pipeline quality.

## 5. Functional Requirements

### FR-1 Zotero Folder Ingestion
- User provides path to Zotero storage/library folder.
- System recursively scans for supported file types (initially PDF).
- System captures file metadata: file path, filename, hash, modified date.
- System deduplicates by content hash.

### FR-2 Paper Metadata Handling
- System stores available bibliographic metadata when present (title, authors, year, venue, DOI).
- If metadata is missing, system infers basic fields from filename and extracted first-page heuristics.

### FR-3 PDF Extraction (Docling)
- System sends each PDF to Docling pipeline.
- System extracts:
	- Full text (section-aware when possible)
	- Figures and figure captions
	- Page-level location anchors for citations
- System stores extraction artifacts and parsing status.

### FR-4 Prompt and Question Parsing
- UI accepts a prompt with one or multiple explicit questions.
- System normalizes prompt into question list and validation checks (non-empty, max length).

### FR-5 LLM Synthesis Workflow (LangGraph)
- Build LangGraph workflow to process each paper:
	- Retrieve extracted chunks/figures
	- Run question answering for each question
	- Attach evidence snippets and references
	- Produce structured JSON output
- Workflow must handle retries and partial failures per paper without failing the full batch.

### FR-6 Reference and Evidence Preservation
- Each answer includes:
	- Citation metadata (paper id/title/year)
	- Evidence snippets (quoted text)
	- Location anchors (page number, section, figure id when available)
- If evidence is insufficient, answer must explicitly return "Insufficient evidence".

### FR-7 Tabular Output
- Persist results in database table where each row = one paper.
- Columns include paper metadata + one column per question answer + reference/evidence payload.
- UI displays sortable/filterable table and status indicators.

### FR-8 Observability (Langfuse)
- Track pipeline runs, token usage, latency, failures, and step-level traces.
- Correlate each row output to run id and paper id.

### FR-9 Export
- Export synthesis table as CSV/JSON.
- Include references/evidence in export.

## 6. Non-Functional Requirements

### NFR-1 Performance
- Support at least 1,000 PDFs in repository metadata index.
- Batch processing with configurable concurrency.

### NFR-2 Reliability
- Idempotent re-runs (same PDF hash should not duplicate records unless forced refresh).
- Resume interrupted batch jobs from checkpoint.

### NFR-3 Traceability
- Every generated answer must be linked to source evidence artifacts.

### NFR-4 Security and Privacy
- Local-first processing by default.
- Configurable redaction for sensitive text in logs.
- Secrets management for LLM keys and Langfuse keys via environment variables.

### NFR-5 Maintainability
- Modular Python codebase with clear separation: ingestion, extraction, synthesis, persistence, UI.
- Typed interfaces and testable pipeline stages.

## 7. System Architecture (High-Level)

### 7.1 Components
- Streamlit UI: configure folder, prompt, run jobs, inspect table
- Ingestion Service: discover Zotero files and metadata
- Extraction Service (Docling): parse PDFs into text/figures
- Synthesis Orchestrator (LangGraph): run per-paper Q&A workflow
- Database (SQLite): store papers, extraction artifacts, answers, runs
- Observability (Langfuse): monitor and trace workflow execution

### 7.2 Processing Flow
1. User selects Zotero folder and enters prompt/questions.
2. Ingestion indexes PDFs and metadata.
3. Extraction parses each PDF into structured artifacts.
4. LangGraph workflow answers each question per paper using extracted content.
5. Outputs with references are saved to SQLite table.
6. Streamlit renders results and supports export.
7. Langfuse captures traces/metrics across all steps.

## 8. Data Model (Initial)

### 8.1 Core Tables
- `papers`
	- `id` (uuid, pk)
	- `file_hash` (unique)
	- `file_path`
	- `title`
	- `authors` (json)
	- `year`
	- `doi`
	- `created_at`, `updated_at`

- `paper_extractions`
	- `id` (uuid, pk)
	- `paper_id` (fk -> papers)
	- `text_content` (json/chunks)
	- `figures` (json)
	- `extraction_status`
	- `error_message`
	- `created_at`

- `analysis_runs`
	- `id` (uuid, pk)
	- `run_name`
	- `prompt_raw`
	- `questions` (json)
	- `status`
	- `started_at`, `finished_at`
	- `langfuse_trace_id`

- `paper_answers`
	- `id` (uuid, pk)
	- `run_id` (fk -> analysis_runs)
	- `paper_id` (fk -> papers)
	- `answers` (json; keyed by question)
	- `references` (json)
	- `confidence` (optional)
	- `created_at`

### 8.2 View/Table for UI
- `paper_synthesis_view` (materialized view or query)
	- one row per paper per run
	- flattened answer columns + reference summary

## 9. Prompt and Output Contract

### 9.1 Prompt Input Format
- Free-form user prompt, expected to include explicit questions.
- Optional structured mode (future): list of questions.

### 9.2 LLM Output Schema (Per Paper)
```json
{
	"paper_id": "uuid",
	"paper_title": "string",
	"answers": [
		{
			"question": "string",
			"answer": "string",
			"evidence": [
				{
					"quote": "string",
					"page": 4,
					"section": "Methods",
					"figure_id": "fig_2"
				}
			],
			"references": [
				{
					"title": "string",
					"year": 2023,
					"doi": "string"
				}
			],
			"status": "answered | insufficient_evidence"
		}
	]
}
```

## 10. UX Requirements (Streamlit)

### 10.1 Main Screens
- Data Source Screen
	- Zotero folder selector
	- Scan summary (files found, duplicates, parse-ready)
- Analysis Screen
	- Prompt input
	- Run controls (start, stop, resume)
	- Live progress by stage
- Results Screen
	- Table view (one row per paper)
	- Column filters and search
	- Expandable evidence/reference details
	- Export CSV/JSON

### 10.2 UX Constraints
- Show clear per-paper status: indexed, extracted, answered, failed.
- Surface errors with actionable messages.
- Ensure responsiveness for large tables.

## 11. Failure Handling

- If a PDF fails extraction, mark paper as `extraction_failed` and continue batch.
- If LLM step fails for one question, retry with backoff; then mark question failed while preserving other answers.
- If no evidence found for a question, return `insufficient_evidence` not hallucinated output.

## 12. Testing and Validation

### 12.1 Automated Tests
- Unit tests for ingestion, dedup, schema validation, prompt parser.
- Integration tests for Docling extraction on sample PDFs.
- Workflow tests for LangGraph state transitions and retry behavior.
- Database tests for persistence and view correctness.

### 12.2 Evaluation Set
- Curate small gold dataset of papers + known question-answer expectations.
- Measure answer completeness, citation correctness, and evidence grounding.

## 13. Milestones

### Milestone 1: Foundation
- Project scaffolding in Python
- SQLite schema
- Streamlit basic app shell

### Milestone 2: Ingestion + Extraction
- Zotero folder indexing
- Docling extraction pipeline
- Artifact persistence

### Milestone 3: Synthesis Workflow
- LangGraph orchestration
- Q&A generation with evidence and references
- Langfuse tracing integration

### Milestone 4: Results and Export
- Tabular results UI
- CSV/JSON export
- Reliability hardening and retries

### Milestone 5: QA and MVP Release
- End-to-end testing
- Performance tuning
- Documentation and deployment notes

## 14. Risks and Mitigations

- PDF quality variability:
	- Mitigation: fallback extraction modes, quality flags, manual reprocess option.
- Hallucinated answers:
	- Mitigation: strict evidence-required prompting and insufficient-evidence status.
- Large-batch latency:
	- Mitigation: concurrency controls, chunking, resumable jobs.
- Incomplete metadata from Zotero files:
	- Mitigation: heuristic enrichment and optional user correction.

## 15. Open Questions

1. Should Zotero integration remain folder-based only, or add Zotero API sync in v2?
2. Which LLM provider(s) should be supported first?
3. Should figure-level reasoning be optional due to cost/time?
4. Should runs be versioned by prompt template for reproducibility?

## 16. Tech Stack (Confirmed)

- Python
- Zotero (folder-based source)
- Docling (PDF text/figure extraction)
- LangGraph (agent/workflow orchestration)
- Langfuse (observability)
- Streamlit (UI)
- SQLite (database)


