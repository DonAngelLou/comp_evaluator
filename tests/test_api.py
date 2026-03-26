from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models import (
    CompanyProfile,
    EvaluationResponse,
    FinancialSnapshot,
    ProjectionScenario,
    ScoreBreakdown,
    SourceSummary,
    UpsideProjection,
    Verdict,
)


class StubService:
    async def evaluate(self, request):
        return EvaluationResponse(
            company_profile=CompanyProfile(
                input_name=request.company_name,
                canonical_name=request.company_name,
                website=request.website,
                domain="example.com",
                identity_confidence=0.9,
            ),
            source_summary=SourceSummary(total_sources=1, accepted_sources=1, rejected_sources=0, by_type={"website": 1}),
            financial_snapshot=FinancialSnapshot(has_financial_data=False),
            recent_activity=[],
            org_changes=[],
            scores=ScoreBreakdown(financial=50, momentum=50, governance=50, valuation_confidence=70, overall=55),
            verdict=Verdict.WATCH,
            upside_projection=UpsideProjection(
                bull_case=ProjectionScenario(name="bull", projected_return_pct=15, assumptions=["test"]),
                base_case=ProjectionScenario(name="base", projected_return_pct=5, assumptions=["test"]),
                bear_case=ProjectionScenario(name="bear", projected_return_pct=-12, assumptions=["test"]),
            ),
            risks=["Test risk"],
            citations=[],
            report_markdown="Test report",
            report_html="<p>Test report</p>",
        )


@pytest.mark.asyncio
async def test_healthz() -> None:
    app = create_app(service=StubService())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root_page() -> None:
    app = create_app(service=StubService())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "Evaluate a company like an investor" in response.text


@pytest.mark.asyncio
async def test_evaluation_endpoint() -> None:
    app = create_app(service=StubService())
    app.state.evaluation_service = StubService()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/evaluations",
            json={"company_name": "Acme Corp", "website": "https://acme.example"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["company_profile"]["canonical_name"] == "Acme Corp"
    assert payload["verdict"] == "watch"
