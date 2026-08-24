#!/usr/bin/env bash
# zh-draft-zed — open a ZenHub draft in Zed, wait for edits, print the final path.
#
# Hard Rule #6 helper: after the user chooses "Open in Zed to modify", run this
# instead of hand-rolling temp files + `zed -w`. When it exits 0, use the printed
# path with `zh create … -f` / `zh comment -f` / body update.
#
# Usage:
#   zh-draft-zed.sh [--kind issue|comment|body] [--title TITLE] [--keep] [FILE]
#   zh-draft-zed.sh --kind comment <<< "$draft"
#   printf '%s' "$body" | zh-draft-zed.sh --kind issue --title "My ticket"
#
# Behavior:
#   - If FILE is given, edit that path in place.
#   - Else write stdin (or an empty starter) to a temp file under ${TMPDIR:-/tmp}.
#   - Opens with `zed -w` (blocks until the tab/window for that path closes).
#   - On success: prints the absolute path on stdout (only). Hints go to stderr.
#   - Exit 1 if zed missing, empty after edit (unless --allow-empty), or zed fails.
set -euo pipefail

KIND="body"
TITLE=""
KEEP=0
ALLOW_EMPTY=0
FILE=""

usage() {
  cat >&2 <<'EOF'
zh-draft-zed — open a ZenHub draft in Zed, wait for edits, print the final path.

Usage:
  zh-draft-zed.sh [--kind issue|comment|body] [--title TITLE] [--keep] [--allow-empty] [FILE]
  zh-draft-zed.sh --kind comment <<< "$draft"
  printf '%s' "$body" | zh-draft-zed.sh --kind issue --title "My ticket"

On success, prints the absolute draft path on stdout (hints on stderr).
Use that path with: zh create … -f / zh comment -f / body update.
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kind)
      KIND="${2:?}"; shift 2 ;;
    --title)
      TITLE="${2:?}"; shift 2 ;;
    --keep)
      KEEP=1; shift ;;
    --allow-empty)
      ALLOW_EMPTY=1; shift ;;
    -h|--help)
      usage ;;
    --)
      shift; break ;;
    -*)
      echo "unknown option: $1" >&2; usage ;;
    *)
      FILE="$1"; shift; break ;;
  esac
done

if [[ $# -gt 0 ]]; then
  echo "unexpected args: $*" >&2
  usage
fi

if ! command -v zed >/dev/null 2>&1; then
  echo "zed not found on PATH — fall back to Proceed / Change only" >&2
  exit 1
fi

case "$KIND" in
  issue|comment|body) ;;
  *)
    echo "invalid --kind '$KIND' (want issue|comment|body)" >&2
    exit 2
    ;;
esac

CREATED=0
if [[ -z "$FILE" ]]; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  FILE="${TMPDIR:-/tmp}/zh-draft-${KIND}-${stamp}.md"
  CREATED=1
  if [[ ! -t 0 ]]; then
    cat >"$FILE"
  else
    {
      if [[ -n "$TITLE" ]]; then
        printf '# %s\n\n' "$TITLE"
      fi
      case "$KIND" in
        issue)
          printf '%s\n' "## Context" "" "(what / why)" "" "## Acceptance" "" "- [ ] …" ""
          ;;
        comment)
          printf '%s\n' "(comment draft)" ""
          ;;
        body)
          printf '%s\n' "(draft)" ""
          ;;
      esac
    } >"$FILE"
  fi
elif [[ ! -f "$FILE" ]]; then
  echo "file not found: $FILE" >&2
  exit 1
fi

# Resolve absolute path for a stable printout (macOS/BSD readlink -f is absent).
abs() {
  local d b
  d="$(cd "$(dirname "$1")" && pwd)"
  b="$(basename "$1")"
  printf '%s/%s\n' "$d" "$b"
}
FILE="$(abs "$FILE")"

if [[ -n "$TITLE" ]]; then
  echo "title (not in file unless you put it there): $TITLE" >&2
fi
echo "opening in Zed (close the tab when done): $FILE" >&2

zed -w "$FILE"
status=$?
if [[ $status -ne 0 ]]; then
  echo "zed exited $status" >&2
  exit "$status"
fi

if [[ ! -s "$FILE" && $ALLOW_EMPTY -eq 0 ]]; then
  echo "draft is empty after edit — aborting (pass --allow-empty to override)" >&2
  exit 1
fi

# Agent/caller consumes this path for `zh … -f`.
printf '%s\n' "$FILE"

if [[ $CREATED -eq 1 && $KEEP -eq 0 ]]; then
  echo "temp draft kept at $FILE (delete after zh apply, or re-run with --keep intentionally)" >&2
fi

exit 0
