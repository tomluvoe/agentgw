# Document Management - Implementation Summary

## Overview

Added comprehensive document management functionality to view, search, and delete documents from the RAG knowledge base.

## New Features

### 1. List Documents (`RAGStore.list_documents`)

**Location:** `src/agentgw/rag/chroma.py`

**Functionality:**
- List all documents in a collection
- Filter by skill names
- Filter by source (substring match)
- Limit number of results
- Returns document ID, preview text, full text, and metadata

**Key implementation details:**
- Uses ChromaDB's `get()` method with limit
- Post-filters by skills and source in Python
- Truncates preview text to 200 characters
- Includes chunk metadata (index, total chunks)

### 2. Delete Documents

**By IDs (`RAGStore.delete`):**
- Delete specific chunks by their IDs
- Accepts list of IDs
- Logs deletion count

**By Source (`RAGStore.delete_by_source`):**
- Delete ALL chunks from a specific source
- Uses ChromaDB's `where` clause to find docs
- Returns count of deleted documents
- Handles non-existent sources gracefully

### 3. CLI Commands

**`agentgw documents`** - List documents
```bash
agentgw documents [--collection COLL] [--skills SKILL...] [--source SRC] [--limit N]
```

**`agentgw delete-documents`** - Delete documents
```bash
agentgw delete-documents [--collection COLL] [--source SRC | --id ID...]
```

Features:
- Color-coded output
- Chunk information display
- Skill availability indication
- Confirmation prompt before deletion

### 4. Web UI

**New route:** `/documents`

**Template:** `src/agentgw/interfaces/web/templates/documents.html`

**Features:**
- Search & filter form (source, skills, collection, limit)
- Documents grouped by source
- Expandable details per source
- Individual chunk preview
- Delete buttons (per chunk and per source)
- Confirmation modal
- Toast notifications
- Real-time refresh after deletion

**UI/UX:**
- Tokyo Night color scheme
- Responsive layout
- Clear visual hierarchy
- Metadata badges (skills, tags)
- Chunk count indicators

### 5. REST API

**GET `/api/documents`**
- Query params: `collection`, `skills`, `source`, `limit`
- Returns: `{documents: [...], count: N}`

**DELETE `/api/documents`**
- Query params: `collection`, `source` OR `ids` (comma-separated)
- Returns: `{status: "ok", deleted: N}`

### 6. Navigation

Updated `base.html` to include "Documents" link in navbar.

## Code Changes

### Modified Files

1. **`src/agentgw/rag/chroma.py`**
   - Added `list_documents()` method
   - Enhanced `delete()` with logging
   - Added `delete_by_source()` method

2. **`src/agentgw/interfaces/cli.py`**
   - Added `documents` command
   - Added `delete-documents` command with confirmation

3. **`src/agentgw/interfaces/web/app.py`**
   - Added `/documents` page route
   - Added `GET /api/documents` endpoint
   - Added `DELETE /api/documents` endpoint

4. **`src/agentgw/interfaces/web/templates/base.html`**
   - Added "Documents" to navbar

### New Files

1. **`src/agentgw/interfaces/web/templates/documents.html`**
   - Full-featured document browser UI

2. **`tests/test_document_management.py`**
   - 11 comprehensive tests

3. **`examples/document_management.md`**
   - Complete usage guide

## Testing

Added 11 new tests in `test_document_management.py`:

1. ✅ List all documents
2. ✅ Filter by skill
3. ✅ Filter by source
4. ✅ Limit results
5. ✅ Empty skills included in listings
6. ✅ Delete by IDs
7. ✅ Delete by source
8. ✅ Delete non-existent source (returns 0)
9. ✅ Delete multiple IDs
10. ✅ Preview text truncation
11. ✅ Chunk metadata included

**Total: 61 tests passing** (50 original + 11 new)

## Use Cases

### 1. Content Updates
Replace outdated documentation:
```bash
agentgw delete-documents --source old-api-v1.md
agentgw ingest ./docs/api-v2.md --skills code_assistant
```

### 2. Mistake Correction
Fix wrong ingestion:
```bash
agentgw documents --source wrong-file
agentgw delete-documents --source wrong-file.txt
agentgw ingest ./correct-file.txt --skills proper_skill
```

### 3. Access Auditing
Check which skills can access docs:
```bash
agentgw documents --skills hr_assistant
```

### 4. Bulk Cleanup
Remove multiple documents:
```bash
agentgw documents --source temp-
# Review output
agentgw delete-documents --source temp-file-1.txt
agentgw delete-documents --source temp-file-2.txt
```

## Design Decisions

### Why Post-Filtering?

We use Python post-filtering instead of ChromaDB where clauses because:
- More control over skill matching logic
- Easier to implement "available to all" semantics
- Simpler to combine multiple filter conditions
- Better error handling

### Why Group by Source?

In the Web UI, documents are grouped by source because:
- Most updates/deletes are at the source level
- Easier to understand document organization
- Reduces visual clutter (one source = many chunks)
- Matches user mental model

### Why Confirmation?

Deletions require confirmation because:
- RAG deletions are permanent
- No built-in "undo" mechanism
- Prevents accidental data loss
- Best practice for destructive operations

## Performance Considerations

- **Listing**: Fetches up to `limit` documents from ChromaDB, then filters in Python
- **Deletion by source**: Single ChromaDB query to find docs, then batch delete
- **Deletion by IDs**: Direct deletion, O(1) per ID
- **Web UI**: Fetches all matching docs at once (no pagination yet)

## Future Enhancements

Potential improvements:
- [ ] Pagination for large result sets
- [ ] Export documents to file
- [ ] Bulk delete by skill filter
- [ ] Document update-in-place
- [ ] Search within document content (full-text)
- [ ] Statistics dashboard (doc count by skill, by source, etc.)
- [ ] Scheduled cleanup jobs

## Backward Compatibility

✅ **100% backward compatible:**
- No changes to existing ingestion API
- No changes to search behavior
- Purely additive functionality
- No database schema changes required
