from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date

from app.adapters.grok import GrokAnalyzer
from app.adapters.news import NewsResearcher
from app.adapters.sec import SecResearcher
from app.adapters.website import WebsiteResearcher
from app.config import Settings
from app.models import (
    ActivityItem,
    Citation,
    CompanyProfile,
    EvaluationRequest,
    EvaluationResponse,
    FinancialSnapshot,
    ReportNarrative,
    SourceDocument,
    SourceFact,
    SourceSummary,
)
from app.services.relevance import is_document_accepted, score_document_relevance
from app.services.rendering import render_report
from app.services.scoring import build_projection, compute_scores


class EvaluationService:
    def __init__(
        self,
        settings: Settings,
        website_researcher: WebsiteResearcher,
        sec_researcher: SecResearcher,
        news_researcher: NewsResearcher,
        grok_analyzer: GrokAnalyzer,
    ) -> None:
        self.settings = settings
        self.website_researcher = website_researcher
        self.sec_researcher = sec_researcher
        self.news_researcher = news_researcher
        self.grok_analyzer = grok_analyzer

    async def evaluate(self, request: EvaluationRequest) -> EvaluationResponse:
        normalized_website, domain, website_result = await self.website_researcher.collect(
            request.company_name,
            request.website,
        )
        company_profile = CompanyProfile(
            input_name=request.company_name,
            canonical_name=website_result.canonical_name,
            website=normalized_website,
            domain=domain,
            aliases=website_result.aliases,
            identity_confidence=website_result.identity_confidence,
            summary=website_result.summary,
        )

        sec_result = await self.sec_researcher.collect(company_profile, website_result.ticker_hints)
        if sec_result.ticker and sec_result.cik:
            company_profile.ticker = sec_result.ticker
            company_profile.cik = sec_result.cik
            company_profile.public_company = True
            company_profile.identity_confidence = max(company_profile.identity_confidence, sec_result.confidence)

        news_documents = await self.news_researcher.search(company_profile)
        raw_documents = [*website_result.documents, *sec_result.filing_documents, *news_documents]
        accepted_docs, rejected_docs = self._filter_documents(raw_documents, company_profile)
        analyzed_docs = accepted_docs[: self.settings.max_analyzed_sources]
        facts = await self._analyze_documents(company_profile, analyzed_docs)

        financial_snapshot = sec_result.financial_snapshot if company_profile.public_company else FinancialSnapshot()
        scores, verdict, risks = compute_scores(
            financial_snapshot=financial_snapshot,
            facts=facts,
            identity_confidence=company_profile.identity_confidence,
        )
        projection = build_projection(scores, facts, risks)
        projection_summary = (
            f"Bull {projection.bull_case.projected_return_pct:.1f}%, "
            f"base {projection.base_case.projected_return_pct:.1f}%, "
            f"bear {projection.bear_case.projected_return_pct:.1f}%."
        )
        narrative = await self.grok_analyzer.synthesize_report(
            profile=company_profile,
            scores=scores,
            financial_snapshot=financial_snapshot,
            source_facts=facts,
            risks=risks,
            projection_summary=projection_summary,
        )
        recent_activity, org_changes = self._build_activity_lists(accepted_docs, facts)
        citations = [
            Citation(
                source_id=document.source_id,
                source_type=document.source_type,
                title=document.title,
                url=document.url,
                domain=document.domain,
                published_at=document.published_at,
            )
            for document in accepted_docs
        ]
        summary = SourceSummary(
            total_sources=len(raw_documents),
            accepted_sources=len(accepted_docs),
            rejected_sources=len(rejected_docs),
            by_type=dict(Counter(document.source_type.value for document in raw_documents)),
        )
        body_markdown = self._compose_narrative_markdown(narrative)
        response = EvaluationResponse(
            company_profile=company_profile,
            source_summary=summary,
            financial_snapshot=financial_snapshot,
            recent_activity=recent_activity,
            org_changes=org_changes,
            scores=scores,
            verdict=verdict,
            upside_projection=projection,
            risks=narrative.key_risks or risks,
            citations=citations,
            report_markdown=body_markdown,
            report_html="",
        )
        full_markdown, full_html = render_report(response)
        response.report_markdown = full_markdown
        response.report_html = full_html
        return response

    def _filter_documents(
        self,
        documents: list[SourceDocument],
        profile: CompanyProfile,
    ) -> tuple[list[SourceDocument], list[SourceDocument]]:
        accepted: list[SourceDocument] = []
        rejected: list[SourceDocument] = []
        for document in documents:
            score, reason = score_document_relevance(document, profile)
            document.relevance_score = score
            document.relevance_reason = reason
            if is_document_accepted(score):
                accepted.append(document)
            else:
                rejected.append(document)
        accepted.sort(
            key=lambda item: (
                item.relevance_score,
                item.published_at.timestamp() if item.published_at else 0.0,
            ),
            reverse=True,
        )
        return accepted, rejected

    async def _analyze_documents(
        self,
        profile: CompanyProfile,
        documents: list[SourceDocument],
    ) -> list[SourceFact]:
        if not documents:
            return []
        tasks = [self.grok_analyzer.analyze_source(profile, document) for document in documents]
        facts = await asyncio.gather(*tasks)
        return list(facts)

    def _build_activity_lists(
        self,
        documents: list[SourceDocument],
        facts: list[SourceFact],
    ) -> tuple[list[ActivityItem], list[ActivityItem]]:
        by_id = {document.source_id: document for document in documents}
        activities: list[ActivityItem] = []
        org_changes: list[ActivityItem] = []
        for fact in facts:
            document = by_id.get(fact.source_id)
            if document is None:
                continue
            item = ActivityItem(
                title=document.title,
                date=document.published_at.date() if document.published_at else None,
                category=fact.event_type,
                sentiment=fact.sentiment,
                summary=fact.summary,
                source_ids=[fact.source_id],
            )
            activities.append(item)
            if fact.org_change:
                org_changes.append(item)
        activities.sort(key=lambda item: item.date or date.min, reverse=True)
        org_changes.sort(key=lambda item: item.date or date.min, reverse=True)
        return activities[:10], org_changes[:5]

    def _compose_narrative_markdown(self, narrative: ReportNarrative) -> str:
        thesis = "\n".join(f"- {point}" for point in narrative.investment_thesis) or "- No clear thesis."
        risks = "\n".join(f"- {point}" for point in narrative.key_risks) or "- No specific risks."
        upside = "\n".join(f"- {point}" for point in narrative.upside_drivers) or "- No upside drivers."
        return (
            f"{narrative.executive_summary}\n\n"
            f"### Investment Thesis\n{thesis}\n\n"
            f"### Upside Drivers\n{upside}\n\n"
            f"### Key Risks\n{risks}\n\n"
            f"### Projection Commentary\n{narrative.projection_commentary}"
        )
