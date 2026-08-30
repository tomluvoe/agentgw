---
name: memory
description: >
  Persist facts, preferences, standing orders, and watch lists as Markdown
  files in the workspace. Use when the user says remember, forget, recall,
  what do you know about me, watch this, standing order, or asks you to
  keep something for later.
---

# Memory

Chat history is not memory. Durable notes live as files under `memory/` in
the workspace. Use `read`, `write`, and `list_dir` only.

## Layout

- `memory/MEMORY.md` — long-lived facts and preferences
- `memory/WATCH.md` — things to check and act on (one `##` heading per item)
- `memory/YYYY-MM-DD.md` — optional daily log

## Remember

1. `read` `memory/MEMORY.md` if it exists (empty is fine).
2. Merge the new fact. Do not drop old facts.
3. `write` the full file back.

## Recall

1. `list_dir` on `memory`.
2. `read` `MEMORY.md` and any file that looks relevant.
3. Answer from those files, not from earlier chat turns alone.

## Watch / standing order

Add or update a heading in `memory/WATCH.md`:

```markdown
## <short name>
- check: <what to look at>
- when: <how often or what event>
- then: <what to do, including notify if configured>
```

A heartbeat job (when enabled) should `read` this file and follow `then`
for items that are due.
