from __future__ import annotations

from urllib.parse import quote_plus

import feedparser
import httpx

from app.config import Settings
from app.models import CompanyProfile, SourceDocument, SourceType
from app.utils import domain_from_url, extract_text_snippet, to_utc_datetime


class NewsResearcher:
    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self.http_client = http_client
        self.settings = settings

    async def search(self, profile: CompanyProfile) -> list[SourceDocument]:
        query = self._build_query(profile)
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return []

        feed = feedparser.parse(response.text)
        documents: list[SourceDocument] = []
        for index, entry in enumerate(feed.entries[: self.settings.max_news_items]):
            link = getattr(entry, "link", "")
            title = getattr(entry, "title", "Untitled")
            summary = extract_text_snippet(getattr(entry, "summary", ""), 500)
            published = getattr(entry, "published", None) or getattr(entry, "updated", None)
            source = getattr(entry, "source", None)
            documents.append(
                SourceDocument(
                    source_id=f"news-{index}",
                    source_type=SourceType.NEWS,
                    title=title,
                    url=link,
                    domain=domain_from_url(link) if link else "news.google.com",
                    published_at=to_utc_datetime(published),
                    summary=summary,
                    content=summary,
                    source_name=source.get("title") if source else None,
                )
            )
        return documents

    def _build_query(self, profile: CompanyProfile) -> str:
        parts = [f"\"{profile.canonical_name}\"", f"when:{self.settings.news_lookback_days}d"]
        if profile.ticker:
            parts.append(profile.ticker)
        return " ".join(parts)
