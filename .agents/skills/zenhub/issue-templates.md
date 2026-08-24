# Issue body templates

Default bodies when drafting new tickets (Hard Rule #6). Keep them **short** — fill only what you know; drop empty sections rather than padding with placeholders.

Pick by `zh` type: **Task** (default), **Bug** (regression / defect), **Issue** (Feature or open-ended work that is not a single bugfix).

Titles: imperative, specific, ≤ ~80 chars. No trailing period.

---

## Task

```markdown
## Goal
<one sentence: what to do>

## Done when
- [ ] <observable criterion>
```

Optional (only if needed):

```markdown
## Notes
- <constraint, link, or pointer>
```

---

## Bug

```markdown
## Symptom
<what breaks / wrong behavior>

## Repro
1. <step>
2. <step>

## Expected
<correct behavior>
```

Optional (only if needed):

```markdown
## Evidence
- <log line, metric, env, link>
```

---

## Issue

Use for Features and non-bug work that needs a thin why/scope frame (not a multi-page spec).

```markdown
## Why
<problem or need — one sentence>

## Scope
- in: <what this covers>
- out: <explicit non-goals>

## Done when
- [ ] <acceptance criterion>
```

Optional (only if needed):

```markdown
## Notes
- <dependency, epic link, design pointer>
```

---

## Rules of thumb

- Prefer **Task** unless it is clearly a **Bug** or a scoped **Issue**/Feature.
- One primary outcome per ticket; split rather than inflate the template.
- No essays, no duplicated title in the body, no "Background" walls.
- Still run Hard Rule #5 (duplicates) before drafting, and Hard Rule #6 (AskQuestion Proceed / Change / Open in Zed) before create.
