"""Central loguru configuration for the zh CLI and MCP server."""

from __future__ import annotations

import logging
import os
import re
import sys

from loguru import logger

from zh.cli.color import color_enabled, get_color_mode, no_color_set, paint, reset_consoles, set_color_mode, stderr_console, stdout_console

__all__ = [
    "color_enabled",
    "configure_cli_logging",
    "configure_mcp_logging",
    "get_color_mode",
    "intercept_stdlib_loggers",
    "logger",
    "no_color_set",
    "normalize_log_message",
    "paint",
    "reconfigure_cli_logging",
    "reset_consoles",
    "set_color_mode",
    "silence_third_party_loggers",
    "stderr_console",
    "stdout_console",
]

_ACRONYMS: dict[str, str] = {
    "api": "API",
    "acl": "ACL",
    "cli": "CLI",
    "dr": "DR",
    "graphql": "GraphQL",
    "github": "GitHub",
    "http": "HTTP",
    "https": "HTTPS",
    "id": "ID",
    "json": "JSON",
    "mcp": "MCP",
    "oauth": "OAuth",
    "pr": "PR",
    "rest": "REST",
    "stix": "STIX",
    "url": "URL",
    "zenhub": "ZenHub",
}

_WORD_RE = re.compile(r"[A-Za-z]+")
_SUCCESS_TITLE_HEAD_RE = re.compile(
    r"(?:created|updated|moved|assigned|reordered|closed|reopened|deleted|added|removed|set|changed)\b.*#\d+$",
    re.IGNORECASE,
)


def _normalize_word(word: str) -> str:
    if word.isupper() and len(word) >= 2:
        return word
    canonical = _ACRONYMS.get(word.lower())
    if canonical is not None:
        return canonical
    if any(ch.isupper() for ch in word[1:]):
        return word
    return word.lower()


def normalize_log_message(message: str) -> str:
    """Lowercase CLI/MCP log prose while preserving acronyms and payload tails."""
    if ": " in message:
        head, sep, tail = message.partition(": ")
        if _SUCCESS_TITLE_HEAD_RE.search(head):
            return _normalize_words(head) + sep + tail
    return _normalize_words(message)


def _normalize_words(text: str) -> str:
    return _WORD_RE.sub(lambda match: _normalize_word(match.group(0)), text)


_cli_configured = False


def intercept_stdlib_loggers(
    *,
    names: tuple[str, ...] = ("huggingface_hub", "transformers", "sentence_transformers"),
    min_level: int = logging.ERROR,
) -> None:
    """Route selected stdlib loggers through loguru, dropping below ``min_level``."""

    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno < min_level:
                return
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            logger.opt(depth=6, exception=record.exc_info).log(level, record.getMessage())

    for name in names:
        log = logging.getLogger(name)
        log.handlers = [InterceptHandler()]
        log.propagate = False
        log.setLevel(min_level)


def configure_cli_logging(*, force: bool = False) -> None:
    """User-facing CLI output on stderr; ``print_line`` on stdout."""
    global _cli_configured
    if _cli_configured and not force:
        return
    logger.remove()
    logger.add(
        sys.stderr,
        format="{message}",
        level="DEBUG",
        colorize=False,
        filter=lambda record: not record["extra"].get("zh_stdout"),
    )
    logger.add(
        sys.stdout,
        format="{message}",
        level="DEBUG",
        colorize=False,
        filter=lambda record: record["extra"].get("zh_stdout"),
    )
    _cli_configured = True


def reconfigure_cli_logging() -> None:
    """Rebind loguru sinks and Rich consoles after ``set_color_mode`` changes."""
    from zh.cli.color import reset_consoles

    reset_consoles()
    global _cli_configured
    _cli_configured = False
    configure_cli_logging(force=True)


def configure_mcp_logging() -> None:
    """MCP diagnostics on stderr only (stdio transport uses stdout)."""
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG",
        colorize=False,
        format=lambda record: (
            f"[zenhub-mcp] {record['level'].name.lower()}: "
            f"{normalize_log_message(record['message'])}\n"
        ),
    )


def silence_third_party_loggers() -> None:
    """Quiet Hugging Face / transformers load noise for similarity search."""
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    intercept_stdlib_loggers(min_level=logging.ERROR)
    try:
        from transformers.utils.logging import set_verbosity_error

        set_verbosity_error()
    except ImportError:
        pass
