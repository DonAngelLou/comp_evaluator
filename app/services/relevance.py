from __future__ import annotations

from app.models import CompanyProfile, SourceDocument, SourceType
from app.utils import clamp, normalize_text, token_set


def score_document_relevance(document: SourceDocument, profile: CompanyProfile) -> tuple[float, str]:
    title = normalize_text(document.title)
    body = normalize_text(f"{document.summary} {document.content}")
    aliases = [profile.canonical_name, profile.input_name, *profile.aliases]
    alias_tokens = [token_set(alias) for alias in aliases if alias.strip()]
    score = 0.0
    reasons: list[str] = []

    if document.domain == profile.domain or document.domain.endswith(f".{profile.domain}"):
        score += 0.55
        reasons.append("same-domain")

    if document.source_type == SourceType.SEC_FILING and profile.cik:
        score = max(score, 0.9)
        reasons.append("verified-sec-company")

    ticker = (profile.ticker or "").lower()
    if ticker and (f" {ticker} " in f" {title} " or f" {ticker} " in f" {body} "):
        score += 0.2
        reasons.append("ticker-match")

    best_overlap = 0.0
    strongest_alias_size = len(max(alias_tokens, key=len, default=set()))
    for tokens in alias_tokens:
        if not tokens:
            continue
        title_overlap = len(tokens & token_set(title)) / len(tokens)
        body_overlap = len(tokens & token_set(body)) / len(tokens)
        best_overlap = max(best_overlap, title_overlap, body_overlap)

    if best_overlap >= 1.0 and strongest_alias_size >= 2:
        score += 0.3
        reasons.append("exact-name-match")
    elif best_overlap >= 0.75:
        score += 0.18
        reasons.append("strong-name-overlap")
    elif best_overlap >= 0.5:
        score += 0.08
        reasons.append("partial-name-overlap")

    if document.source_type == SourceType.NEWS and document.domain == "news.google.com" and best_overlap < 0.75:
        score -= 0.15
        reasons.append("weak-news-match")

    if document.domain != profile.domain and best_overlap < 0.5 and document.source_type != SourceType.SEC_FILING:
        score -= 0.2
        reasons.append("insufficient-identity-signal")

    score = clamp(score, 0.0, 1.0)
    return score, ", ".join(reasons) if reasons else "no-clear-match"


def is_document_accepted(score: float) -> bool:
    return score >= 0.45
