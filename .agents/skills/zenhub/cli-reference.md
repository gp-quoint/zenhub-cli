# `zh` CLI Reference

This file is the agent-facing command surface for backlog work. Prefer it (and SKILL.md examples) over shell discovery. Run **`zh <command> --help`** only after a real flag miss or when the user asks whether a capability exists — not before every `edit`/`comment`/`move`. Do **not** use `zh help <command>` — the `help` subcommand does not take arguments. Full tree: `zh --help` (rare).

**Shell only.** All backlog operations go through `zh …`. Do not call the zenhub MCP server for work this skill covers.

---

## Invocation style

```bash
# Global flags peel off before any subcommand
zh -r owner/repo -w "Workspace Name" <command> …

# Root help vs per-command help
zh --help
zh create --help
zh epic create --help
zh comment edit --help

# Machine-readable output (many commands)
zh create "Title" … --json          # JSON on stdout; human info on stderr
zh -r org/repo --json board         # root --json applies to the command

# Body input (create, edit, comment add/edit, close, planning creates)
zh create "Title" -f body.md
zh create "Title" --stdin < body.md
zh edit 42 -t "New title" -f body.md
zh comment 42 -f comment.md      # -f/-m after the issue is fine (default add)
zh comment 42 -m "short note"
zh comment 42 "Fixed in PR #99"  # positional body
zh comment add 42 -f comment.md  # explicit add subcommand (same as bare comment)
zh comment 42                    # opens $EDITOR when no body/-m/-f/--stdin
zh edit 42                       # opens $EDITOR for title+body when no -t/-d/-f

# comment edit — same body flags as add (zh ≥ 1.12); bare still opens $EDITOR
zh comment edit 42 2 -f final.md
zh comment edit 42 2 -m "corrected note"
zh comment edit 42 2 --fill PYTHON_PR=https://github.com/org/py/pull/1 \
  --fill GO_PR=https://github.com/org/go/pull/1

# Close (agent) — prefer -f/--stdin for multi-line notes; --json for verify
zh close 41 -r completed -f /tmp/close.md --json
zh reopen 41 --json
```

**PRs:** there is no `zh pr` / `zh link`. Open with `gh pr create`; attach to a ZenHub issue via PR-body `owner/repo#N` (or full URL) plus `zh -r owner/issue-repo comment <N>` and/or deferred `--fill`. See [operation-patterns.md](operation-patterns.md)#link-prs-to-zenhub-issues. **`Closes`/`Fixes`/`Resolves` only auto-close on merge into the repo default branch** — after merge to `develop`/env branches, run `zh close` explicitly.

**Issue numbers:** `#` prefix optional (`42` or `#42`).

**Pipeline names:** case-insensitive **exact**, then **unique prefix**, then **unique substring** against `zh pipelines`. Ambiguous fragments error with the candidate list (`in` may uniquely hit `In Progress` via prefix; a shared character like `e` errors). Prefer the full quoted name in scripts.

**GitHub-backed scope:** issue numbers resolve through GitHub. **ZenHub-only cards** (no GitHub issue; `NoOwner/<repo>`, `…/issues/zh/<n>` URLs) are not reliably addressable — `1` resolves to GitHub #1, not `zh/1`. Manage those in the ZenHub web UI.

---

## Setup & config

| Requirement | Notes |
|---|---|
| **uv** | Launcher runs `uv run --project <checkout> python -m zh …` (isolates from ambient `UV_PROJECT_ENVIRONMENT` / `VIRTUAL_ENV`) |
| **Python 3.13+** | Managed by uv in the install checkout |
| **gh, jq, git** | GitHub auth via `gh auth status` |
| **~/.config/zh/config** | `ZH_TOKEN` (GraphQL); optional `ZH_REST_TOKEN`, `ZH_REPO`, `ZH_WORKSPACE` |

**Similarity search** (`zh similar`, duplicate pre-flight on creates) is a core dependency — installed with a normal `uv sync` / first `zh` run (pulls `sentence-transformers` + torch; model caches under `~/.cache/huggingface/`).

### Environment variables

