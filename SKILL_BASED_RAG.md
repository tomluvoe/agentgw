# Skill-Based RAG Filtering - Implementation Summary

## Overview

The RAG system now supports **per-skill document access control**. Documents can be associated with zero or more skills, where zero means "available to all agents."

## Key Changes

### 1. Storage Layer (`src/agentgw/rag/chroma.py`)

**Ingestion:**
- Added `skills` field to metadata (comma-separated string in ChromaDB)
- Empty `skills` = available to all agents
- Example: `{"skills": "code_assistant,general_assistant", "tags": "python,api"}`

**Search:**
- Added `skills` parameter for filtering
- Post-filtering in Python for precise skill/tag matching
- Documents with empty `skills` field match all skill filters
- Backward compatible with tag-only filtering

### 2. Agent Loop (`src/agentgw/core/agent.py`)

**Auto-injection:**
- RAG context now auto-filters by current skill name
- `rag_context.skills` defaults to `[current_skill.name]`
- Can override with explicit skill list for cross-skill access
- Example:
  ```yaml
  rag_context:
    enabled: true
    skills: ["code_assistant"]  # Defaults to current skill
    tags: ["documentation"]     # Additional filtering
    top_k: 3
  ```

### 3. Tools (`src/agentgw/tools/rag_tools.py`)

**search_documents:**
- Added `skills` parameter
- `skills: list[str] | None = None`

**ingest_document:**
- Added `skills` parameter
- `skills: list[str] | None = None` (empty = all skills)

### 4. CLI (`src/agentgw/interfaces/cli.py`)

**ingest command:**
```bash
# Specific skills
agentgw ingest ./doc.md --skills code_assistant --skills hr_assistant

# Available to all (default)
agentgw ingest ./doc.md

# With tags
agentgw ingest ./doc.md --skills code_assistant --tags python --tags api
```

Output shows skill availability:
```
Ingested 5 chunks from './doc.md' into collection 'default'
Skills: code_assistant, hr_assistant
Tags: python, api
```

### 5. Web UI

**Ingest Form (`src/agentgw/interfaces/web/templates/ingest.html`):**
- Added "Skills" input field
- Helper text: "Leave empty to make this document available to all agents"
- Success message shows skill availability

**API (`src/agentgw/interfaces/web/app.py`):**
- `IngestRequest` model includes `skills: list[str] | None = None`
- POST `/api/ingest` accepts skills parameter

### 6. Documentation

**Updated:**
- `README.md` - Added skill-based filtering examples
- `skills/_schema.yaml` - Updated rag_context documentation
- `CHANGELOG.md` - Added release notes
- `examples/skill_based_rag.md` - Comprehensive usage guide

## Filtering Logic

### How Documents Match

A document matches a search if:

1. **Skill filtering (if specified):**
   - Document has empty `skills` field (available to all), OR
   - Any requested skill is in document's skill list

2. **Tag filtering (if specified):**
   - Any requested tag is in document's tag list

3. **Both filters (if both specified):**
   - Must match BOTH skill AND tag conditions

### Examples

**Documents:**
```
doc1: skills=["code_assistant"], tags=["python"]
doc2: skills=[], tags=["general"]
doc3: skills=["hr_assistant"], tags=["benefits"]
```

**Search queries:**
```python
# Search with skill="code_assistant"
# Matches: doc1 (explicit), doc2 (available to all)

# Search with skill="hr_assistant"
# Matches: doc2 (available to all), doc3 (explicit)

# Search with skill="code_assistant", tags=["python"]
# Matches: doc1 (both conditions met)

# Search with no filters
# Matches: doc1, doc2, doc3 (all)
```

## Migration Guide

### From Tag-Based to Skill-Based

**Before (tag-only):**
```bash
agentgw ingest ./python-guide.md --tags coding --tags python
```

**After (skill-based, recommended):**
```bash
agentgw ingest ./python-guide.md --skills code_assistant --tags python
```

**Skill YAML before:**
```yaml
rag_context:
  enabled: true
  tags: ["coding"]
  top_k: 3
```

**Skill YAML after:**
```yaml
rag_context:
  enabled: true
  # skills defaults to [current_skill_name]
  tags: ["coding"]  # Optional additional filtering
  top_k: 3
```

## Use Cases

### 1. Privacy & Security
```bash
# HR documents only for HR assistant
agentgw ingest ./employee-salaries.pdf --skills hr_assistant

# Engineering docs only for code assistant
agentgw ingest ./api-keys.md --skills code_assistant
```

### 2. Shared Knowledge Base
```bash
# Company policies available to all
agentgw ingest ./code-of-conduct.md
```

### 3. Cross-Skill Access
```yaml
name: manager_assistant
rag_context:
  enabled: true
  skills: ["code_assistant", "hr_assistant"]  # Access both
```

### 4. Gradual Migration
```bash
# Keep existing tag-based ingestion (still works!)
agentgw ingest ./doc.md --tags my-tag

# New ingestion uses skills
agentgw ingest ./new-doc.md --skills my_skill
```

## Testing

Added 8 new tests in `tests/test_rag_skill_filtering.py`:

1. ✅ Ingest with skills
2. ✅ Ingest available to all (empty skills)
3. ✅ Search filters by skill
4. ✅ Empty skills field matches all searches
5. ✅ Search with multiple skills
6. ✅ Combined skill and tag filtering
7. ✅ Search without filters
8. ✅ Backward compatibility with tags-only

**Total: 50 tests passing** (42 original + 8 new)

## Performance

**Post-filtering approach:**
- Fetches 3x requested results from ChromaDB when filters are active
- Filters in Python for precise control
- Returns exactly `top_k` results after filtering
- Minimal performance impact (filtering is O(n) on small result sets)

## Backward Compatibility

✅ **100% backward compatible:**
- Tag-only filtering still works
- Empty skills field = available to all
- Existing ingested documents (without skills) remain accessible
- No migration required for existing data
