---
name: zenhub
description: >-
  Manages ZenHub backlog operations via the uv-managed `zh` CLI: board surveys,
  sprint planning, ticket lifecycle (create/update/move/reorder/close), epic
  and sub-issue management, batch operations with audit-trail logging, sprint
  metadata, and semantic duplicate detection (`zh similar`) on new issues.
  Enforces project-specific filing conventions, propose-first handling of
  destructive operations, and draft-review (proceed / change / open in Zed)
  before issues, comments, or other authored content lands; prefers
  AskQuestion (or equivalent) for decision gates; ships concise Issue / Task /
  Bug body templates. Use when working with ZenHub or the `zh` CLI, or when
  asked to survey a board, plan a sprint, or create or manage tickets/epics/
  sub-issues.
---

# ZenHub — Backlog Operations via `zh`

Manage ZenHub backlogs with the installed **`zh` CLI** (Python + uv) as a black box. Use shell `zh …` for **all** operations — do **not** use the zenhub MCP server.

Do **not** open, edit, clone, or otherwise depend on `zh`'s internals during backlog work. If a needed capability is missing from this skill's docs **and** from `zh <cmd> --help` after a real miss, escalate to the user — do not try to extend the tool from source in a backlog session (CLI maintenance is a separate, explicit task).

## Lean session bootstrap (token hygiene)

Agents waste tokens when every `/zenhub` turn starts with discovery shells. **Do not** ritualistically run:

```bash
zh version && zh --help | head …
zh edit --help   # or create/comment/move/issue --help "just to be sure"
rg -i zenhub|filing|workspace AGENTS.md README.md docs/ …
git remote -v; git branch; git log --oneline -5
zh workspaces; zh pipelines; zh pipeline "…"   # fan-out just to find one ticket
```

**Trust the skill docs first.** Common lifecycle flags are already in this file, [cli-reference.md](cli-reference.md), and [operation-patterns.md](operation-patterns.md) — e.g. `zh edit <N> -t "…" -f body.md` then `zh issue <N> --json`. Do **not** re-discover those via `--help` before every write.

| Situation | Do this | Skip |
|---|---|---|
| Ticket id known (`#1044`, branch `1044-…`, `Tracked in owner/repo#N`) | One targeted write/read: `zh -r owner/repo -w "…" move 1044 Blocked --json` or `zh issue 1044 --json` | version/help, repo greps, git log, listing every pipeline |
| Edit title/body (known pattern) | Draft → Hard Rule #6 → `zh edit <N> -t "…" -f body.md` → verify `zh issue <N> --json` | `zh edit --help` |
| Comment / move / create (documented in skill) | Use the examples in this skill / operation-patterns | per-command `--help` "to confirm flags" |
| Need "where is this ticket?" | `zh -r … -w … issue N --json` (includes **pipeline**, estimate, priority, ZH+GH URLs) | `zh pipeline` over every column |
| Need board overview | `zh board` (and maybe one `zh pipeline` / `zh mine`) | full help dump |
| First write in an unfamiliar project, **no** Engram/AGENTS filing notes | Read project conventions once (Engram → AGENTS/`CLAUDE.md` filing section); ask if missing | repeating that scan every turn |
| Real flag/`--json` failure, or user asks "can zh …?", or flag absent from skill docs | `zh <that-command> --help` only | `zh --help` whole tree + `zh version` + preemptive help |
| Suspected missing feature after a real error | `zh version` once, then escalate or use fallback | version check on every turn |

**Default move (+ optional block reason comment):**

1. Resolve `-r` / `-w` from config, Engram, or known project convention (e.g. Collection for `QuoIntelligence/quollection`) — not by probing every workspace every time.
2. `zh -r … -w … move N "<Pipeline>" --json` → trust workspace-scoped `from` / `to`.
3. If a reason comment is needed → Hard Rule #6 draft → `zh comment N -f …`.
4. Only if move JSON looks wrong (unexpected `from`, or `to` ≠ requested) → one `zh issue N --json` to re-check; do not pre-scan pipelines.