| Variable | Purpose |
|---|---|
| `ZH_REPO` | Default `owner/repo`; overridden by `-r` |
| `ZH_WORKSPACE` | Default workspace name; overridden by `-w` |
| `ZH_TOKEN` | GraphQL API token |
| `ZH_REST_TOKEN` | REST token (required for `zh unblock` only) |
| `ZH_GRAPHQL_CACHE=0` | Disable on-disk GraphQL read cache (L1 in-process remains) |
| `ZH_GRAPHQL_CACHE_TTL` | L2 TTL (default `5m`) |
| `ZH_GRAPHQL_CACHE_FORCE=1` | Skip L2 for this process |
| `ZH_GRAPHQL_CACHE_DIR` | Override L2 directory |

L2 defaults to `~/.cache/zh/graphql`. If that path is not writable (e.g. Cursor sandbox without `additionalReadwritePaths`), zh **degrades to L1** and continues; it does not abort. To enable L2 under sandbox, add `~/.cache/zh` (and optionally `~/.cache/huggingface` for `zh similar`) to `~/.cursor/sandbox.json` → `additionalReadwritePaths`.

Precedence: **flag > env / config > git-remote + first-workspace fallback**. Use `-w` when a repo connects to multiple workspaces.

---

## Read operations (safe, fire-and-forget)

| Command | Purpose |
|---|---|
| `zh version` | Installed version |
| `zh board [--all] [--json]` | Per-pipeline issue counts (`--all` includes closed) |
| `zh pipelines [--json]` | Pipeline names (plain one-per-line output) |
| `zh pipeline "<name>" [--json]` | Issues in a pipeline (top = highest priority) |
| `zh issue <N> [--json]` | Full detail: GH body/comments **plus** workspace-scoped `pipeline`, `estimate`, `priority`, `zenhub_url`, `workspace_id`, **`blocked_by`** / **`blocking`** (`[{number, title, state?}, …]`), parent/sub-issue counts. Each comment has **`index`** (1-based) for `zh comment edit` |
| `zh mine [user] [--no-urls] [--json]` | Issues assigned to current or specified user |
| `zh users [--json]` | Assignable users (via `gh` collaborators; plain one-per-line output) |
| `zh workspaces [--json]` | Workspaces for the repo (● = active target) |
| `zh types [--json]` | Assignable issue types (name, level 1–5, disposition, source) |
| `zh priorities [--json]` | Workspace-configured priorities (name + color) |
| `zh labels [--json]` | Repository labels (plain one-per-line output) |
| `zh similar "<query>" [--json] [-k N] [-t threshold]` | Semantic duplicate search across open issues |
| `zh reindex [--full] [--json]` | Refresh similarity index (auto-syncs on `zh similar`; manual refresh rarely needed) |
| `zh epic list [--json]` | Epic-typed issues (`zh initiative list`, `zh project list`, `zh subtask list` — same surface) |
| `zh epic show <N> [--json]` | Epic detail + sub-issues |
| `zh subissue list <parent#> [--json]` | Sub-issues of a parent |
| `zh sprints [--all] [--json]` | Sprint list (● = active; `--all` includes closed) |
| `zh sprint [name] [--json]` | Sprint detail + issues (`name` → `show`; omit / `current` / `active` = current sprint) |
| `zh sprint show [name] [--json]` | Explicit show (same as above) |

---

## Write operations (issue lifecycle)

