# Investment Evaluation Report API

FastAPI service that evaluates a company as a potential investment using public data, deterministic scoring, and Grok for structured extraction and report synthesis.

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
copy .env.example .env
uvicorn app.main:app --reload
```

## API

### `GET /healthz`

Returns a simple service health response.

### `POST /api/v1/evaluations`

```json
{
  "company_name": "NVIDIA Corporation",
  "website": "https://www.nvidia.com"
}
```

The response includes company identity, citations, financial snapshot, recent activity, a verdict, and rendered Markdown/HTML.

## Notes

- If `XAI_API_KEY` is not set, the app falls back to deterministic heuristics so the API still runs locally.
- Current facts come from retrieved sources, not from Grok's memory.