`from` / `to` are **workspace-scoped**. Repos on multiple ZenHub workspaces used to report the wrong board when the CLI read unscoped `pipelineIssues[0]` — current `zh` uses `pipelineIssue(workspaceId:)`. Trust `--json`; do not "verify" by listing all pipelines unless something contradicts intent.

## CLI invocation (Typer)

```bash
zh -r owner/repo -w "Team" board   # global flags before subcommand
zh edit 36 -t "New title" -f body.md   # title and/or body; then zh issue 36 --json
# zh create --help           # ONLY after a real miss / unknown flag — NOT `zh help create`
# zh --help                  # only when exploring an unfamiliar command family
```

- **Body input:** prefer `-f <file>` (works after the issue number: `zh comment 42 -f notes.md`). Also `--stdin`; create/edit use `-b`/`-d`; **comment add** and **comment edit** accept `-m` / `-f` / `--stdin`. Bare `zh comment <N>` / `zh edit <N>` / `zh comment edit <N>` opens `$EDITOR` — avoid in non-interactive agent sessions unless intentional.
- **`zh comment edit` body flags (zh ≥ 1.12):** `-m` / `-f` / `--stdin` replace the whole comment; `--fill KEY=value` (repeatable) replaces `{{KEY}}` in the existing body (or in the `-m`/`-f`/`--stdin` body). Prefer `--fill` for deferred PR URL fill after `gh pr create`.
- **No `zh pr` / `zh link`:** linking PRs to issues is GitHub + a comment — see [operation-patterns.md](operation-patterns.md)#link-prs-to-zenhub-issues. Create PRs with `gh pr create`, then notify or fill the issue comment with final URLs.
- **Machine output:** `--json` on stdout (human info on stderr) where supported; `-q` emits only the new issue number on create. Prefer `--json` on writes agents must verify (`zh move … --json`, `zh sprint add … --json`). **`zh edit` has no `--json`** — apply with `-f`/`-t`/`-d`, then verify via `zh issue <N> --json`.
- **Nested subcommands:** `zh sprint add current 42`, `zh comment edit 42 [index]`, `zh epic create "Title"`. Comment add is the default: `zh comment 42 …` ≡ `zh comment add 42 …`. Sprint show defaults similarly: `zh sprint` / `zh sprint current` ≡ `zh sprint show current`.
- **Sprint membership:** `zh sprint add current 42` and `zh sa current 42` both work. Prefer the explicit form in scripts.
- **Pipeline moves:** `zh move 42 "In Progress"` or unique prefix/substring (`zh move 42 progress`). `--json` returns `{ok, number, title, from, to}` with the **workspace-scoped** prior/new pipeline. Mutations invalidate GraphQL read caches (in-process + on-disk gen), so a follow-up `zh pipeline` / `zh sprint` sees fresh state without `ZH_GRAPHQL_CACHE_FORCE=1`.
- **`zh c` vs `zh comment`:** `c` is add-only (no `edit` subcommand). Use `zh comment edit …` for edits.
- **`zh issue <N> [--json]`:** GitHub body/comments **plus** workspace-scoped `pipeline`, `estimate`, `priority`, `zenhub_url`, `workspace_id`. Prefer this over pipeline fan-out when locating one ticket.

## CLI setup

`zh` is a uv-managed Python CLI. The launcher (`zh` at the install root) runs `uv run --project <checkout> python -m zh …` when `uv` is on PATH, and clears ambient `VIRTUAL_ENV` / `UV_PROJECT*` / `PYTHONPATH` so direnv in another repo cannot steal the venv.

