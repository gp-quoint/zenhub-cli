# Operation Patterns

All operations use **shell `zh …`**. See [cli-reference.md](cli-reference.md) for flags; use **`zh <command> --help`** when unsure.

---

## Board surveillance

For "what's the state?" queries:

```bash
zh board                          # high-level counts
zh pipeline "Sprint Backlog"      # what's queued for the team
zh pipeline "In Progress"         # what's actively being worked
zh mine                           # what's assigned to current user
zh epic list                      # all epics + state
zh issue <N> --json               # one ticket: pipeline + body + ZH/GH URLs (prefer over pipeline fan-out)
zh subissue list <parent#>        # drill into a parent's sub-issues
```

Do **not** start with `zh version` / full `--help` / repo greps — see Lean session bootstrap in [SKILL.md](SKILL.md).

Report the digest, not the raw output. Surface: total open, pipeline distribution, anything that looks stuck (assigned & old without movement, blocked items, anything in In Progress with no recent commits). For 3-tier-using projects, also surface: epics with parent-issues that have unstarted sub-issues, and any orphan sub-issues whose parent has been closed.

---

## Sprint planning

When asked to propose a next sprint:

1. Read current Sprint Backlog (what's already there)
2. Read top of Product Backlog (next-up candidates per pipeline ordering)
3. Check each candidate's:
   - Story-point estimate (if set)
   - Assignee (already taken or open)
   - Dependencies (`zh issue N` shows blockers)
   - Epic membership (sprint coherence)
   - Parent / sub-issue relationships (`zh issue N` shows them). For a parent with sub-issues, decide whether to pull just the parent (the team will fan out), pull all sub-issues, or split across sprints. For an orphan sub-issue, surface its parent's status so the team can decide whether to defer until the parent is groomed.
4. Propose: which tickets to pull into the sprint, in what order, with rationale (size, dependency, who owns)
5. Surface anything in Sprint Backlog that's been there too long without progress (stale = >2 sprints)
6. If the project uses ZH sprints (with dates), propose sprint duration + start/end and which tickets to assign

DO NOT actually move tickets into a sprint without explicit go-ahead — sprint composition is a team decision.

---

## Ticket lifecycle

For routine operations:

- **Create**: `zh create "<title>" -t <type> -p "<pipeline>" -f <body_file>`. Default type is `Task` unless the work is clearly a `Feature` (multi-AC, multi-week) or `Bug` (regression). Default pipeline is `Product Backlog` unless told otherwise.

  **Always run the duplicate-check flow first** (see Hard Rule #5 in [SKILL.md](SKILL.md)):
  1. `zh similar "<title and one-sentence summary>" --json` — surface existing tickets that already track this work. If similarity extra is missing, keyword-scan via `zh board` / pipelines and say so.
  2. If top match ≥ 0.55: present matches and decide together (abandon / link / file anyway)
  3. If clear or after explicit go-ahead: draft title + body from [issue-templates.md](issue-templates.md), then run **Hard Rule #6** via AskQuestion (Proceed / Change / Open in Zed). Only after approval:

  ```bash
  zh create "<title>" -t Task -p "Product Backlog" -f /tmp/body.md
  # batch callers:
  zh create "<title>" … --json    # parse stdout; stderr has human chatter
  zh create "<title>" … -q        # emit only the new number
  ```

  `zh create --json` re-runs duplicate check as a safety net. On `{"ok": false, "blocked": true, "duplicate_check": …}`, surface matches and AskQuestion (**File anyway** / **Abandon** / **Link / comment elsewhere**) before retrying with `--confirm-create`.

- **Edit title/body**: draft + Hard Rule #6 for body rewrites (Hard Rule #2). Then `zh edit <N> -t "…" -f body.md` or `zh edit <N> -f body.md`. **`zh edit` has no `--json`** — confirm the rewrite with `zh issue <N> --json`. Bare `zh edit N` opens `$EDITOR` — avoid in non-interactive agent sessions.
- **Comment**: draft first, then Hard Rule #6. Prefer `zh comment <N> -f <file>` (flags after the issue are fine; especially after a Zed edit). Use `-m` or a short positional string only for already-approved one-liners. Edit existing: `zh comment edit <N> [index] [-m|-f|--stdin|--fill …]` (zh ≥ 1.12). Not `zh c …` — the `c` alias is add-only.

---

## Link PRs to ZenHub issues

`zh` has **no** PR or link command. Pattern when the user asks to open a PR "linked to" a ZenHub/GitHub issue (often in a different repo than the PR):

1. Confirm the issue: `zh -r owner/issue-repo issue <N> --json` (title, state, URL).
2. Create the PR with `gh pr create` from the **implementation** repo. In the PR body include a non-closing cross-repo reference, e.g.:
   - `Tracked in QuoIntelligence/quollection#1044`
   - or the full `https://github.com/QuoIntelligence/quollection/issues/1044`
   - Use `Closes owner/repo#N` only when that issue is meant to auto-close on **this** PR's merge and lives in a repo GitHub will resolve (same-repo `Closes #N` is safest when applicable). Multi-PR / multi-repo tickets → prefer `Tracked in`, not `Closes`.
3. Notify the issue with PR URL(s) using one of:

   **A — Post after create (simplest):**

   ```bash
   zh -r owner/issue-repo comment <N> -f /tmp/pr-links.md
   # body lists final https://github.com/…/pull/N URLs
   ```

   **B — Deferred fill (zh ≥ 1.12):** post placeholders first, create PRs, then edit:

   ```bash
   zh -r owner/issue-repo comment <N> -m $'Opened PRs:\n- Python: {{PYTHON_PR}}\n- Go: {{GO_PR}}'
   # … gh pr create … capture URLs …
   zh -r owner/issue-repo comment edit <N> <index> \
     --fill PYTHON_PR=https://github.com/…/pull/1 \
     --fill GO_PR=https://github.com/…/pull/2
   ```

   Resolve `<index>` from `zh -r owner/issue-repo issue <N>` (1-based comment list). If you only have one own comment, omit index.

4. Return the PR URL(s) to the user.

**Anti-patterns:** leaving `{{PLACEHOLDERS}}` unfilled; bare `#N` in a PR whose repo is not the issue's repo; `Closes #N` that would close the wrong same-repo issue or never touch the ZenHub ticket; using ellipsis `…` placeholders without a later `comment edit`.

- **Close**: ALWAYS include a closing comment (draft + Hard Rule #6). Cite evidence (commit SHA, file:line, audit YAML pointer). Use `-r not planned` or `-r duplicate` when appropriate. Close itself remains propose-first under Hard Rule #2.
- **Move**: single ticket can fire directly (`zh move N "<Pipeline>" --json` — trust workspace-scoped `from`/`to`). Bulk moves (>3) → propose-first. Do not pre-scan every pipeline when the ticket number is known.
- **Reorder**: numeric positions or `top`/`bottom`. Bulk reorders apply position 1 first, then 2, etc. — each call computes from current state.
- **Assign**: free to fire directly.

---

## Epic management

- **Create** an epic: `zh epic create "Title" -d "body"` or `-f body.md`. Convention: prefix epic titles with a project tag for visibility in the workspace-wide epic list (document the prefix in project conventions). Draft title + body first, then Hard Rule #6 before create.
- **Add children**: `zh epic add <parent#> <issue#> [<issue#> …]` (batch in a single call; attaches sub-issues).
- **Restructure** (move children between epics): propose-first. Restructuring epic boundaries affects how the team views grouped work.
- **Close**: propose-first. Closing an epic doesn't close its children, but it does change board visibility.
- **Delete**: NEVER without explicit confirmation. An epic is an issue, so deletion is `zh delete <issue#>`, which is irreversible. Prefer close. (`zh epic delete` is a stub that errors — use top-level `zh delete`.)
- **Other levels**: `zh initiative`, `zh project`, and `zh subtask` expose the identical surface on their respective hierarchy levels; `zh type <issue#> <name>` retypes an existing issue (e.g. promote Task → Epic).

---

## Sub-issue management (3rd tier)

Sub-issues sit below regular issues (Epic → Issue → Sub-issue). Use this tier when a single Issue is too big for one ticket but doesn't justify being promoted to an Epic. Common patterns: a "Refactor X" parent with one sub-issue per file group; a "Wire up new dashboard widget" parent with sub-issues for backend, API, frontend, and tests.

- **Add children**: `zh subissue add <parent#> <child#> [<child#> …]` — batch in single call. Single-ticket adds can fire directly; bulk adds (>3) propose-first because they restructure the hierarchy.
- **List**: `zh subissue list <parent#>` — see the children.
- **Remove** (unlink): `zh subissue remove <parent#> <child#> […]`. The child still exists as a standalone issue — this just unlinks the parent relationship. Propose-first if removing more than one at a time.
- **Reorder**: `zh subissue reorder <child#> top|bottom|after <sib#>|before <sib#>`. **Different from `zh reorder`** — sibling-anchored positions, not integers. Free to fire directly for single reorders.
- **Inspect**: `zh issue <N>` opportunistically shows parent + sub-issue count. Use it as the first stop for "where does this issue sit in the hierarchy?"

When recommending sub-issue use over epics: epics are workspace-scoped and visible in the workspace epic list; sub-issues are issue-scoped and only visible from their parent. Choose epics for cross-team / multi-sprint groupings, sub-issues for tight "one parent ticket, several worker tickets" relationships.

**Multi-repo workspaces:** `zh subissue` resolves issue numbers via the current git checkout's repo (`-r` overrides). Parent in one repo with sub-issues in another can't be wired from a single working directory. If a project hits this, propose: (a) keep the hierarchy single-repo by re-filing one side, or (b) build the parent/child relationship via the ZenHub web UI.

---

## Batch operations (wave pattern)

A robust reference pattern for safely executing many ZH operations in sequence:

1. **Plan** — draft the planned operations as YAML (`zh_execution_plan.yaml` or equivalent). One entry per operation: target ticket/epic, action, expected before/after state, closing comment if applicable, rationale link.
2. **Decisions** — surface design questions BEFORE executing. Don't presume.
3. **Pre-check** — query each target's current state, log drift if it doesn't match the plan.
4. **Execute** in sub-batches (5–7 ops each), pause between sub-batches for a spot-check.
5. **Post-check** — verify each action took effect.
6. **Announce** — thread per-sub-batch updates if the project has an announcement channel.
7. **Audit log** — append a per-batch entry to the execution_log YAML. Capture ticket lists + drift + outcomes.

---

## Structured-plan bulk-load (`--related-issues`)

When filing a structured plan (YAML tickets with Planning IDs like `E1-T1`, each carrying `depends_on:`), graph-linked tickets in the same domain often score above the hard duplicate threshold against each other. That match is expected, not a duplicate. Forward each ticket's resolved dependencies as `--related-issues` so the structural-relative rule downgrades block → warn (see Hard Rule #5 in [SKILL.md](SKILL.md)).

Pattern: keep a Planning-ID → issue-number map as you file, resolve each ticket's `depends_on` through it, and pass the resolved numbers on create.

```bash
# Pseudocode loop — plan sorted depends_on-first (topological)
declare -A id_to_num=()

for ticket in "${plan[@]}"; do
  pid="${ticket[parent_planning_id]}"
  if [[ -n "$pid" && -z "${id_to_num[$pid]:-}" ]]; then
    echo "halt: ${ticket[id]} parent $pid unfiled" >&2; exit 1
  fi
  parent="${id_to_num[$pid]:-}"
  relatives=""   # build comma list from depends_on → id_to_num

  args=(create "${ticket[title]}" -t "${ticket[type]:-Task}" -p "${ticket[pipeline]:-Product Backlog}"
        -f "${ticket[body_file]}" --json)
  [[ -n "$parent" ]] && args+=(--parent "$parent")
  [[ -n "$relatives" ]] && args+=(--related-issues "$relatives")
  # pass -l, -e, --priority from plan when present

  out=$(zh "${args[@]}" 2>/dev/null) || { echo "create failed: ${ticket[id]}" >&2; exit 1; }

  ok=$(jq -r '.ok' <<<"$out")
  blocked=$(jq -r '.blocked // false' <<<"$out")
  partial=$(jq -r '.partial_applied // false' <<<"$out")

  if [[ "$ok" != "true" || "$blocked" == "true" || "$partial" == "true" ]]; then
    echo "halt at ${ticket[id]}: $out" >&2
    exit 1
  fi

  id_to_num["${ticket[id]}"]=$(jq -r '.number' <<<"$out")
done
```

Constraints:

- **Forward-only.** `--related-issues` can only reference tickets already filed earlier in the same load.
- **Sort dependencies first.** Topologically order the plan by `depends_on`. For an unavoidable back-edge, fall back to `--confirm-create` on that one create after reviewing the surfaced match.
- **Only map clean successes.** Record a number only when `ok` is true AND `partial_applied` is falsy. A parent-wire failure creates an orphaned issue — don't feed its number to dependents.
- **Forward the plan's metadata.** Defaults are `Task` / `Product Backlog`; pass `-t`, `-l`, `-e`, `--priority` from the plan when present.
- **Planning-noun creates** (`zh epic create`, etc.) accept the same duplicate flags; they have no `-t` (type is fixed per noun). Use `-d`/`-f` for body.

`depends_on` is not a blanket duplicate-exemption: the downgrade is to **warn, not skip**, so a dependency pair that is also an accidental true duplicate still surfaces in `duplicate_check.matches`. Read those matches even on warn.

For bulk loads after auditing the backlog, `--skip-duplicate-check` per call is reasonable — document the choice in the batch audit YAML.

---

## Sprint metadata

If the project uses ZH sprints (with dates + member lists):

- **Reads:** `zh sprints`, `zh sprint`, `zh sprint current` / `zh sprint show [name]`
- **Membership:** `zh sprint add current 42 43`, `zh sprint remove current 42` (aliases: `zh sa`, `zh sr`)

### Put ticket in current sprint + In Progress

```bash
zh sprint add current 42 --json
zh move 42 "In Progress" --json   # {ok, number, title, from, to}
zh pipeline "In Progress" --json  # membership is fresh (mutation invalidated GraphQL cache)
zh sprint --json
```

Needs **zh ≥ 1.11.0** (honest `from`/`to`, subcommand-first sprint add, mutation cache invalidation).
For sprint **creation**, **date changes**, or **completion** flows the installed `zh` does not expose, escalate to the user — do not hit the API directly or patch `zh` from this skill.

If a needed capability is missing from `zh --help`, stop and ask rather than inventing a workaround.
