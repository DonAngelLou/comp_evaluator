from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.config import Settings
from app.models import (
    CompanyProfile,
    EventType,
    FinancialSnapshot,
    ReportNarrative,
    ScoreBreakdown,
    Sentiment,
    SourceDocument,
    SourceFact,
)
from app.utils import clamp


class GrokAnalyzer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = (
            AsyncOpenAI(api_key=settings.xai_api_key, base_url="https://api.x.ai/v1")
            if settings.xai_api_key
            else None
        )

    async def analyze_source(self, profile: CompanyProfile, document: SourceDocument) -> SourceFact:
        if self._client is None:
            return self._fallback_source_fact(document)

        system_prompt = (
            "You are a financial research assistant. Only use the provided source text. "
            "Do not infer facts not present in the source. Summaries must stay source-grounded."
        )
        user_prompt = (
            f"Company: {profile.canonical_name}\n"
            f"Ticker: {profile.ticker or 'unknown'}\n"
            f"Source title: {document.title}\n"
            f"Source type: {document.source_type.value}\n"
            f"Source URL: {document.url}\n"
            f"Source summary:\n{document.summary}\n\n"
            f"Source content:\n{document.content[:3000]}"
        )
        try:
            return await self._parse_structured(
                schema_name="source_fact",
                model=SourceFact,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception:
            return self._fallback_source_fact(document)

    async def synthesize_report(
        self,
        profile: CompanyProfile,
        scores: ScoreBreakdown,
        financial_snapshot: FinancialSnapshot,
        source_facts: list[SourceFact],
        risks: list[str],
        projection_summary: str,
    ) -> ReportNarrative:
        if self._client is None:
            return self._fallback_narrative(profile, scores, source_facts, risks, projection_summary)

        fact_block = "\n".join(
            f"- {fact.source_id}: {fact.summary} | event={fact.event_type.value} | sentiment={fact.sentiment.value}"
            for fact in source_facts
        )
        user_prompt = (
            f"Company: {profile.canonical_name}\n"
            f"Identity confidence: {profile.identity_confidence:.2f}\n"
            f"Financial score: {scores.financial:.1f}\n"
            f"Momentum score: {scores.momentum:.1f}\n"
            f"Governance score: {scores.governance:.1f}\n"
            f"Overall score: {scores.overall:.1f}\n"
            f"Latest revenue: {financial_snapshot.latest_revenue}\n"
            f"Latest net income: {financial_snapshot.latest_net_income}\n"
            f"Known risks: {json.dumps(risks)}\n"
            f"Projection summary: {projection_summary}\n"
            f"Source-grounded facts:\n{fact_block}"
        )
        system_prompt = (
            "Write a concise investment report narrative using only the supplied facts. "
            "Do not introduce uncited claims, valuation metrics, or market data not present in the context."
        )
        try:
            return await self._parse_structured(
                schema_name="report_narrative",
                model=ReportNarrative,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception:
            return self._fallback_narrative(profile, scores, source_facts, risks, projection_summary)

    async def _parse_structured(self, schema_name: str, model, messages: list[dict[str, str]]):
        completion = await self._client.chat.completions.create(
            model=self.settings.xai_model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": model.model_json_schema(),
                    "strict": True,
                },
            },
        )
        content = completion.choices[0].message.content or "{}"
        return model.model_validate_json(content)

    def _fallback_source_fact(self, document: SourceDocument) -> SourceFact:
        text = f"{document.title} {document.summary}".lower()
        event_type = EventType.OTHER
        sentiment = Sentiment.NEUTRAL
        org_change = False
        if any(keyword in text for keyword in ("ceo", "cfo", "chief", "board", "director")):
            event_type = EventType.LEADERSHIP
            org_change = True
        elif any(keyword in text for keyword in ("revenue", "earnings", "profit", "guidance", "quarter")):
            event_type = EventType.FINANCIAL
        elif any(keyword in text for keyword in ("launch", "product", "platform")):
            event_type = EventType.PRODUCT
        elif any(keyword in text for keyword in ("partner", "partnership", "agreement")):
            event_type = EventType.PARTNERSHIP
        elif any(keyword in text for keyword in ("lawsuit", "probe", "investigation")):
            event_type = EventType.LEGAL

        if any(keyword in text for keyword in ("beat", "growth", "expands", "raises", "wins")):
            sentiment = Sentiment.POSITIVE
        elif any(keyword in text for keyword in ("miss", "cuts", "decline", "loss", "resigns", "lawsuit")):
            sentiment = Sentiment.NEGATIVE

        return SourceFact(
            source_id=document.source_id,
            summary=document.summary[:240] or document.title,
            event_type=event_type,
            sentiment=sentiment,
            key_points=[document.title],
            org_change=org_change,
            financial_signal=sentiment if event_type == EventType.FINANCIAL else Sentiment.NEUTRAL,
            source_confidence=clamp(document.relevance_score or 0.5, 0.3, 0.95),
        )

    def _fallback_narrative(
        self,
        profile: CompanyProfile,
        scores: ScoreBreakdown,
        source_facts: list[SourceFact],
        risks: list[str],
        projection_summary: str,
    ) -> ReportNarrative:
        positives = [fact.summary for fact in source_facts if fact.sentiment == Sentiment.POSITIVE][:3]
        negatives = [fact.summary for fact in source_facts if fact.sentiment == Sentiment.NEGATIVE][:3]
        executive_summary = (
            f"{profile.canonical_name} scores {scores.overall:.1f}/100. "
            f"The current view is based on {len(source_facts)} source-grounded signals and an identity confidence of "
            f"{profile.identity_confidence:.2f}."
        )
        thesis = positives or ["The available evidence is mixed, so conviction should stay moderate."]
        downside = risks or negatives or ["Limited public evidence reduces conviction."]
        return ReportNarrative(
            executive_summary=executive_summary,
            investment_thesis=thesis,
            key_risks=downside,
            upside_drivers=positives[:3],
            projection_commentary=projection_summary,
        )
