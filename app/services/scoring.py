from __future__ import annotations

from app.models import (
    FinancialSnapshot,
    ProjectionScenario,
    ScoreBreakdown,
    Sentiment,
    SourceFact,
    UpsideProjection,
    Verdict,
)
from app.utils import clamp


def compute_scores(
    financial_snapshot: FinancialSnapshot,
    facts: list[SourceFact],
    identity_confidence: float,
) -> tuple[ScoreBreakdown, Verdict, list[str]]:
    financial = _financial_score(financial_snapshot)
    momentum = _momentum_score(facts)
    governance = _governance_score(facts)
    valuation_confidence = clamp(identity_confidence * 70 + min(len(facts), 8) * 3, 15, 100)
    if financial_snapshot.has_financial_data:
        valuation_confidence = clamp(valuation_confidence + 10, 0, 100)

    overall = clamp(financial * 0.35 + momentum * 0.25 + governance * 0.15 + valuation_confidence * 0.25, 0, 100)
    verdict = _verdict(overall, identity_confidence, financial_snapshot.has_financial_data)
    risks = derive_risks(financial_snapshot, facts, identity_confidence)
    return (
        ScoreBreakdown(
            financial=round(financial, 1),
            momentum=round(momentum, 1),
            governance=round(governance, 1),
            valuation_confidence=round(valuation_confidence, 1),
            overall=round(overall, 1),
        ),
        verdict,
        risks,
    )


def build_projection(scores: ScoreBreakdown, facts: list[SourceFact], risks: list[str]) -> UpsideProjection:
    positive_count = sum(1 for fact in facts if fact.sentiment == Sentiment.POSITIVE)
    negative_count = sum(1 for fact in facts if fact.sentiment == Sentiment.NEGATIVE)
    base_return = clamp((scores.overall - 50) * 0.45, -15, 20)
    bull_return = clamp(base_return * 1.6 + 6 + positive_count * 1.5, -5, 35)
    bear_return = clamp(base_return * 1.4 - 10 - negative_count * 1.5, -35, 5)
    return UpsideProjection(
        bull_case=ProjectionScenario(
            name="bull",
            projected_return_pct=round(bull_return, 1),
            assumptions=[
                "Recent positive catalysts convert into sustained execution.",
                "Revenue trend and sentiment improve faster than the base case.",
            ],
        ),
        base_case=ProjectionScenario(
            name="base",
            projected_return_pct=round(base_return, 1),
            assumptions=[
                "Current operating trend persists over the next 12 months.",
                "No major adverse governance or legal event appears.",
            ],
        ),
        bear_case=ProjectionScenario(
            name="bear",
            projected_return_pct=round(bear_return, 1),
            assumptions=[
                "Recent risks intensify or current weaknesses persist.",
                risks[0] if risks else "Confidence falls if evidence remains thin.",
            ],
        ),
    )


def _financial_score(snapshot: FinancialSnapshot) -> float:
    if not snapshot.has_financial_data:
        return 40.0
    score = 50.0
    if snapshot.revenue_growth_yoy is not None:
        score += clamp(snapshot.revenue_growth_yoy * 80, -20, 20)
    if snapshot.latest_net_income is not None:
        score += 8 if snapshot.latest_net_income > 0 else -12
    if snapshot.net_income_margin is not None:
        score += clamp(snapshot.net_income_margin * 100, -10, 12)
    if snapshot.current_ratio is not None:
        if snapshot.current_ratio >= 1.5:
            score += 10
        elif snapshot.current_ratio >= 1.0:
            score += 4
        else:
            score -= 10
    return clamp(score, 0, 100)


def _momentum_score(facts: list[SourceFact]) -> float:
    score = 50.0
    for fact in facts:
        if fact.sentiment == Sentiment.POSITIVE:
            score += 6 * fact.source_confidence
        elif fact.sentiment == Sentiment.NEGATIVE:
            score -= 8 * fact.source_confidence
    return clamp(score, 0, 100)


def _governance_score(facts: list[SourceFact]) -> float:
    score = 55.0
    for fact in facts:
        if fact.org_change and fact.sentiment == Sentiment.NEGATIVE:
            score -= 15 * fact.source_confidence
        elif fact.org_change and fact.sentiment == Sentiment.POSITIVE:
            score += 6 * fact.source_confidence
    return clamp(score, 0, 100)


def _verdict(overall: float, identity_confidence: float, has_financial_data: bool) -> Verdict:
    if identity_confidence < 0.6:
        return Verdict.WATCH
    if overall >= 67 and has_financial_data:
        return Verdict.GOOD_INVESTMENT_NOW
    if overall < 45:
        return Verdict.AVOID_FOR_NOW
    return Verdict.WATCH


def derive_risks(snapshot: FinancialSnapshot, facts: list[SourceFact], identity_confidence: float) -> list[str]:
    risks: list[str] = []
    if identity_confidence < 0.75:
        risks.append("Identity confidence is below ideal, so same-name contamination risk remains.")
    if not snapshot.has_financial_data:
        risks.append("Financial filings are missing or not confidently linked, which weakens conviction.")
    if snapshot.latest_net_income is not None and snapshot.latest_net_income < 0:
        risks.append("Latest reported net income is negative.")
    if snapshot.current_ratio is not None and snapshot.current_ratio < 1:
        risks.append("Current liabilities exceed current assets, indicating liquidity pressure.")
    if any(fact.sentiment == Sentiment.NEGATIVE for fact in facts):
        risks.append("Recent source-grounded activity includes at least one negative signal.")
    return risks[:5]
