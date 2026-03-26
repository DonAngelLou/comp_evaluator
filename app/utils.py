from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html import unescape
from typing import Iterable
from urllib.parse import urlparse


WHITESPACE_RE = re.compile(r"\s+")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
TICKER_RE = re.compile(r"(?:nasdaq|nyse|amex|otc)\s*[:(]?\s*([a-z.\-]{1,6})", re.IGNORECASE)


def normalize_website(website: str) -> tuple[str, str]:
    raw = website.strip()
    if not raw:
        raise ValueError("Website is required.")
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError("Website must include a valid domain.")
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    normalized = parsed._replace(scheme=parsed.scheme or "https", netloc=domain).geturl().rstrip("/")
    return normalized, domain


def normalize_text(value: str) -> str:
    lowered = unescape(value).lower()
    return WHITESPACE_RE.sub(" ", lowered).strip()


def slugify(value: str) -> str:
    return NON_ALNUM_RE.sub("-", normalize_text(value)).strip("-")


def token_set(value: str) -> set[str]:
    return {token for token in NON_ALNUM_RE.split(normalize_text(value)) if token}


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(a=normalize_text(left), b=normalize_text(right)).ratio()


def same_domain(candidate_url: str, domain: str) -> bool:
    parsed = urlparse(candidate_url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == domain or host.endswith(f".{domain}")


def extract_text_snippet(text: str, limit: int = 1400) -> str:
    normalized = WHITESPACE_RE.sub(" ", unescape(text)).strip()
    return normalized[:limit]


def extract_ticker_hints(text: str) -> list[str]:
    seen: list[str] = []
    for match in TICKER_RE.finditer(text):
        ticker = match.group(1).upper()
        if ticker not in seen:
            seen.append(ticker)
    return seen


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def to_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def mean(values: Iterable[float], default: float = 0.0) -> float:
    materialized = list(values)
    if not materialized:
        return default
    return sum(materialized) / len(materialized)


def joined_unique(*groups: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for item in group:
            cleaned = item.strip()
            if not cleaned:
                continue
            key = normalize_text(cleaned)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(cleaned)
    return ordered


def percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def log_scaled_score(value: float, max_value: float = 1_000_000_000.0) -> float:
    if value <= 0:
        return 0.0
    return clamp(math.log10(min(value, max_value) + 1) / math.log10(max_value + 1), 0.0, 1.0)
