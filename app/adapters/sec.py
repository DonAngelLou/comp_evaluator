from __future__ import annotations

from datetime import date, datetime

import httpx

from app.config import Settings
from app.models import CompanyProfile, FinancialSnapshot, SecLookupResult, SourceDocument, SourceType
from app.utils import clamp, domain_from_url, normalize_text, safe_ratio, similarity, token_set


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class SecResearcher:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self.http_client = http_client
        self.settings = settings
        self._ticker_cache: list[dict[str, str]] | None = None

    async def collect(self, profile: CompanyProfile, ticker_hints: list[str]) -> SecLookupResult:
        match = await self._lookup_company(profile, ticker_hints)
        if not match:
            return SecLookupResult()

        cik = match["cik"].zfill(10)
        submissions_url = SEC_SUBMISSIONS_URL.format(cik=cik)
        facts_url = SEC_COMPANY_FACTS_URL.format(cik=cik)
        submissions = await self._get_json(submissions_url)
        facts = await self._get_json(facts_url)
        filings = self._build_filing_documents(cik, submissions)
        snapshot = self._build_financial_snapshot(submissions, facts)
        return SecLookupResult(
            ticker=match["ticker"],
            cik=cik,
            confidence=match["confidence"],
            financial_snapshot=snapshot,
            filing_documents=filings,
        )

    async def _lookup_company(self, profile: CompanyProfile, ticker_hints: list[str]) -> dict[str, str | float] | None:
        tickers = await self._ticker_rows()
        if not tickers:
            return None

        best: dict[str, str | float] | None = None
        normalized_tickers = {ticker.upper() for ticker in ticker_hints}
        aliases = [profile.canonical_name, profile.input_name, *profile.aliases]
        for row in tickers:
            title = str(row.get("title", ""))
            ticker = str(row.get("ticker", "")).upper()
            score = max(similarity(title, alias) for alias in aliases if alias.strip())
            title_tokens = token_set(title)
            overlap = max(
                (
                    len(title_tokens & token_set(alias)) / len(token_set(alias))
                    for alias in aliases
                    if token_set(alias)
                ),
                default=0.0,
            )
            if ticker and ticker in normalized_tickers:
                score += 0.15
            if normalize_text(title) in {normalize_text(alias) for alias in aliases if alias.strip()}:
                score += 0.12
            elif overlap >= 1.0 and len(title_tokens) >= 1:
                score += 0.1
            elif overlap >= 0.75:
                score += 0.06
            score = clamp(score, 0.0, 1.0)
            if best is None or score > float(best["confidence"]):
                best = {
                    "title": title,
                    "ticker": ticker,
                    "cik": str(row.get("cik_str", "")),
                    "confidence": score,
                    "overlap": overlap,
                }
        if best and float(best["confidence"]) >= 0.72 and float(best["overlap"]) >= 0.5:
            return best
        return None

    async def _ticker_rows(self) -> list[dict[str, str]]:
        if self._ticker_cache is not None:
            return self._ticker_cache
        payload = await self._get_json(SEC_TICKERS_URL)
        rows: list[dict[str, str]] = []
        if isinstance(payload, dict):
            values = payload.values()
        elif isinstance(payload, list):
            values = payload
        else:
            values = []
        for item in values:
            if isinstance(item, dict):
                rows.append(item)
        self._ticker_cache = rows
        return rows

    async def _get_json(self, url: str) -> dict | list | None:
        headers = {"User-Agent": self.settings.sec_user_agent, "Accept": "application/json"}
        try:
            response = await self.http_client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        return response.json()

    def _build_filing_documents(self, cik: str, submissions: dict | list | None) -> list[SourceDocument]:
        if not isinstance(submissions, dict):
            return []
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        accepted: list[SourceDocument] = []
        interesting_forms = {"10-K", "10-Q", "8-K", "DEF 14A"}
        for index, form in enumerate(forms[:25]):
            if form not in interesting_forms:
                continue
            accession = accession_numbers[index].replace("-", "")
            primary_doc = primary_docs[index]
            filing_date = filing_dates[index]
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{primary_doc}"
            accepted.append(
                SourceDocument(
                    source_id=f"sec-{form.lower()}-{index}",
                    source_type=SourceType.SEC_FILING,
                    title=f"{form} filing",
                    url=url,
                    domain=domain_from_url(url),
                    published_at=datetime.fromisoformat(f"{filing_date}T00:00:00"),
                    summary=f"{form} filed on {filing_date}.",
                    content=f"SEC filing {form} for CIK {cik}, filed on {filing_date}.",
                    source_name="SEC EDGAR",
                )
            )
            if len(accepted) >= 6:
                break
        return accepted

    def _build_financial_snapshot(self, submissions: dict | list | None, facts: dict | list | None) -> FinancialSnapshot:
        snapshot = FinancialSnapshot()
        if isinstance(submissions, dict):
            recent = submissions.get("filings", {}).get("recent", {})
            dates = recent.get("filingDate", [])
            forms = recent.get("form", [])
            if dates:
                snapshot.latest_filing_date = date.fromisoformat(dates[0])
            if forms:
                snapshot.latest_filing_form = forms[0]

        if not isinstance(facts, dict):
            return snapshot

        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        revenue_series = self._extract_series(
            us_gaap,
            ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
        )
        net_income_series = self._extract_series(us_gaap, ["NetIncomeLoss"])
        current_assets_series = self._extract_series(us_gaap, ["AssetsCurrent"])
        current_liabilities_series = self._extract_series(us_gaap, ["LiabilitiesCurrent"])
        cash_series = self._extract_series(us_gaap, ["CashAndCashEquivalentsAtCarryingValue"])

        latest_revenue = revenue_series[0] if revenue_series else None
        previous_revenue = revenue_series[1] if len(revenue_series) > 1 else None
        latest_income = net_income_series[0] if net_income_series else None
        current_assets = current_assets_series[0] if current_assets_series else None
        current_liabilities = current_liabilities_series[0] if current_liabilities_series else None
        cash = cash_series[0] if cash_series else None

        snapshot.latest_revenue = latest_revenue["value"] if latest_revenue else None
        snapshot.revenue_period_end = latest_revenue["end"] if latest_revenue else None
        if latest_revenue and previous_revenue and previous_revenue["value"]:
            snapshot.revenue_growth_yoy = (latest_revenue["value"] - previous_revenue["value"]) / abs(previous_revenue["value"])
        snapshot.latest_net_income = latest_income["value"] if latest_income else None
        snapshot.net_income_period_end = latest_income["end"] if latest_income else None
        snapshot.net_income_margin = safe_ratio(snapshot.latest_net_income, snapshot.latest_revenue)
        snapshot.current_assets = current_assets["value"] if current_assets else None
        snapshot.current_liabilities = current_liabilities["value"] if current_liabilities else None
        snapshot.current_ratio = safe_ratio(snapshot.current_assets, snapshot.current_liabilities)
        snapshot.cash_and_equivalents = cash["value"] if cash else None
        snapshot.has_financial_data = snapshot.latest_revenue is not None or snapshot.latest_net_income is not None
        return snapshot

    def _extract_series(self, us_gaap: dict, concept_names: list[str]) -> list[dict[str, object]]:
        for concept in concept_names:
            concept_block = us_gaap.get(concept)
            if not isinstance(concept_block, dict):
                continue
            units = concept_block.get("units", {})
            usd_values = units.get("USD", [])
            cleaned: list[dict[str, object]] = []
            for item in usd_values:
                if item.get("form") not in {"10-K", "10-Q", "20-F", "6-K"}:
                    continue
                value = item.get("val")
                end = item.get("end")
                if value is None or not end:
                    continue
                cleaned.append({"value": float(value), "end": date.fromisoformat(end)})
            cleaned.sort(key=lambda item: item["end"], reverse=True)
            if cleaned:
                return cleaned
        return []
