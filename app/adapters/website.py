from __future__ import annotations

import asyncio
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from app.models import SourceDocument, SourceType, WebsiteResearchResult
from app.utils import (
    domain_from_url,
    extract_text_snippet,
    extract_ticker_hints,
    joined_unique,
    normalize_text,
    normalize_website,
    same_domain,
    slugify,
)


class WebsiteResearcher:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self.http_client = http_client

    async def collect(self, company_name: str, website: str) -> tuple[str, str, WebsiteResearchResult]:
        normalized_url, domain = normalize_website(website)
        homepage_html = await self._fetch_text(normalized_url)
        if homepage_html is None:
            raise ValueError("Could not fetch the company website.")

        homepage_doc, metadata = self._parse_document(normalized_url, homepage_html, SourceType.WEBSITE, "website-home")
        candidate_urls = self._discover_relevant_urls(normalized_url, homepage_html)
        pages = await self._fetch_pages(candidate_urls)
        documents = [homepage_doc]
        for page_url, page_html in pages:
            doc, _ = self._parse_document(page_url, page_html, SourceType.WEBSITE, f"website-{slugify(page_url)}")
            documents.append(doc)

        combined_text = " ".join(filter(None, [homepage_doc.title, homepage_doc.summary, *[doc.summary for doc in documents]]))
        canonical_name = (
            metadata.get("og_site_name")
            or metadata.get("application_name")
            or metadata.get("title_candidate")
            or company_name
        )
        aliases = joined_unique(
            [company_name],
            [canonical_name],
            metadata.get("title_parts", []),
        )
        ticker_hints = extract_ticker_hints(combined_text)
        summary = homepage_doc.summary or f"{canonical_name} corporate website."
        confidence = 0.65
        if canonical_name and normalize_text(canonical_name) != normalize_text(company_name):
            confidence += 0.05
        if ticker_hints:
            confidence += 0.05

        return normalized_url, domain, WebsiteResearchResult(
            canonical_name=canonical_name,
            aliases=aliases,
            ticker_hints=ticker_hints,
            summary=summary,
            documents=documents,
            identity_confidence=min(confidence, 0.85),
        )

    async def _fetch_pages(self, urls: Iterable[str]) -> list[tuple[str, str]]:
        unique_urls = list(dict.fromkeys(urls))
        tasks = [self._fetch_text(url) for url in unique_urls]
        payloads = await asyncio.gather(*tasks)
        pages: list[tuple[str, str]] = []
        for url, html in zip(unique_urls, payloads):
            if html:
                pages.append((url, html))
        return pages

    async def _fetch_text(self, url: str) -> str | None:
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        if "text/html" not in response.headers.get("content-type", ""):
            return None
        return response.text

    def _discover_relevant_urls(self, base_url: str, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        base_domain = domain_from_url(base_url)
        candidates: list[str] = []
        keywords = ("about", "investor", "investors", "news", "press", "leadership", "company")
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            text = normalize_text(anchor.get_text(" ", strip=True))
            if not any(keyword in href.lower() or keyword in text for keyword in keywords):
                continue
            absolute = urljoin(base_url, href)
            if same_domain(absolute, base_domain):
                candidates.append(absolute)
            if len(candidates) >= 5:
                break
        return candidates

    def _parse_document(
        self,
        url: str,
        html: str,
        source_type: SourceType,
        source_id: str,
    ) -> tuple[SourceDocument, dict[str, object]]:
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else url
        description_meta = soup.find("meta", attrs={"name": "description"})
        og_site_name = soup.find("meta", attrs={"property": "og:site_name"})
        application_name = soup.find("meta", attrs={"name": "application-name"})
        paragraphs = [
            paragraph.get_text(" ", strip=True)
            for paragraph in soup.find_all(["p", "h1", "h2", "li"])
        ]
        summary = extract_text_snippet(
            description_meta["content"] if description_meta and description_meta.get("content") else " ".join(paragraphs[:8]),
            600,
        )
        doc = SourceDocument(
            source_id=source_id,
            source_type=source_type,
            title=title,
            url=url,
            domain=domain_from_url(url),
            summary=summary,
            content=extract_text_snippet(" ".join(paragraphs), 2500),
            source_name=domain_from_url(url),
        )
        title_parts = [part.strip() for part in title.split("|") if part.strip()]
        metadata = {
            "og_site_name": og_site_name.get("content") if og_site_name and og_site_name.get("content") else None,
            "application_name": application_name.get("content") if application_name and application_name.get("content") else None,
            "title_candidate": title_parts[0] if title_parts else None,
            "title_parts": title_parts,
        }
        return doc, metadata
