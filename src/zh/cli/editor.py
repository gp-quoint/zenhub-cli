"""Interactive $EDITOR helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from zh.api import ZhApiError


def edit_text(initial: str = "", *, suffix: str = ".md") -> str | None:
    """Open ``$EDITOR`` on *initial* content; return edited text or ``None`` if cancelled."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    tmpdir = tempfile.mkdtemp(prefix="zh-edit-")
    path = Path(tmpdir) / f"buffer{suffix}"
    try:
        path.write_text(initial, encoding="utf-8")
        subprocess.run([editor, str(path)], check=False)
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ZhApiError(f"failed to run editor {editor!r}: {exc}") from exc
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    stripped = text.rstrip("\n")
    if not stripped and not initial.strip():
        return None
    return stripped
