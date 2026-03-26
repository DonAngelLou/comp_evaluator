# Investment Evaluation Report

## Overview

This project is a FastAPI-based company research application that generates an AI-assisted investment evaluation report from a company name and website.

The goal is not just to summarize a company. The goal is to build a safer research pipeline that:

- retrieves current public information
- checks whether the information is actually about the target company
- uses Grok as an analysis layer instead of a source of truth
- produces a grounded report with citations, risks, and upside scenarios

The app includes both:

- a browser-based UI for entering a company name and website
- a JSON API for programmatic use

## What the app does

Given:

- `company_name`
- `website`

The system:

1. normalizes the website and extracts company identity clues from the company’s own domain
2. attempts to match the company to SEC public-company records
3. retrieves evidence from the company website, SEC EDGAR, and recent news
4. filters out irrelevant sources, including same-name collisions
5. sends accepted source content to Grok for structured extraction and synthesis
6. computes deterministic investment scores and 12-month bull/base/bear scenarios
7. returns a full evaluation report in JSON, Markdown, and HTML

## Main features

- FastAPI backend with typed request/response models
- Modern HTML/CSS frontend for browser-based demo use
- Website-first identity resolution
- SEC EDGAR support for public-company financial data
- Google News RSS integration for recent activity
- Relevance scoring to reduce wrong-company contamination
- Grok structured-output integration
- Graceful fallback if Grok is unavailable or the API key is invalid
- Deterministic scoring for financial strength, momentum, governance, and confidence
- Rendered in-page report plus raw structured API output

## Why this design

This project is built around a retrieval-first architecture.

Instead of asking the model to “know” current company facts, the app fetches current public evidence first and only then uses AI to interpret that evidence. That reduces hallucination risk and makes the result easier to explain and defend.

Core design principles:

- retrieval before generation
- domain and company identity verification first
- structured model outputs instead of free-form responses
- deterministic scoring for the final stance
- graceful degradation when data is incomplete

## Architecture

### API and app entrypoint

- `app/main.py`
  - serves the browser UI
  - exposes the health check and evaluation API

### Source adapters

- `app/adapters/website.py`
  - fetches the provided company website
  - extracts related pages and identity clues
- `app/adapters/sec.py`
  - looks up ticker and CIK
  - fetches filings and company facts from SEC EDGAR
- `app/adapters/news.py`
  - fetches recent news from Google News RSS
- `app/adapters/grok.py`
  - sends source-grounded prompts to Grok
  - parses structured responses

### Services

- `app/services/evaluation.py`
  - orchestrates the full workflow
- `app/services/relevance.py`
  - scores and filters source relevance
- `app/services/scoring.py`
  - computes investment scores and projection ranges
- `app/services/rendering.py`
  - generates Markdown and HTML report output

## Tech stack

- Python
- FastAPI
- Pydantic
- httpx
- BeautifulSoup
- feedparser
- Markdown
- xAI / Grok API

## Browser UI

The root route serves a browser page where the user can:

- enter a company name
- enter the official company website
- submit the evaluation request
- read the resulting report on the same page

The frontend shows:

- company snapshot
- verdict and scores
- recent activity
- projection cases
- risks
- citations
- full rendered report

## API endpoints

### `GET /`

Loads the browser UI.

### `GET /healthz`

Returns a basic health response.

### `POST /api/v1/evaluations`

Example request:

```json
{
  "company_name": "NVIDIA Corporation",
  "website": "https://www.nvidia.com"
}
```

The response includes:

- `company_profile`
- `source_summary`
- `financial_snapshot`
- `recent_activity`
- `org_changes`
- `scores`
- `verdict`
- `upside_projection`
- `risks`
- `citations`
- `report_markdown`
- `report_html`

## Quick Start

### 1. Create a virtual environment

```bash
python -m venv .venv
```

### 2. Activate it

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -e .[dev]
```

### 4. Configure environment variables

```bash
copy .env.example .env
```

Important variables:

- `XAI_API_KEY`
- `XAI_MODEL`
- `SEC_USER_AGENT`

### 5. Start the app

```bash
uvicorn app.main:app --reload
```

### 6. Open it

- Browser UI: `http://127.0.0.1:8000/`
- Swagger docs: `http://127.0.0.1:8000/docs`

## Example API call

PowerShell:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/evaluations" `
  -ContentType "application/json" `
  -Body '{"company_name":"NVIDIA Corporation","website":"https://www.nvidia.com"}'
```

## Anti-hallucination and relevance safeguards

This project explicitly tries to reduce hallucinations and wrong-company results.

Safeguards include:

- website-first identity resolution
- SEC verification for public companies
- relevance scoring based on domain, name overlap, and ticker/company confirmation
- rejection of low-confidence sources
- source-grounded model prompts
- deterministic scoring outside the model
- fallback heuristics if Grok fails

## Limitations

This is a solid v1, but not a full production investment platform.

Current limitations:

- private-company financial analysis is weaker than public-company analysis
- news ingestion is based on RSS rather than a richer news provider
- entity resolution is still heuristic
- no database or persistent history yet
- scoring is simplified and not a full valuation framework

## Testing

Run the test suite with:

```bash
.\.venv\Scripts\python.exe -m pytest
```

The tests cover:

- API routing
- browser UI route availability
- same-name filtering behavior
- private-company fallback behavior

## Notes

- If `XAI_API_KEY` is missing, the app still runs using heuristic fallback logic.
- If `XAI_API_KEY` is invalid, the app falls back instead of crashing.
- Current facts are retrieved from public sources; Grok is used for structured interpretation, not as the source of truth.
