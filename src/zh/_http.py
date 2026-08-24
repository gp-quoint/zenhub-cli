"""HTTPS-only urllib helpers."""

from __future__ import annotations

import urllib.request
from typing import Any

from zh.errors import ZhApiError


def assert_https_url(url: str) -> None:
    if not url.startswith("https://"):
        msg = f"Refusing non-HTTPS URL: {url}"
        raise ZhApiError(msg)


def urlopen_https(req: urllib.request.Request, *, timeout: float) -> Any:
    assert_https_url(req.full_url)
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