| Command | Notes |
|---|---|
| `zh create "<title>" …` | See flags below. Built-in duplicate pre-flight. |
| `zh type <N> <type-name>` | Change issue type (hidden aliases: `set-type`, `retype`) |
| `zh edit <N> [-t title] [-d|-b body] [-f file] [--stdin]` | Edit title/body; bare `zh edit N` opens `$EDITOR`. **No `--json`** — verify with `zh issue <N> --json` |
| `zh comment <N> [text] [-m text] [-f file] [--stdin]` | Add comment (default `add` subcommand). Flags may follow the issue. Bare `zh comment N` opens `$EDITOR` |
| `zh comment add <N> …` | Explicit add (same as bare `zh comment <N> …`) |
| `zh comment edit <N> [index] [-m text] [-f file] [--stdin] [--fill KEY=value] [--json]` | Edit your comment. **`index` is 1-based** (`comments[].index` from `zh issue --json`; never 0 / jq `to_entries` keys). Body flags (zh ≥ 1.12) for agents; `--fill` replaces `{{KEY}}`. `--json`: `{ok, unchanged, number, index, comment_id}`. Bare opens `$EDITOR` |
| `zh c <N> …` | Hidden add-only alias — **cannot** run `edit`; use `zh comment edit …` |
| `zh attach <N>` | Open issue in browser + print URL for drag-and-drop attachments (GitHub API has no upload) |
| `zh close <N> [comment] [-m text] [-f file] [--stdin] [-r completed\|not planned\|duplicate] [--json]` | Close issue. Prefer `-f`/`--stdin`/`-m` for multi-line agent notes; positional comment for one-liners. `--json`: `{ok, number, title, state, reason, comment_added, pipeline?}` (`pipeline` = prior workspace pipeline when available) |
| `zh reopen <N> [--json]` | Reopen closed issue. `--json`: `{ok, number, title, state}` |
| `zh delete <N> [-y]` | **DANGER** — permanent GitHub delete. `-y` skips interactive confirm. Prefer `zh close`. |
| `zh move <N> "<pipeline>" [--json]` | Move between pipelines. Human line shows workspace-scoped `from → to`. `--json`: `{ok, number, title, from, to}` (not unscoped `pipelineIssues[0]`) |
| `zh reorder <N> <position\|top\|bottom>` | Reorder within current pipeline (`top` = 1) |
| `zh estimate <N> <points\|clear>` | Set/clear story points |
| `zh assign <N> <user> [user…]` | Assign one or more users |
| `zh unassign <N> <user> [user…]` | Remove named assignee(s) only |
| `zh unassign <N> --all` | Remove all assignees (bare unassign with no user **errors**) |
| `zh priority <N> <name\|clear>` | Set priority by workspace-defined name (case-insensitive) |

### `zh create` flags

```
-t, --type           Issue type (discover with zh types)
-l, --labels         Comma-separated labels
-a, --assignee       GitHub assignee
-p, --pipeline       Target pipeline
-e, --estimate       Story points
-b, --body, --description  Issue body (top-level create only)
-f, --file, --body-file  Read body from file
--stdin              Read body from stdin
--parent <N>         Wire as sub-issue of parent
--priority <name>    Workspace priority at create time
--confirm-create     Bypass duplicate block (after user saw matches)
--skip-duplicate-check  Skip pre-flight entirely
--related-issues 1,2 Comma-separated structural-relative numbers (bulk-load)
--json               JSON on stdout
-q, --quiet          Emit only the new issue number
```

**`--json` success shape:** `ok`, `number`, `url` (GitHub), `github_url`, `zenhub_url`, `title`, `type`, `pipeline`, `estimate`, `parent`, `priority`, `priority_requested`, `duplicate_check`, optionally `partial_applied`.

Human create output prints both links after the success line:

```
✓ Created issue #1050: …
  ZenHub: https://app.zenhub.com/workspaces/…/issues/gh/owner/repo/1050
  GitHub: https://github.com/owner/repo/issues/1050
```

**`--json` blocked shape:** `{"ok": false, "blocked": true, "duplicate_check": {...}}`.

Compare `priority` vs `priority_requested` to detect a partial priority apply (safe to retry via `zh priority`).

---

## Write operations (relationships)

| Command | Notes |
|---|---|
| `zh block <blocked#> <blocking#> [--json]` | Set dependency (blocked BY blocking). `--json`: `{ok, blocked, blocked_title, blocking, blocking_title}` |
| `zh unblock <blocked#> <blocking#> [--json]` | Remove dependency. **Requires `ZH_REST_TOKEN`** (GraphQL cannot remove deps). `--json`: `{ok, blocked, blocking, removed: true}`. Missing edge → `Dependency not found between #A and #B` |

