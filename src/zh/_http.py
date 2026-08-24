"""HTTPS-only HTTP helpers (httpx)."""

from __future__ import annotations

from typing import Any

import httpx

from zh.errors import ZhApiError


def assert_https_url(url: str) -> None:
    if not url.startswith("https://"):
        msg = f"Refusing non-HTTPS URL: {url}"
        raise ZhApiError(msg)


def request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    timeout: float,
) -> Any:
    """Perform an HTTPS request and return parsed JSON (dict/list).

    Raises ZhApiError on non-HTTPS URLs, transport failures, HTTP errors,
    or non-JSON bodies.
    """
    assert_https_url(url)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, url, headers=headers, json=json_body)
    except httpx.TimeoutException as exc:
        raise ZhApiError(f"Transport error to {url}: timed out after {timeout}s") from exc
    except httpx.RequestError as exc:
        raise ZhApiError(f"Transport error to {url}: {exc}") from exc

    body = resp.text
    if resp.status_code >= 400:
        raise ZhApiError(f"HTTP {resp.status_code} from {url}: {body or resp.reason_phrase}")

    try:
        return resp.json()
    except ValueError as exc:
        raise ZhApiError(f"Non-JSON response from {url}: {body[:200]!r}") from exc


def request_text(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    timeout: float,
) -> tuple[int, str]:
    """Perform an HTTPS request and return ``(status_code, body_text)``.

    Does not raise on HTTP error statuses (caller interprets). Transport
    failures and non-HTTPS URLs still raise ZhApiError.
    """
    assert_https_url(url)
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, url, headers=headers, json=json_body)
    except httpx.TimeoutException as exc:
        raise ZhApiError(f"Transport error to {url}: timed out after {timeout}s") from exc
    except httpx.RequestError as exc:
        raise ZhApiError(f"Transport error to {url}: {exc}") from exc
    return resp.status_code, resp.text
