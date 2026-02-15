# Skill-Based RAG Filtering Example

This example demonstrates how to use skill-based document filtering in the RAG system.

## Scenario

You have two agents:
1. **code_assistant** - Helps with programming questions
2. **hr_assistant** - Answers HR policy questions

You want to ensure each agent only sees relevant documents.

## Setup

### 1. Create the Skills

**skills/code_assistant.yaml:**
```yaml
name: code_assistant
description: Helps with programming and technical questions
system_prompt: |
  You are a helpful coding assistant. Use the knowledge base to find
  relevant code examples and documentation.

tools:
  - search_documents
  - read_file

rag_context:
  enabled: true
  # Defaults to skills: ["code_assistant"]
  top_k: 3
```

**skills/hr_assistant.yaml:**
```yaml
name: hr_assistant
description: Answers HR policy and employee benefit questions
system_prompt: |
  You are an HR assistant. Use the company policies from the knowledge
  base to provide accurate information about benefits and policies.

tools:
  - search_documents

rag_context:
  enabled: true
  # Defaults to skills: ["hr_assistant"]
  top_k: 5
```

### 2. Ingest Documents

```bash
# Python documentation - only for code_assistant
agentgw ingest ./docs/python-guide.md --skills code_assistant

# Company HR policies - only for hr_assistant
agentgw ingest ./docs/pto-policy.md --skills hr_assistant
agentgw ingest ./docs/benefits-2024.md --skills hr_assistant

# General company info - available to ALL agents
agentgw ingest ./docs/company-overview.md

# Technical doc available to multiple skills
agentgw ingest ./docs/api-reference.md --skills code_assistant --skills general_assistant
```

## How It Works

### Automatic Filtering

When you chat with `code_assistant`:
- Searches documents with `skills: ["code_assistant"]` or empty skills
- Finds: `python-guide.md`, `company-overview.md`, `api-reference.md`
- Does NOT see: `pto-policy.md`, `benefits-2024.md`

When you chat with `hr_assistant`:
- Searches documents with `skills: ["hr_assistant"]` or empty skills
- Finds: `pto-policy.md`, `benefits-2024.md`, `company-overview.md`
- Does NOT see: `python-guide.md`, `api-reference.md`

### Testing It

```bash
# Chat with code assistant
agentgw chat --skill code_assistant
> How do I use async/await in Python?
# Agent finds relevant info from python-guide.md automatically

# Chat with HR assistant
agentgw chat --skill hr_assistant
> How many vacation days do I get?
# Agent finds relevant info from pto-policy.md automatically
```

## Advanced: Cross-Skill RAG Access

If you want a skill to access documents from multiple skills:

```yaml
name: manager_assistant
description: Helps managers with both technical and HR questions
system_prompt: |
  You assist managers with technical and people management questions.

tools:
  - search_documents

rag_context:
  enabled: true
  skills: ["code_assistant", "hr_assistant"]  # Explicit cross-skill access
  top_k: 5
```

## Benefits

1. **Privacy**: Sensitive HR docs aren't leaked to technical assistants
2. **Relevance**: Each agent gets focused, relevant context
3. **Scalability**: Add new skills without polluting other agents' contexts
4. **Flexibility**: Documents available to all (empty skills) for shared knowledge
5. **Security**: Control which agents can access which information

## Migration from Tag-Based Filtering

If you were using tags before:

```bash
# Old approach (still works!)
agentgw ingest ./doc.md --tags coding --tags python

# New approach (recommended)
agentgw ingest ./doc.md --skills code_assistant --tags python
```

Tags are now for **sub-categorization within a skill**, while skills provide the primary access control.
