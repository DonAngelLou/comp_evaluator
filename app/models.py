from __future__ import annotations

from datetime import date as Date, datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    WEBSITE = "website"
    SEC_FILING = "sec_filing"
    NEWS = "news"


class EventType(str, Enum):
    FINANCIAL = "financial"
    LEADERSHIP = "leadership"
    GOVERNANCE = "governance"
    PRODUCT = "product"
    PARTNERSHIP = "partnership"
    OPERATIONS = "operations"
    LEGAL = "legal"
    MARKET = "market"
    OTHER = "other"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Verdict(str, Enum):
    GOOD_INVESTMENT_NOW = "good_investment_now"
    WATCH = "watch"
    AVOID_FOR_NOW = "avoid_for_now"


class EvaluationRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    website: str = Field(min_length=3, max_length=500)


class Citation(BaseModel):
    source_id: str
    source_type: SourceType
    title: str
    url: str
    domain: str
    published_at: datetime | None = None


class SourceDocument(BaseModel):
    source_id: str
    source_type: SourceType
    title: str
    url: str
    domain: str
    published_at: datetime | None = None
    summary: str = ""
    content: str = ""
    source_name: str | None = None
    relevance_score: float = 0.0
    relevance_reason: str | None = None


class CompanyProfile(BaseModel):
    input_name: str
    canonical_name: str
    website: str
    domain: str
    aliases: list[str] = Field(default_factory=list)
    ticker: str | None = None
    cik: str | None = None
    public_company: bool = False
    identity_confidence: float = 0.0
    summary: str | None = None


class SourceSummary(BaseModel):
    total_sources: int
    accepted_sources: int
    rejected_sources: int
    by_type: dict[str, int]


class FinancialSnapshot(BaseModel):
    has_financial_data: bool = False
    currency: str = "USD"
    latest_revenue: float | None = None
    revenue_period_end: Date | None = None
    revenue_growth_yoy: float | None = None
    latest_net_income: float | None = None
    net_income_period_end: Date | None = None
    net_income_margin: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    current_ratio: float | None = None
    cash_and_equivalents: float | None = None
    latest_filing_date: Date | None = None
    latest_filing_form: str | None = None


class ActivityItem(BaseModel):
    title: str
    date: Date | None = None
    category: EventType = EventType.OTHER
    sentiment: Sentiment = Sentiment.NEUTRAL
    summary: str
    source_ids: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    financial: float
    momentum: float
    governance: float
    valuation_confidence: float
    overall: float


class ProjectionScenario(BaseModel):
    name: str
    projected_return_pct: float
    assumptions: list[str]


class UpsideProjection(BaseModel):
    horizon_months: int = 12
    bull_case: ProjectionScenario
    base_case: ProjectionScenario
    bear_case: ProjectionScenario


class EvaluationResponse(BaseModel):
    company_profile: CompanyProfile
    source_summary: SourceSummary
    financial_snapshot: FinancialSnapshot
    recent_activity: list[ActivityItem]
    org_changes: list[ActivityItem]
    scores: ScoreBreakdown
    verdict: Verdict
    upside_projection: UpsideProjection
    risks: list[str]
    citations: list[Citation]
    report_markdown: str
    report_html: str


class WebsiteResearchResult(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    ticker_hints: list[str] = Field(default_factory=list)
    summary: str | None = None
    documents: list[SourceDocument] = Field(default_factory=list)
    identity_confidence: float = 0.0


class SecLookupResult(BaseModel):
    ticker: str | None = None
    cik: str | None = None
    confidence: float = 0.0
    financial_snapshot: FinancialSnapshot = Field(default_factory=FinancialSnapshot)
    filing_documents: list[SourceDocument] = Field(default_factory=list)


class SourceFact(BaseModel):
    source_id: str
    summary: str
    event_type: EventType = EventType.OTHER
    sentiment: Sentiment = Sentiment.NEUTRAL
    key_points: list[str] = Field(default_factory=list)
    org_change: bool = False
    financial_signal: Sentiment = Sentiment.NEUTRAL
    source_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ReportNarrative(BaseModel):
    executive_summary: str
    investment_thesis: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    upside_drivers: list[str] = Field(default_factory=list)
    projection_commentary: str
