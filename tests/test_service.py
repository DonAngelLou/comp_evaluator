from __future__ import annotations

from datetime import datetime

import pytest

from app.config import Settings
from app.models import (
    CompanyProfile,
    EvaluationRequest,
    EventType,
    FinancialSnapshot,
    ReportNarrative,
    SecLookupResult,
    Sentiment,
    SourceDocument,
    SourceFact,
    SourceType,
    WebsiteResearchResult,
)
from app.services.evaluation import EvaluationService


class FakeWebsiteResearcher:
    async def collect(self, company_name: str, website: str):
        return (
            "https://acme.com",
            "acme.com",
            WebsiteResearchResult(
                canonical_name="Acme Corporation",
                aliases=["Acme Corp"],
                ticker_hints=["ACME"],
                summary="Acme makes industrial automation software.",
                identity_confidence=0.72,
                documents=[
                    SourceDocument(
                        source_id="website-home",
                        source_type=SourceType.WEBSITE,
                        title="Acme Corporation | Industrial Automation",
                        url="https://acme.com",
                        domain="acme.com",
                        summary="Acme provides automation software and services.",
                        content="Acme provides automation software and investor updates.",
                    )
                ],
            ),
        )


class FakeSecResearcher:
    async def collect(self, profile: CompanyProfile, ticker_hints: list[str]) -> SecLookupResult:
        return SecLookupResult(
            ticker="ACME",
            cik="0000123456",
            confidence=0.92,
            financial_snapshot=FinancialSnapshot(
                has_financial_data=True,
                latest_revenue=1_000_000_000,
                revenue_growth_yoy=0.18,
                latest_net_income=120_000_000,
                net_income_margin=0.12,
                current_ratio=1.8,
            ),
            filing_documents=[
                SourceDocument(
                    source_id="sec-10q-0",
                    source_type=SourceType.SEC_FILING,
                    title="10-Q filing",
                    url="https://sec.gov/acme10q",
                    domain="sec.gov",
                    published_at=datetime(2026, 2, 10),
                    summary="Quarterly revenue growth accelerated and margins expanded.",
                    content="Acme reported growth and higher margins in the latest quarter.",
                )
            ],
        )


class FakeNewsResearcher:
    async def search(self, profile: CompanyProfile):
        return [
            SourceDocument(
                source_id="news-0",
                source_type=SourceType.NEWS,
                title="Acme Corporation expands enterprise partnership",
                url="https://news.example/acme-partnership",
                domain="news.example",
                published_at=datetime(2026, 3, 1),
                summary="Acme signed a large enterprise partnership.",
                content="The company announced a new enterprise partnership.",
            ),
            SourceDocument(
                source_id="news-1",
                source_type=SourceType.NEWS,
                title="Acme Bank opens new branch",
                url="https://news.example/acme-bank",
                domain="news.example",
                published_at=datetime(2026, 3, 2),
                summary="Acme Bank expanded retail presence.",
                content="This article is about a bank, not the target company.",
            ),
        ]


class FakeGrokAnalyzer:
    async def analyze_source(self, profile: CompanyProfile, document: SourceDocument) -> SourceFact:
        text = f"{document.title} {document.summary}".lower()
        is_partnership = "partnership" in text
        return SourceFact(
            source_id=document.source_id,
            summary=document.summary,
            sentiment=Sentiment.POSITIVE if ("growth" in text or is_partnership) else Sentiment.NEUTRAL,
            event_type=EventType.PARTNERSHIP if is_partnership else EventType.FINANCIAL,
            key_points=[document.title],
            org_change=False,
            financial_signal=Sentiment.POSITIVE if "growth" in text else Sentiment.NEUTRAL,
            source_confidence=0.8,
        )

    async def synthesize_report(self, profile, scores, financial_snapshot, source_facts, risks, projection_summary):
        return ReportNarrative(
            executive_summary="Acme shows improving execution and a reasonable evidence base.",
            investment_thesis=["Revenue and partnership momentum are positive."],
            key_risks=risks,
            upside_drivers=["Recent partnership expansion supports demand."],
            projection_commentary=projection_summary,
        )


@pytest.mark.asyncio
async def test_service_filters_same_name_news_and_returns_report() -> None:
    service = EvaluationService(
        settings=Settings(),
        website_researcher=FakeWebsiteResearcher(),
        sec_researcher=FakeSecResearcher(),
        news_researcher=FakeNewsResearcher(),
        grok_analyzer=FakeGrokAnalyzer(),
    )
    response = await service.evaluate(EvaluationRequest(company_name="Acme Corporation", website="https://acme.com"))
    citation_ids = {citation.source_id for citation in response.citations}
    assert "news-0" in citation_ids
    assert "news-1" not in citation_ids
    assert response.company_profile.ticker == "ACME"
    assert response.financial_snapshot.has_financial_data is True
    assert response.verdict.value in {"watch", "good_investment_now"}


class PrivateSecResearcher:
    async def collect(self, profile: CompanyProfile, ticker_hints: list[str]) -> SecLookupResult:
        return SecLookupResult()


class PrivateGrokAnalyzer(FakeGrokAnalyzer):
    async def synthesize_report(self, profile, scores, financial_snapshot, source_facts, risks, projection_summary):
        return ReportNarrative(
            executive_summary="Evidence exists, but without filings the result should stay cautious.",
            investment_thesis=["Website and news signals are useful but incomplete."],
            key_risks=risks,
            upside_drivers=["Customer-facing activity is still visible."],
            projection_commentary=projection_summary,
        )


@pytest.mark.asyncio
async def test_service_private_company_falls_back_to_watch() -> None:
    service = EvaluationService(
        settings=Settings(),
        website_researcher=FakeWebsiteResearcher(),
        sec_researcher=PrivateSecResearcher(),
        news_researcher=FakeNewsResearcher(),
        grok_analyzer=PrivateGrokAnalyzer(),
    )
    response = await service.evaluate(EvaluationRequest(company_name="Acme Corporation", website="https://acme.com"))
    assert response.company_profile.public_company is False
    assert response.verdict == "watch"
    assert "Financial filings are missing" in " ".join(response.risks)
