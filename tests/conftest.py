"""pytest fixtures for the zh Python package."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["ZH_MCP_SKIP_BOOTSTRAP"] = "1"
os.environ.setdefault("ZH_BKT", "0")

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest


@pytest.fixture(autouse=True)
def _reset_zh_caches() -> None:
    from zh.api import clear_api_caches
    from zh.graphql_cache import clear_process_read_cache
    from zh.workspace_ops import _cached_pipeline_nodes

    clear_api_caches()
    clear_process_read_cache()
    _cached_pipeline_nodes.cache_clear()
    yield
    clear_api_caches()
    clear_process_read_cache()
    _cached_pipeline_nodes.cache_clear()

# modules that import the removed bash CLI at collection time
collect_ignore = [
    "test_assign_unassign_safety.py",
    "test_verb_matrix.py",
    "test_zh_bash_regression.py",
    "test_zh_production_regression.py",
    "test_zh_gh_repo_id.py",
    "test_zh_auth_guidance.py",
]
