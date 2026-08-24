"""Test harness for running the REAL `zh` script under test.

The historical regression tests in `test_zh_bash_regression.py` embedded
parallel `_SNIPPET` strings that re-implemented production bash. The
snippet author had to keep the snippet byte-identical to production;
when production drifted, the snippet passed against itself and the
production bug shipped. The v1.9.1 round-4 finding ("envelope stub
returns 1 while production exits 1, snippet's `if cmd; then else` form
catches return-1 but production's exit terminates the shell") was a
textbook instance: the test passed against the snippet, but the same
behavior in production aborted the script. Six review rounds did not
catch it because every reviewer read the snippet, not production.

The fix is structural. v1.9.2 makes the `zh` bash script sourceable
(via a guarded `main "$@"` at the bottom) and this helper provides a
small harness for tests to:

  1. Source `zh` so every production `cmd_*` function is available.
  2. Optionally inject stub overrides for I/O helpers (`zh_graphql`,
     `gh`, `get_repo_info`, etc.) so tests can drive a real `cmd_*`
     with controlled inputs.
  3. Capture stdout, stderr, and exit code.

Stub functions are defined AFTER `source zh`, so they override
production's same-named functions — bash function definitions are
overwritten by later same-name definitions in the same shell. The
production `cmd_*` function then calls the stub, not the real
network-facing helper.

This is the canonical pattern for tests added from v1.9.2 onward.
Pre-v1.9.2 snippet tests remain in `test_zh_bash_regression.py` (they
still provide coverage and most of their drift risk is on jq
projections that have been stable for many rounds), but new tests
should target production via this runner.
"""

from __future__ import annotations

import atexit
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ZH_SCRIPT = REPO_ROOT / "zh"

# v1.9.2 round-4 #11: track isolated-HOME tempdirs and remove at exit so local runs don't accumulate dozens of scratch dirs.
_HARNESS_TEMPDIRS: list[str] = []


def _cleanup_harness_tempdirs() -> None:
    """atexit hook: remove every tempdir provisioned by the harness.

    `ignore_errors=True` so a dir already removed by a prior cleanup,
    a file the test process locked, or a permission glitch on shared
    CI tmpfs cannot fail the test suite at exit.
    """
    for path in _HARNESS_TEMPDIRS:
        shutil.rmtree(path, ignore_errors=True)


atexit.register(_cleanup_harness_tempdirs)


