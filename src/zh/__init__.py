"""ZenHub CLI — Python package."""

from __future__ import annotations

try:
    from zh._version import __version__
except ImportError:  # pragma: no cover - editable/source tree before first build
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover
        __version__ = "0.0.0"
    else:
        try:
            __version__ = version("zenhub-cli")
        except PackageNotFoundError:
            __version__ = "0.0.0"
