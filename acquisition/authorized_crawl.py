"""Permission-gated crawler for company-authorized websites only (Phase 9)."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
from django.conf import settings

from acquisition.candidates import BusinessCandidate
from acquisition.http_retry import request_with_retries
from acquisition.ingest import IngestStats, ingest_candidates
from sources.models import DataSource
from sources.quota import require_preflight

logger = logging.getLogger("acquisition")

PHONE_RE = re.compile(
    r"(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}"
)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)

MAX_REDIRECTS = 5


class AuthorizedCrawlError(Exception):
    """Raised when crawl is refused or fails."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_public_https_url(url: str, *, context: str = "URL") -> None:
    """Require https and resolve host to non-private IPs (SSRF guard)."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise AuthorizedCrawlError(f"{context} must use https:// (got {parsed.scheme!r})")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise AuthorizedCrawlError(f"{context} is missing a hostname")
    if host in ("localhost", "metadata.google.internal"):
        raise AuthorizedCrawlError(f"{context} host is not allowed: {host}")

    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AuthorizedCrawlError(f"{context} host could not be resolved: {host}") from exc

    if not infos:
        raise AuthorizedCrawlError(f"{context} host could not be resolved: {host}")

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            raise AuthorizedCrawlError(
                f"{context} resolves to a blocked address ({ip}); "
                "private/link-local/metadata hosts are not allowed"
            )


def assert_authorized(source: DataSource) -> dict:
    """Validate source is an authorized website; return allowed_params."""
    if source.source_type != DataSource.SourceType.WEBSITE:
        raise AuthorizedCrawlError(
            f"{source.slug} is not source_type=website (got {source.source_type})"
        )
    params = source.allowed_params or {}
    if params.get("authorized") is not True:
        raise AuthorizedCrawlError(
            f"{source.slug} is not marked authorized=true in allowed_params. "
            "Only company-approved sites may be crawled."
        )
    base_url = (params.get("base_url") or "").strip()
    if not base_url:
        raise AuthorizedCrawlError(f"{source.slug} missing allowed_params.base_url")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AuthorizedCrawlError(
            f"{source.slug} base_url must be https:// with a host (got {base_url!r})"
        )
    assert_public_https_url(base_url, context=f"{source.slug} base_url")
    return params


def _fetch_with_safe_redirects(
    client: httpx.Client,
    url: str,
    *,
    base_host: str,
) -> httpx.Response:
    """GET without automatic redirects; re-validate each hop against SSRF rules."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_https_url(current, context="crawl URL")
        if urlparse(current).netloc.lower() != base_host:
            raise AuthorizedCrawlError(f"Redirect left authorized host: {current}")
        response = request_with_retries(client, "GET", current)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        location = response.headers.get("Location") or response.headers.get("location")
        if not location:
            return response
        current = urljoin(current, location)
    raise AuthorizedCrawlError(f"Too many redirects starting from {url}")


def crawl_authorized_source(
    source: DataSource,
    *,
    city: str = "",
    category: str = "website",
    limit: int = 25,
    max_pages: int = 5,
) -> IngestStats:
    """
    Fetch allowlisted pages under base_url, extract phone-like strings,
    and ingest as BusinessCandidates.
    """
    if not source.is_active:
        raise AuthorizedCrawlError(f"{source.slug} is inactive")
    params = assert_authorized(source)
    require_preflight(source, min_calls=1)

    base_url = params["base_url"].rstrip("/") + "/"
    start_paths = params.get("start_paths") or ["/"]
    if isinstance(start_paths, str):
        start_paths = [start_paths]
    delay = float(
        params.get("delay_seconds")
        or getattr(settings, "AUTHORIZED_CRAWL_DELAY_SECONDS", 1.5)
    )
    user_agent = getattr(
        settings,
        "AUTHORIZED_CRAWL_USER_AGENT",
        "PhoneCollectionAgent/0.1 (authorized-crawl)",
    )
    base_host = urlparse(base_url).netloc.lower()

    queue: list[str] = []
    for path in start_paths:
        queue.append(urljoin(base_url, path))
    seen: set[str] = set()
    candidates: list[BusinessCandidate] = []

    with httpx.Client(
        timeout=float(getattr(settings, "HTTP_TIMEOUT", 30.0)),
        headers={"User-Agent": user_agent, "Accept": "text/html"},
        follow_redirects=False,
    ) as client:
        pages = 0
        while queue and pages < max_pages and len(candidates) < limit:
            url = queue.pop(0)
            if url in seen:
                continue
            if urlparse(url).netloc.lower() != base_host:
                logger.info("Skip off-host URL %s", url)
                continue
            if not url.startswith(base_url.rstrip("/")) and urlparse(url).path:
                # Still same host; require path under base path prefix
                base_path = urlparse(base_url).path or "/"
                if not urlparse(url).path.startswith(base_path.rstrip("/") or "/"):
                    if urlparse(base_url).path not in ("", "/"):
                        continue
            seen.add(url)
            pages += 1
            logger.info("Authorized crawl GET %s", url)
            try:
                response = _fetch_with_safe_redirects(
                    client, url, base_host=base_host
                )
            except AuthorizedCrawlError:
                logger.warning("Crawl refused for %s", url)
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                logger.warning("Crawl %s status=%s", url, response.status_code)
                time.sleep(delay)
                continue
            text = response.text or ""
            for match in PHONE_RE.findall(text):
                raw = match.strip()
                if not raw:
                    continue
                candidates.append(
                    BusinessCandidate(
                        raw_phone=raw,
                        business_name=f"Authorized site {source.slug}",
                        address="",
                        city=city or "",
                        state="",
                        postal_code="",
                        category=category or "website",
                        source_record_id="",
                        source_url=url[:1024],
                        raw_payload={"page_url": url, "source_slug": source.slug},
                    )
                )
                if len(candidates) >= limit:
                    break
            # Discover same-host links for shallow crawl
            if pages < max_pages:
                for href in HREF_RE.findall(text):
                    abs_url = urljoin(url, href.split("#")[0])
                    parsed_link = urlparse(abs_url)
                    if (
                        abs_url not in seen
                        and parsed_link.scheme == "https"
                        and parsed_link.netloc.lower() == base_host
                    ):
                        queue.append(abs_url)
            time.sleep(delay)

    # Deduplicate by raw phone text within this crawl
    unique: list[BusinessCandidate] = []
    seen_phones: set[str] = set()
    for c in candidates:
        key = re.sub(r"\D", "", c.raw_phone)
        if key in seen_phones:
            continue
        seen_phones.add(key)
        unique.append(c)

    return ingest_candidates(
        unique,
        source=source,
        city_hint=city or "",
        category_label=category or "website",
        source_query=f"authorized_crawl slug={source.slug} base={base_url}",
        limit=limit,
    )