def run_zh_with_stubs(
    stubs: str,
    invocation: str,
    *,
    args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    stdin: str | None = None,
    cwd: str | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Source the real `zh` script, install stubs, then run `invocation`.

    The wrapper script that bash runs has three stages:

      1. Set required env vars so `load_config` and similar helpers do
         not try to touch real config / network.
      2. `source` the real `zh` script. Every production function is
         now defined in the current shell.
      3. `eval` the caller's `stubs` block. Stubs OVERRIDE same-named
         production functions because the latest `function name() {}`
         definition wins.
      4. `eval` the caller's `invocation` block. This is normally a
         single call to a production `cmd_*` function.

    Args:
        stubs: bash snippet defining stub functions (e.g.
            `zh_graphql() { printf '%s' "$STUB_RESPONSE"; }`). Can
            also set local shell vars the stubs read from.
        invocation: bash snippet that calls the production function(s)
            under test. Receives `"$@"` from the `args` list. Examples:
            `cmd_create "$@"`, `cmd_set_type 42 Epic`.
        args: positional args passed as `$1`, `$2`, ... to the
            invocation block.
        extra_env: additional env vars (overrides the defaults the
            harness sets).
        stdin: optional stdin text for the bash process.
        cwd: optional working directory; defaults to a temporary-ish
            location (the repo root, so `./zh` paths resolve).
        timeout: subprocess timeout in seconds.

    Returns:
        subprocess.CompletedProcess (returncode, stdout, stderr).
    """
    # ZH_TOKEN required; per-call isolated HOME defeats stray /tmp/.config/zh/config (round-3 #10).
    import tempfile

    _isolated_home = tempfile.mkdtemp(prefix="zh-test-home-")
    _HARNESS_TEMPDIRS.append(_isolated_home)
    env_defaults = {
        "PATH": "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin",
        "ZH_TOKEN": "test-token-do-not-use",
        "ZH_REPO": "acme/widgets",
        "ZH_WORKSPACE": "TestWS",
        # Per-call isolated HOME so load_config cannot source a stray config from another tenant.
        "HOME": _isolated_home,
        "NO_COLOR": "1",
        # Disable bkt: same-shell curl() stubs never run when bkt wraps zh_graphql reads.
        "ZH_BKT": "0",
    }
    if extra_env:
        env_defaults.update(extra_env)

    # Keep set -e armed after source — disabling it hid round-4/7 envelope-abort bugs.
    wrapper = f'source "{ZH_SCRIPT}"\n{stubs}\n{invocation}\n'

    cmd = ["bash", "-c", wrapper, "_"]
    if args:
        cmd.extend(args)

    # Allowlist env inheritance (round-4 #4): never pass through developer ZH_* secrets like ZH_REST_TOKEN.
    import os as _os
    import sys as _sys

    _ALLOWED_INHERIT = (
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_COLLATE",
        "LC_TIME",
        "LC_NUMERIC",
        "LC_MESSAGES",
        "TMPDIR",
        "TERM",
        "USER",
        "LOGNAME",
        "SHELL",
        "PYTHONIOENCODING",
    )
    inherited = {k: _os.environ[k] for k in _ALLOWED_INHERIT if k in _os.environ}

    # Inherit sanitized parent PATH (round-3 #8/#4): Nix/asdf shims win, but drop world-writable dirs.
    parent_path = _os.environ.get("PATH", "")
    safe_path_parts = []
    dropped_entries = []
    if parent_path:
        for entry in parent_path.split(":"):
            if not entry:
                continue
            try:
                st = _os.stat(entry)
            except OSError:
                continue
            # Drop world-writable PATH entries — sticky bit doesn't stop planted binaries (round-4 #4).
            mode = st.st_mode
            world_writable = bool(mode & 0o002)
            if world_writable:
                dropped_entries.append(entry)
                continue
            safe_path_parts.append(entry)
    # Optional breadcrumb when PATH filter drops entries (round-4 #5); gated on ZH_TEST_PATH_FILTER_VERBOSE.
    if dropped_entries and _os.environ.get("ZH_TEST_PATH_FILTER_VERBOSE") == "1":
        _sys.stderr.write(
            "_bash_runner: filtered "
            f"{len(dropped_entries)} world-writable PATH "
            f"{'entry' if len(dropped_entries) == 1 else 'entries'}: "
            f"{','.join(dropped_entries)}\n"
        )
    if safe_path_parts:
        inherited["PATH"] = ":".join(safe_path_parts)

    merged_env = {**inherited, **env_defaults}
    if "PATH" in inherited:
        merged_env["PATH"] = inherited["PATH"] + ":" + env_defaults["PATH"]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=merged_env,
        input=stdin,
        cwd=cwd or str(REPO_ROOT),
        timeout=timeout,
        check=False,
    )


def run_zh_function(
    func_name: str,
    args: list[str],
    *,
    stubs: str = "",
    extra_env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess:
    """Convenience wrapper: call a production function with args.

    Equivalent to `run_zh_with_stubs(stubs, f'{func_name} "$@"', args=args)`.
    Use this when the test only needs to invoke one `cmd_*` and doesn't
    need any inline pre/post bash.
    """
    return run_zh_with_stubs(
        stubs=stubs,
        invocation=f'{func_name} "$@"',
        args=args,
        extra_env=extra_env,
        stdin=stdin,
    )
