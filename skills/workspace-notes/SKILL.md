---
name: workspace-notes
description: >
  Read and write notes in the workspace. Use when the user asks to take notes,
  remember something, list notes, or save text to a file.
---

# Workspace notes

Keep notes as Markdown files under `notes/` in the workspace.

- To save: `write` to `notes/<short-name>.md`
- To recall: `list_dir` on `notes` then `read` the relevant file
- Prefer existing files over creating duplicates

`{baseDir}` is this skill's directory if you need bundled templates.