**Related ≠ blocked.** ZenHub has no "related" edge API — keep `Related: #N` in the issue body (Hard Rule #6). Use `zh block` / `zh unblock` only for the blockage graph. Discover/verify with `zh issue <N> --json` → `issue.blocked_by` / `issue.blocking`.

```bash
zh block 1047 1044 --json
zh unblock 1047 1044 --json
zh issue 1047 --json   # check issue.blocked_by / issue.blocking
```

---

## Write operations (planning hierarchy)

ZenHub's June 2025 model: **epics are normal issues typed Epic**; children attach via sub-issues. Levels: Initiative (1), Project (2), Epic (3), Bug/Feature/Task (4), Sub-task (5).

Each level has an identical noun surface: `zh initiative`, `zh project`, `zh epic`, `zh subtask`.

| Subcommand | Purpose |
|---|---|
| `create "<title>" …` | Create typed issue (duplicate flags as `zh create`; body via `-d`/`-f`, not `-t`) |
| `list [--json]` | List issues of that type |
| `show <N> [--json]` | Detail + sub-issues |
| `add <parent#> <child#> […]` | Attach sub-issues (single API call) |
| `remove <parent#> <child#> […]` | Detach sub-issues |
| `update <N> [-t title] [-d body] [-f file]` | Edit title/body |
| `close <N> [comment] [-m|-f|--stdin] [-r reason] [--json]` / `reopen <N> [--json]` | Close / reopen (same body + `--json` surface as top-level) |
| `delete` | Stub — errors and points to `zh delete <N>` (no issue arg) |

Board-level Bug/Feature/Task: use `zh create -t <type>`. To delete any planning issue: `zh delete <N>` (DANGER).

---

## Write operations (sub-issues)

Sub-issues sit below regular issues (Epic → Issue → Sub-issue). **`zh subissue reorder` uses sibling-anchored positions**, not integer positions like `zh reorder`.

| Command | Purpose |
|---|---|
| `zh subissue add <parent#> <child#> […]` | Link sub-issues |
| `zh subissue remove <parent#> <child#> […]` | Unlink (child remains as standalone issue) |
| `zh subissue list <parent#>` | List children |
| `zh subissue reorder <child#> top\|bottom\|after <sib#>\|before <sib#>` | Reorder among siblings |

Hidden aliases: `subissues`, `sub`, `subissues`/`sub` as root typer names.

---

## Write operations (sprint membership)

| Command | Purpose |
|---|---|
| `zh sprint add <name\|current\|active> <issue#> […] [--json]` | Add issues to sprint |
| `zh sprint remove <name\|current\|active> <issue#> […] [--json]` | Remove issues from sprint |
| `zh sprint` / `zh sprint show [name]` / `zh sprint current` | Show sprint detail (default: current) |
| `zh sa …` / `zh sr …` | Top-level aliases for add / remove |

`zh sprint add current 42` is the natural form (subcommand first). `zh sprint current` still works via a default-`show` group. Requires **zh ≥ 1.11.0** for that layout (older builds stole `add` as a sprint name).

`--json` on add/remove: `{ok, sprint, issues, success_count, outcome, message}`.

Mutations report per-issue success/failure counts. GraphQL read caches are invalidated on every mutation, so a follow-up `zh sprint` / `zh pipeline` sees membership changes without `ZH_GRAPHQL_CACHE_FORCE=1`. If an add still fails, investigate via `zh sprint --json` — the API doesn't distinguish reasons (already-in-sprint, archived, ineligible).

**Not exposed:** sprint creation, date changes, or completion flows. Escalate to the user rather than hitting the API directly.

---

## Hidden aliases (still work)

| Visible | Hidden |
|---|---|
| `zh issue` | `i`, `show` |
| `zh mine` | `my` |
| `zh board` | `b`, `overview` |
| `zh pipeline` | `pipe`, `col` |
| `zh pipelines` | `pipes`, `p` |
| `zh move` | `mv`, `m` |
| `zh reorder` | `order`, `pos` |
| `zh estimate` | `est`, `points` |
| `zh priority` | `prio` |
| `zh comment add` | `c` (add-only — no `edit`) |
| `zh edit` | `e` |
| `zh type` | `set-type`, `retype` |
| `zh sprints` | `sp` |
| `zh sprint add` | `sa` (top-level) |
| `zh sprint remove` | `sr` (top-level) |
| `zh subissue` | `subissues`, `sub` (hidden typer names) |
| `zh epic` | `epics`; `zh initiative`→`initiatives`; `zh project`→`projects`; `zh subtask`→`subtasks`, `sub-task`, `sub-tasks` |

Prefer the visible forms in agent scripts for clarity.

---

## Similarity & duplicate detection

```bash
# Pre-draft duplicate check
zh similar "login fails after token refresh under load" --json

# Manual index refresh (rare)
zh reindex [--full] --json
```

- Phrase queries as **natural-language sentences** — they score higher than keyword lists.
- `matches[]` carries `similarity`, `meets_threshold`, optionally `match_kind` (`structural_relative`).
- `zh create` / planning `create` re-run the check at create time. See Hard Rule #5 in [SKILL.md](SKILL.md).

---

## Multi-repo workspaces

Output may show repo name per issue. Issue commands resolve numbers via the **current git checkout's repo** (`-r` overrides). Parent/sub-issue wiring across repos in one workspace requires running `zh` from each repo that owns the issue numbers being passed — or use the ZenHub web UI.
