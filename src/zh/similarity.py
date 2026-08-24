"""Semantic duplicate detection via sentence-transformers embeddings.

Per-repo pickle cache at ~/.config/zh/index/<owner_repo>.pkl; delta-sync
through GitHub's ``since=`` filter. API: find_similar, check_duplicate, reindex.
"""

from __future__ import annotations

import json
import os
import pickle
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from zh.schemas import DuplicateCheckResult, DuplicateRecommendation, ReindexResult

INDEX_DIR = Path(os.path.expanduser("~/.config/zh/index"))
CACHE_VERSION = 1
AUTO_SYNC_TTL_SECONDS = 300
FULL_REBUILD_AFTER_SECONDS = 7 * 24 * 60 * 60
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DUPLICATE_HARD_THRESHOLD = 0.70
DUPLICATE_SOFT_THRESHOLD = 0.55
MAX_BODY_CHARS = 1500


@dataclass
class _ModelCache:
    model: Any = None


_model_cache = _ModelCache()


def _hf_hub_cache_dir() -> Path:
    if hf_home := os.environ.get("HF_HOME"):
        return Path(hf_home) / "hub"
    if xdg := os.environ.get("XDG_CACHE_HOME"):
        return Path(xdg) / "huggingface" / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _model_is_cached_locally() -> bool:
    """True when the default model snapshot is already on disk."""
    slug = DEFAULT_MODEL.replace("/", "--")
    return any(_hf_hub_cache_dir().glob(f"models--{slug}*"))


def _configure_model_load_quiet() -> None:
    """Reduce HF/transformers chatter on every CLI invocation."""
    from zh.log import silence_third_party_loggers

    silence_third_party_loggers()


def _get_model():
    """Load the sentence-transformer model on first use."""
    if _model_cache.model is None:
        _configure_model_load_quiet()
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            msg = "sentence-transformers is required for similarity search (reinstall with: uv sync)"
            raise ImportError(msg) from exc
        local_only = _model_is_cached_locally()
        _model_cache.model = SentenceTransformer(DEFAULT_MODEL, local_files_only=local_only)
    return _model_cache.model


def _embed(text: str):
    """Return a normalized embedding (L2 norm = 1) so dot product = cosine."""
    return _get_model().encode(
        text or "",
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )


@dataclass
class IssueEntry:
    """One indexed issue."""

    number: int
    repo: str  # owner/repo
    title: str
    body_preview: str  # truncated to MAX_BODY_CHARS
    state: str  # "open" | "closed"
    updated_at: str  # ISO8601, as reported by the GitHub API
    embedding: object  # numpy.ndarray; kept as object to avoid hard numpy import here


def _cache_path(repo: str) -> Path:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    safe = repo.replace("/", "_").replace(":", "_")
    return INDEX_DIR / f"{safe}.pkl"


def _empty_cache() -> dict:
    return {"version": CACHE_VERSION, "indexed_at": None, "entries": {}}


def _read_pickle_cache(handle: Any) -> dict:
    return pickle.load(handle)  # noqa: S301


def _load_cache(repo: str) -> dict:
    p = _cache_path(repo)
    if not p.exists():
        return _empty_cache()
    try:
        with p.open("rb") as f:
            data = _read_pickle_cache(f)
    except (pickle.PickleError, EOFError, OSError):
        return _empty_cache()
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return _empty_cache()
    return data


def _save_cache(repo: str, cache: dict) -> None:
    p = _cache_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")  # atomic replace on crash
    with tmp.open("wb") as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, p)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds_since(iso: str | None) -> float:
    if not iso:
        return float("inf")
    try:
        ts = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return float("inf")
    return (datetime.now(UTC) - ts).total_seconds()


# lockstep with zh.api._GH_URL_RE and bash get_repo_info; ^ rejects non-canonical schemes
_GITHUB_URL_RE = re.compile(
    r"^(?:git@github\.com:|https?://github\.com/)"
    r"([^/]+)/([^/]+?)(?:\.git)?/?$"
)


