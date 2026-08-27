---
name: demo
description: Example agent that includes shared skills and tools by path.
model: gpt-4o-mini
provider: openai
temperature: 0.4
max_iterations: 8
workspace: .
skills:
  roots:
    - ../../skills
  max_activated: 3
tools:
  allow:
    - read
    - write
    - list_dir
    - exec
    - echo
  modules:
    - ../../tools
---

You are a local demo assistant. Prefer matching skills when they apply.
Stay inside the workspace. Be concise.