| Requirement | Notes |
|---|---|
| **uv** | Required to launch `zh` (`brew install uv` or [docs.astral.sh/uv](https://docs.astral.sh/uv/)) |
| **Python 3.13+** | Managed by uv in the install checkout |
| **gh, jq, git** | Same as before — GitHub auth via `gh auth status` |
| **~/.config/zh/config** | `ZH_TOKEN` (GraphQL); optional `ZH_REST_TOKEN`, `ZH_REPO`, `ZH_WORKSPACE` |

Install (typical): clone/symlink the checkout, put `zh` on PATH (e.g. `ln -sf ~/dev/github/gp-quoint/zenhub-cli/zh ~/.local/bin/zh`). First run syncs deps via uv automatically.

**Similarity search** (`zh similar`, built-in duplicate pre-flight on `zh create` / planning creates) is a core dependency — first `uv sync` / `zh` run pulls in `sentence-transformers` (+ torch). First embedding load also caches the model under `~/.cache/huggingface/` (~80MB).

**Version:** VCS-derived (`hatch-vcs`); do not expect a static string in `pyproject.toml`. Agents should **not** run `zh version` every turn — see Lean session bootstrap. Human install verify (once): `zh version`, `zh similar "login bug" --json`. Check version only after a real capability miss (`comment edit --fill`, workspace-scoped move/`issue` pipeline fields, etc.).

`zh` has a wide command surface (issue ops, epic ops, sprint ops, board surveys) and each project has its own filing conventions, so recurring tasks (sprint planning, grooming, batch cleanups) benefit from a consistent playbook rather than being re-derived every session.

## What this covers

1. **Board surveillance** — answer "what's the state?" without running 6+ raw `zh` commands. Pipelines, counts, what's assigned, what's in flight, what's stuck.
2. **Sprint planning** — survey Sprint Backlog + top of Product Backlog, propose next-sprint candidates by size / dependencies / priority / assignee availability. Check for blocked or stale items.
3. **Ticket lifecycle** — create / update / move / reorder / close / assign with appropriate audit-trail comments. Respect project-specific filing rules.
4. **Epic management** — create, restructure, manage memberships, close. Wraps the `zh epic` family.
5. **Batch operations** — wave-style execution: pre-check current state → act → post-check → log to per-session audit YAML.
6. **Sprint metadata** — set sprint dates, assign tickets to sprints, mark sprint complete. Only when the project actively uses ZH sprints (not all do).
7. **Duplicate detection** — semantic similarity search (`zh similar`) before drafting / creating tickets, to catch paraphrased duplicates keyword search misses.

## When NOT to use this

- Pure `gh` CLI operations unrelated to ZenHub (e.g., PR diffs, repo metadata) — use `gh` directly.
- Code edits unrelated to ZenHub backlog work — use direct file tools.
- Writing audit-trail notes outside of ZenHub context — use direct file edits.
- Non-ZH project questions ("who's on the team", "what's the deploy status") — use the appropriate domain-specific source.
- Developing or patching `zh` itself — out of scope; escalate missing capabilities to the user.

## Reference files

- [cli-reference.md](cli-reference.md) — full `zh` command surface (read/write ops, aliases, repo/workspace targeting, similarity search). Read before any non-trivial operation to confirm the exact flags/aliases. Prefer `zh --help` / `zh <command> --help` when unsure — the installed binary is authoritative.
- [operation-patterns.md](operation-patterns.md) — concrete workflows: board surveillance, sprint planning, ticket/epic/sub-issue lifecycle, batch "wave" pattern, structured-plan bulk-load with `depends_on` forwarding, sprint metadata.
- [issue-templates.md](issue-templates.md) — concise Issue / Task / Bug body templates (default when drafting).
- [scripts/zh-draft-zed.sh](scripts/zh-draft-zed.sh) — Hard Rule #6 helper: open a draft in Zed (`-w`), wait for edits, print the path for `zh … -f`.

---

## Prefer AskQuestion (AskUser) for decisions

Whenever this skill needs an explicit user choice — draft-review, duplicate handling, propose-first go-ahead, missing project conventions, ambiguous escalations — **prefer the AskQuestion tool** (also known as AskUser in some hosts).

- Use a single-select (or multi-select when several independent choices apply) with short, concrete options.
- Put the draft / summary in chat; put the **decision** in AskQuestion.
- If AskQuestion / AskUser is unavailable, ask conversationally with the **same** labeled options — do not invent a different menu.

Canonical AskQuestion menus:

| Gate | Options (labels) |
|------|------------------|
| Hard Rule #6 draft-review | `Proceed` · `Change` · `Open in Zed` |
| Hard Rule #5 hard duplicate (≥0.70) | `Abandon` · `Comment on #N` · `File related` |
| Hard Rule #5 blocked create | `File anyway` · `Abandon` · `Link / comment elsewhere` |
| Hard Rule #2 propose-first | `Go ahead` · `Revise plan` · `Cancel` |

One question per gate. Do not bury Proceed/Change/Zed inside free-form prose when AskQuestion is available.

---

## Hard rules (never override)

### 1. Never auto-close via `Closes #N` for internal task IDs

GitHub's parser sees `Closes #400` (or `Fixes #400`, `Resolves #400`) in a commit message or PR description, and auto-closes issue #400 in the same repo when the commit/PR lands on the default branch. There is NO disambiguation — any `#N` reference resolves to a same-repo issue if one exists with that number.

For internal local task IDs that may collide with real GitHub issue numbers, use a notation GitHub can't parse:
- `[task 400]` (bracketed, no `#`)
- `internal-id 400`
- Spell it out: *"addresses the X→Y flow fix"* instead of `#400`

A real-world incident this rule guards against: a project used internal task IDs `#369`–`#411` in commit messages for traceability. Those numbers all existed as real GitHub issues in the same repo covering unrelated work. When the PR merged, GitHub auto-closed **10 unrelated tickets**. Recovery was a manual `gh issue reopen` on each.

**`#N` is reserved for real GitHub issues in that repo. Never use it for any foreign ID.** The same parser that auto-closes also auto-LINKS: any `#N` in an issue/epic body or comment renders as a link to GitHub issue N in the current repo. So when authoring bodies or comments, never write `#<number>` to reference:
- a ZenHub-only card (one with no GitHub issue behind it), or
- any other foreign identifier (a ZenHub object id, a tracker ticket from another system).

Doing so 404s if no such GitHub issue exists, or wrongly links to (or closes) an unrelated real issue that happens to share the number. Reference foreign objects by NAME plus a full, correct URL instead. Note that in the modern model an epic IS a real GitHub issue, so an epic's own `#number` is a legitimate `#N` reference; this rule is about ZenHub-only cards and non-GitHub identifiers, not about epics.

**Cross-repo ZenHub tickets (common):** when the tracked issue lives in another repo (e.g. `QuoIntelligence/quollection#1044` while PRs are in `data-team-*-libs`):
- In the **PR body**, link with `owner/repo#N` or the full `https://github.com/owner/repo/issues/N` URL — never bare `#N` (wrong repo) and never `Closes #N` / `Fixes #N` unless that exact issue is in the **PR's** repo and should auto-close on merge.
- Prefer `Tracked in owner/repo#N` (or "Related to") when the issue spans multiple PRs/repos — leave auto-close for when the whole ticket is actually done.
- Notify the issue with PR URLs via either:
  1. **Preferred (single comment):** post once **after** `gh pr create` with final URLs (`zh -r owner/issue-repo comment <N> -f …`), or
  2. **Deferred fill (zh ≥ 1.12):** post early with `{{PLACEHOLDERS}}`, then `zh comment edit <N> <index> --fill KEY=url …` once URLs exist.

### 2. Propose-first for ALL destructive operations

Destructive = anything that's hard to undo or visible to the team. Specifically:
- Closing tickets (any closure with a comment is announced to watchers)
- Deleting epics or issues
- Bulk moves (>3 tickets at once)
- Body rewrites (the team reads the body)
- Bulk reorders (>5 ticket positions)
- Closing or deleting any ZenHub epic
- Anything that fires Slack notifications via GH webhooks

Propose-first protocol:
1. Draft the planned operations as a YAML or markdown summary
2. Present to the user with: what / why / what the new state will be / how to undo if it goes wrong
3. AskQuestion: **Go ahead** / **Revise plan** / **Cancel** — wait for explicit go-ahead
4. Execute with pre-check / action / post-check pattern per ticket
5. Report back with the outcome (success counts, drift observations, links)

Safe operations (can fire directly once content is approved — no destructive propose-first):
- All read operations
- Creating new tickets with no auto-close-trigger risk (still subject to Hard Rule #5 + Hard Rule #6)
- Adding comments (still subject to Hard Rule #6)
- Single-ticket moves
- Single-ticket reorders
- Adding tickets to epics
- Setting assignees / estimates / priorities

**Don't loop-bypass an approval hook across a batch.** If a shell/tool-level approval hook blocks a destructive call (e.g. a smart-mode classifier flags `gh issue close`/`zh close`/`zh delete`), that block is itself a signal the operation needs real human confirmation — not a speed bump to push through with an auto-approval override. This is especially true when the block fires on a **fallback path** (e.g. "deletion isn't authorized, falling back to close-as-not-planned") that changes the nature of the operation from what was originally scoped. Concretely: don't call the override once and then silently reuse it for the remaining N-1 items in the same batch. Instead, stop after the first block, surface the exact block reason plus the revised plan (what changed, why, the full batch it now applies to) to the user, and get one explicit go-ahead for the whole batch before resuming. Only then is it reasonable to apply the same override across the rest of the batch without re-asking per item.

### 3. Always read project memory before acting on a project

Every project has filing conventions — which repo new tickets go to when a workspace spans multiple repos, what pipelines exist, what labels are used, the team's announcement channel, the in-flight epic structure. These belong in project-level instructions (e.g. an `AGENTS.md`/`CLAUDE.md` in the project repo, or a per-project memory/rules file).

**Before any write operation:** read the relevant project memory/rules. If unsure what project is meant, ASK rather than guess.

If the project has no documented conventions yet, ask the user to capture them on first use — see "Adding a new project" below for the minimum needed.

### 4. Batch operations require an audit trail

For any batch of >5 write operations, log to a per-session audit YAML in the project's working notes directory. Capture at minimum:
- Timestamp
- What was done (operation type, target ticket/epic numbers)
- Before state vs after state (for state-changing ops)
- Closing-comment text (full, because GitHub only stores it on the issue)
- Drift observations (anything that didn't match expectation)
- Any rollback notes

This is the durable record — anyone asking "why was ticket #X closed?" six months later should be able to grep the YAML.

### 5. Check for duplicates before drafting a new ticket

Motivating case: a "Users randomly logged out around 5pm" ticket was filed without noticing an "Auth token refresh race condition under load" ticket already tracked the root cause — zero shared keywords, same bug. The duplicate cost coordination effort and confused backlog ordering.

**Pre-draft check (always):** before drafting a full ticket body, run semantic search on the candidate title (+ a one-sentence summary of the body if available):

```bash
zh similar "<title and one-sentence summary>" --json
```

Parse `matches[]` for `similarity` scores and `meets_threshold` flags — apply these judgment bars (your decision thresholds, independent of the tool's lower `meets_threshold` cutoff which just flags "worth a glance"):

- **Top match >= 0.70 cosine** ("almost certainly a duplicate"): do NOT proceed to drafting. Present the match in chat, then AskQuestion: **Abandon** / **Comment on #N** / **File related**. Wait for explicit decision.
- **Top match 0.55–0.70** ("probably related, possibly distinct"): proceed to drafting BUT include the candidate matches at the top of the proposed ticket draft, then AskQuestion with Hard Rule #6 options (and note related #N / #M in the prompt).
- **Top match < 0.55**: proceed normally.

If `zh similar` fails (similarity extra not installed, or other error), fall back to a keyword scan: `zh board`, relevant `zh pipeline "…"`, and `zh mine` / targeted `zh issue N` reads. Say clearly that the check was keyword-only, not semantic.

**Handling `zh create` blocked by pre-flight:** `zh create` (and `zh epic create`, `zh initiative create`, `zh project create`, `zh subtask create`) run a built-in duplicate check. When it refuses with *"Refused: similar open issue exists"*, or when `--json` returns `{"ok": false, "blocked": true, "duplicate_check": {...}}`, a high-similarity match (>= 0.70) was caught. Do NOT just retry with `--confirm-create`. Instead:

1. Read `duplicate_check.matches` — the top candidates with scores (or re-run `zh similar` on the final title+body)
2. Re-present them (the candidates may be more relevant than the pre-draft check surfaced if the body changed the match)
3. AskQuestion: **File anyway** (`--confirm-create`) / **Abandon** / **Link / comment elsewhere**

`--confirm-create` should ONLY be set after the user has seen the matches and explicitly chosen **File anyway**.

**Same gate on planning-noun creates:** `zh epic create`, `zh initiative create`, `zh project create`, and `zh subtask create` run the identical duplicate-check pre-flight. Handle a blocked response the same way.

**Soft-match warnings:** when `zh create --json` returns `ok=true` with `duplicate_check.recommendation == "warn"` and soft matches present, the ticket was created but tangentially related tickets exist — include them in the post-create report.

**Override carefully in bulk operations:** filing many genuinely distinct tickets in a known-clean batch (e.g. wave creation after auditing the backlog) — `--skip-duplicate-check` is reasonable per-call. Document the choice in the batch audit YAML.

**Structural relatives don't block:** creating a child under a parent (`--parent N`) expects a hard match against that parent (a parent whose body enumerates children scores high against each child). The pre-flight tags this `match_kind="structural_relative"` and downgrades block → warn (`duplicate_check.downgraded_structural=true`). Prefer `--parent N` over `--confirm-create` for this case. For a bulk-loaded structured backlog where siblings/dependencies also cross-match, pass `--related-issues 1,2,3` (see [operation-patterns.md](operation-patterns.md)). Genuine (non-structural) hard matches still block and must be surfaced.

Run the pre-draft `zh similar` check even though `zh create` re-checks — the pre-draft gate prevents wasted drafting on obvious duplicates.

### 6. Draft-review before authored content lands

Any user-visible authored text must be reviewed before it is posted or created. This covers:

- New issues / epics / initiatives / projects / subtasks (title + body)
- Comments (including closing comments)
- Body rewrites / title changes
- Batch announcement copy or any other multi-line text that will land on GitHub/ZenHub

**Protocol (always, unless the user already supplied final copy and said to post as-is):**

1. Draft the content (after Hard Rule #5 when creating). For new tickets, use the templates in [issue-templates.md](issue-templates.md) — pick Issue / Task / Bug by type; keep bodies short.
2. Present the full draft to the user (title + body in chat).
3. AskQuestion (preferred) with exactly these options:
   - **Proceed** — post/create with the draft as shown
   - **Change** — user gives edits in chat; revise the draft and re-offer this choice
   - **Open in Zed** — write the draft to a temp file, open it with `zed -w <file>`, wait for the editor to close, re-read the file, then apply (create / comment / update) with the edited content
4. Do not call `zh create` / `zh comment` / body-update tools until the user chose Proceed, or chose Zed and closed the editor (or finished a Change cycle that ends in Proceed / Zed).
5. After a successful create, report **both** links from the CLI output (or `--json` fields `zenhub_url` and `github_url` / `url`) so the user can open either the board view or the GitHub issue.

**Zed path details:**

Prefer the skill helper (blocks on `zed -w`, prints the final path on stdout):

```bash
# From a prepared draft file:
~/.agents/skills/zenhub/scripts/zh-draft-zed.sh --kind issue --title "My ticket" /tmp/zh-draft-body.md
# Or pipe the draft:
printf '%s' "$BODY" | ~/.agents/skills/zenhub/scripts/zh-draft-zed.sh --kind comment
# Capture path, then apply:
BODY_FILE=$(…/zh-draft-zed.sh --kind comment /tmp/zh-draft-comment.md)
zh comment <N> -f "$BODY_FILE"
```

Manual equivalent if the script is unavailable:

```bash
zed -w /tmp/zh-draft-issue-body.md
# `-w` blocks until the tab/window for that path is closed.
# Then re-read the file and run zh create / zh comment / update with -f.
```

- Prefer `-f <file>` for the resulting `zh` write so the edited file is the source of truth.
- For issues: put the body in the temp file; keep the title in chat (or pass `--title` so the script echoes it on stderr). After Zed exits, re-show a one-line title + confirm you will apply, then apply — do not re-open the full Proceed/Change/Zed menu unless the user asks.
- Shell: use a long enough wait (`block_until_ms`) for `zh-draft-zed.sh` / `zed -w`; the user may edit for minutes. Do not treat a long wait as a hang.
- After a successful apply, delete the temp draft unless the user wants to keep it (`--keep` only suppresses the delete reminder).
- If `zed` is unavailable, the script exits 1 — say so and fall back to Proceed / Change only.

This gate is independent of Hard Rule #2: creates and comments are still "safe" once approved, but they are never silent.

---

## Project-specific conventions

Populate this per project. ALWAYS check project memory/rules before write operations.

### Conventions to capture per project

1. **Filing rule** — when a workspace spans multiple GitHub repos, which repo do new tickets default to? Exceptions?
2. **Announcement channel** — Slack channel ID for batch operation announcements.
3. **Active epics** — current epic structure, so new tickets get linked to the right parent.
4. **Sprint Backlog ordering convention** — smallest→largest (onboarding-friendly) vs priority order (execution-focused).
5. **In Progress pipeline policy** — actively-assigned work only, or also epic anchors?
6. **Filing convention notes** — anything litigated and resolved (e.g. *"all admin-panel work goes to the app repo even if it touches server, because branching is easier"*).

Capture in a project-level `AGENTS.md`/`CLAUDE.md`, or a project-scope rules/memory file.

### Adding a new project — checklist

1. Find or create the project's memory/rules location.
2. Add a note capturing where tickets go by default + any exceptions.
3. Record the canonical epic list as epics are created.
4. Reference this skill from the project's rules so future sessions know it exists and what it expects.

---

## Output style

- Board surveys: digestible summaries (counts, top-of-pipeline, anomalies). NOT raw `zh` output dumps.
- Sprint planning: tables with ticket / size / why-this-pick.
- Batch operations: progress per sub-batch with success/fail counts + drift notes. Final summary table.
- Lifecycle operations: brief confirmation with the new state + **both** ZenHub and GitHub URLs (from `zh create` / planning create human output, or `zenhub_url` + `github_url` / `url` in `--json`).
- Match the user's communication style: short and direct unless a complex tradeoff needs discussion.

## When to escalate to the user

- Any destructive operation that hasn't been pre-approved
- Project memory/conventions are missing for the project being worked on
- Drift observation: ticket state contradicts the plan (e.g., already closed when expected open, in wrong pipeline)
- A `zh` operation fails twice with the same error
- ZenHub GraphQL returns rate-limit warnings
- The current action needs a `zh` capability that isn't in `zh --help`
- Cross-project decisions (e.g., "this rule should apply to project A AND project B — should we update both?")
- A duplicate-check match in the 0.55–0.70 band where the relationship is genuinely ambiguous — don't guess
- Authored content ready to land — always AskQuestion Proceed / Change / Open in Zed (Hard Rule #6) unless the user already gave final copy and said to post as-is

Never assume escalation can be skipped because "it's probably fine." Prefer AskQuestion; fall back to chat with the same options.