def repo_from_cwd(cwd: str) -> str:
    """Derive ``owner/repo`` from origin via ``git remote get-url`` (honors insteadOf)."""
    try:
        url = subprocess.check_output(
            ["git", "-C", cwd, "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Cannot derive repo from {cwd}: {e.stderr.strip() or 'not a git checkout'}") from e
    m = _GITHUB_URL_RE.search(url)
    if not m:
        raise RuntimeError(f"Cannot parse GitHub repo from URL: {url}")
    return f"{m.group(1)}/{m.group(2)}"


def _gh_api_paginated(path: str) -> list[dict]:
    """Call `gh api --paginate <path>` and return the flattened JSON array.

    `gh --paginate` concatenates result arrays across pages into a single
    JSON document. Raises RuntimeError on non-zero exit.
    """
    result = subprocess.run(
        ["gh", "api", "--paginate", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr.strip() or 'unknown error'}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        data = []
        for raw_line in result.stdout.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    data.extend(parsed)
                else:
                    data.append(parsed)
            except json.JSONDecodeError:
                continue
    if isinstance(data, dict):
        data = [data]
    return data


def _fetch_issues(repo: str, since: str | None = None, state: str = "all") -> list[dict]:
    """Pull issues from GitHub. `since` filters by `updated_at >=` if set."""
    path = f"repos/{repo}/issues?per_page=100&state={state}&sort=updated&direction=desc"
    if since:
        path += f"&since={since}"
    raw = _gh_api_paginated(path)
    return [i for i in raw if "pull_request" not in i]


def _build_entry(issue: dict, embedding) -> IssueEntry:
    body = issue.get("body") or ""
    return IssueEntry(
        number=int(issue["number"]),
        repo=issue["repository_url"].rsplit("/", 2)[-2] + "/" + issue["repository_url"].rsplit("/", 1)[-1],
        title=issue.get("title") or "",
        body_preview=body[:MAX_BODY_CHARS],
        state=issue.get("state") or "open",
        updated_at=issue.get("updated_at") or "",
        embedding=embedding,
    )


def _embedding_text(title: str, body: str) -> str:
    body_part = (body or "")[:MAX_BODY_CHARS]
    return f"{title or ''}\n\n{body_part}".strip()


def _apply_delta(cache: dict, issues: list[dict]) -> tuple[int, int, int]:
    """Update cache entries from a list of changed issues.

    Returns (added, updated, removed) counts.
    """
    added = updated = removed = 0
    for issue in issues:
        n = int(issue["number"])
        key = str(n)
        if issue.get("state") == "closed":
            if key in cache["entries"]:
                del cache["entries"][key]
                removed += 1
            continue
        existing = cache["entries"].get(key)
        text = _embedding_text(issue.get("title") or "", issue.get("body") or "")
        emb = _embed(text)
        entry = _build_entry(issue, emb)
        cache["entries"][key] = entry
        if existing is None:
            added += 1
        else:
            updated += 1
    return added, updated, removed


def reindex(repo: str, *, full: bool = False) -> ReindexResult:
    """Refresh the embeddings cache for `repo`.

    Args:
        repo: "owner/repo"
        full: if True, rebuild from scratch ignoring any existing cache.
              Otherwise do a delta sync from the cache's indexed_at.

    Returns:
        dict with: ok, repo, mode ('full'/'delta'/'skipped'),
                   added, updated, removed, indexed_at, total_entries
    """
    cache = _empty_cache() if full else _load_cache(repo)

    since = None
    mode = "full"
    if not full and cache.get("indexed_at"):
        age = _seconds_since(cache["indexed_at"])
        if age >= FULL_REBUILD_AFTER_SECONDS:
            cache = _empty_cache()
            mode = "full"
        else:
            since = cache["indexed_at"]
            mode = "delta"

    issues = _fetch_issues(repo, since=since, state="all")
    if mode == "full":
        cache["entries"] = {}

    added, upd, removed = _apply_delta(cache, issues)
    cache["indexed_at"] = _now_iso()
    _save_cache(repo, cache)

    return {
        "ok": True,
        "repo": repo,
        "mode": mode,
        "added": added,
        "updated": upd,
        "removed": removed,
        "indexed_at": cache["indexed_at"],
        "total_entries": len(cache["entries"]),
    }


def _auto_sync(repo: str) -> dict:
    """Run a delta sync if the cache is older than AUTO_SYNC_TTL_SECONDS.

    Returns a brief status dict (may be empty if nothing to do).
    """
    cache = _load_cache(repo)
    age = _seconds_since(cache.get("indexed_at"))
    if age >= AUTO_SYNC_TTL_SECONDS:
        return reindex(repo, full=(not cache.get("indexed_at")))
    return {
        "ok": True,
        "repo": repo,
        "mode": "skipped",
        "indexed_at": cache.get("indexed_at"),
        "total_entries": len(cache.get("entries", {})),
    }


@dataclass
class Match:
    number: int
    repo: str
    title: str
    body_preview: str
    state: str
    similarity: float
    meets_threshold: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number,
            "repo": self.repo,
            "title": self.title,
            "body_preview": self.body_preview,
            "state": self.state,
            "similarity": round(self.similarity, 4),
            "meets_threshold": self.meets_threshold,
        }


def find_similar(
    query_text: str,
    repo: str,
    *,
    top_k: int = 5,
    threshold: float = 0.35,
    min_results: int = 0,
    auto_sync: bool = True,
) -> list[Match]:
    """Return top-K semantically similar issues; optional cache auto-sync."""
    if auto_sync:
        _auto_sync(repo)

    cache = _load_cache(repo)
    entries: dict[str, IssueEntry] = cache.get("entries", {})
    if not entries:
        return []

    if np is None:
        msg = "numpy is required for similarity search (reinstall with: uv sync)"
        raise ImportError(msg)

    q = _embed(query_text)
    scored = sorted(
        ((float(np.dot(q, e.embedding)), e) for e in entries.values()),
        key=lambda t: t[0],
        reverse=True,
    )

    above = [(sim, e) for sim, e in scored if sim >= threshold]
    selected = above
    if len(selected) < min_results:
        below = [(sim, e) for sim, e in scored if sim < threshold]
        selected = above + below[: min_results - len(above)]
    selected = selected[:top_k]

    return [
        Match(
            number=e.number,
            repo=e.repo,
            title=e.title,
            body_preview=e.body_preview[:200],
            state=e.state,
            similarity=sim,
            meets_threshold=(sim >= threshold),
        )
        for sim, e in selected
    ]


def check_duplicate(
    title: str,
    body: str,
    repo: str,
    *,
    parent: int | None = None,
    related_issues: list[int] | None = None,
) -> DuplicateCheckResult:
    """Pre-flight duplicate check for create_issue.

    Returns recommendation (create|warn|block), match list with match_kind,
    and threshold flags. Hard matches against ``parent`` / ``related_issues``
    are downgraded to warn (structural relatives, issue #46).
    """
    structural: set[int] = set()
    if parent:
        structural.add(int(parent))
    if related_issues:
        # positive ints only — bad entries must not disable the duplicate guard
        structural.update(n for n in related_issues if type(n) is int and n > 0)

    query = _embedding_text(title, body)
    matches = find_similar(query, repo, top_k=5, threshold=DUPLICATE_SOFT_THRESHOLD)

    match_dicts = []
    for m in matches:
        d = m.to_dict()
        d["match_kind"] = "structural_relative" if m.number in structural else "candidate"
        match_dicts.append(d)

    any_hard = any(m.similarity >= DUPLICATE_HARD_THRESHOLD for m in matches)
    any_soft = any(m.similarity >= DUPLICATE_SOFT_THRESHOLD for m in matches)
    candidate_hard = any(m.similarity >= DUPLICATE_HARD_THRESHOLD and m.number not in structural for m in matches)
    downgraded_structural = any_hard and not candidate_hard
    if candidate_hard:
        rec: DuplicateRecommendation = "block"
    elif any_soft:
        rec = "warn"
    else:
        rec = "create"
    return {
        "ok": True,
        "matches": match_dicts,
        "any_above_hard": any_hard,
        "any_above_soft": any_soft,
        "downgraded_structural": downgraded_structural,
        "recommendation": rec,
        "hard_threshold": DUPLICATE_HARD_THRESHOLD,
        "soft_threshold": DUPLICATE_SOFT_THRESHOLD,
    }
