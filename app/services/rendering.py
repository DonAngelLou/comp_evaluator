from __future__ import annotations

from markdown import markdown

from app.models import EvaluationResponse
from app.utils import percent


def render_report(response: EvaluationResponse) -> tuple[str, str]:
    snapshot = response.financial_snapshot
    markdown_text = f"""# {response.company_profile.canonical_name} Investment Evaluation

## Verdict

**{response.verdict.value}** with overall score **{response.scores.overall:.1f}/100**.

## Executive Summary

{response.report_markdown}

## Financial Snapshot

- Latest revenue: {snapshot.latest_revenue if snapshot.latest_revenue is not None else "n/a"}
- Revenue growth YoY: {percent(snapshot.revenue_growth_yoy)}
- Latest net income: {snapshot.latest_net_income if snapshot.latest_net_income is not None else "n/a"}
- Net income margin: {percent(snapshot.net_income_margin)}
- Current ratio: {snapshot.current_ratio if snapshot.current_ratio is not None else "n/a"}
- Latest filing: {snapshot.latest_filing_form or "n/a"} on {snapshot.latest_filing_date or "n/a"}

## Recent Activity

{_render_activity(response.recent_activity)}

## Organization Changes

{_render_activity(response.org_changes)}

## Upside Projection

- Bull case: {response.upside_projection.bull_case.projected_return_pct:.1f}%
- Base case: {response.upside_projection.base_case.projected_return_pct:.1f}%
- Bear case: {response.upside_projection.bear_case.projected_return_pct:.1f}%

## Risks

{_render_risks(response.risks)}

## Citations

{_render_citations(response)}
"""
    return markdown_text, markdown(markdown_text)


def _render_activity(items) -> str:
    if not items:
        return "- No strongly grounded recent activity was available."
    return "\n".join(
        f"- {item.date or 'undated'}: {item.title} [{', '.join(item.source_ids)}] - {item.summary}"
        for item in items
    )


def _render_risks(risks: list[str]) -> str:
    if not risks:
        return "- No major source-grounded risks were identified."
    return "\n".join(f"- {risk}" for risk in risks)


def _render_citations(response: EvaluationResponse) -> str:
    if not response.citations:
        return "- No citations."
    return "\n".join(
        f"- {citation.source_id}: [{citation.title}]({citation.url})"
        for citation in response.citations
    )
