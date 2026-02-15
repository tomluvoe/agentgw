# Document Management Guide

This guide shows how to view, search, and manage documents in the RAG knowledge base.

## Why Document Management?

As your knowledge base grows, you need to:
- **Track what's ingested**: See what documents are in the system
- **Update outdated content**: Remove old versions when you update documentation
- **Clean up mistakes**: Delete documents ingested with wrong settings
- **Audit access**: See which skills can access which documents
- **Free up space**: Remove documents that are no longer needed

## CLI Commands

### List Documents

```bash
# List all documents
agentgw documents

# Output shows:
# - Document ID
# - Source name and chunk number
# - Skills (or "available to all")
# - Tags
# - Preview of content
```

### Filter Documents

```bash
# Filter by skill
agentgw documents --skills code_assistant

# Filter by source (substring match)
agentgw documents --source python

# Combine filters
agentgw documents --skills code_assistant --source api-reference

# Limit results
agentgw documents --limit 20

# Different collection
agentgw documents --collection production-kb
```

### Delete Documents

```bash
# Delete ALL chunks from a source
agentgw delete-documents --source old-python-guide.md

# Delete specific chunks by ID
agentgw delete-documents --id abc-123 --id def-456

# You'll be prompted to confirm
# Add --yes to skip confirmation (careful!)
```

## Web UI

Navigate to **http://localhost:8080/documents** (or your configured host/port).

### Features

1. **Search & Filter**
   - Filter by source name (substring match)
   - Filter by skills (comma-separated)
   - Select collection
   - Set result limit

2. **Browse Documents**
   - Grouped by source
   - Shows metadata (skills, tags, chunk count)
   - Click to expand and view individual chunks
   - Preview of chunk content

3. **Delete Operations**
   - "Delete All" button per source (removes all chunks)
   - "Delete" button per chunk (removes individual chunk)
   - Confirmation modal before deletion
   - Toast notification on success

## Common Workflows

### Updating a Document

When you need to replace outdated content:

```bash
# 1. View current version
agentgw documents --source api-reference.md

# 2. Delete old version
agentgw delete-documents --source api-reference.md

# 3. Ingest new version
agentgw ingest ./docs/api-reference-v2.md --skills code_assistant --tags api
```

### Cleaning Up a Mistake

If you ingested with wrong settings:

```bash
# Find the document
agentgw documents --source wrong-file.txt

# Delete it
agentgw delete-documents --source wrong-file.txt

# Re-ingest correctly
agentgw ingest ./docs/correct-file.txt --skills proper_skill
```

### Auditing Document Access

See which skills can access a document:

```bash
# List documents for a specific skill
agentgw documents --skills hr_assistant

# This shows:
# - Documents explicitly assigned to hr_assistant
# - Documents available to all skills (empty skills field)
```

### Bulk Cleanup

Remove all documents from a specific source pattern:

```bash
# List to verify what will be deleted
agentgw documents --source old-

# Delete each source
agentgw delete-documents --source old-api-v1.md
agentgw delete-documents --source old-guide-2023.txt
```

## API Usage

### List Documents

```bash
curl "http://localhost:8080/api/documents?collection=default&skills=code_assistant&limit=10"

# Response:
{
  "documents": [
    {
      "id": "abc-123",
      "text": "Preview text...",
      "full_text": "Complete text...",
      "metadata": {
        "source": "python-guide.md",
        "skills": "code_assistant",
        "tags": "python,tutorial",
        "chunk_index": 0,
        "total_chunks": 5
      }
    }
  ],
  "count": 1
}
```

### Delete Documents

```bash
# Delete by source
curl -X DELETE "http://localhost:8080/api/documents?collection=default&source=old-doc.md"

# Delete by IDs (comma-separated)
curl -X DELETE "http://localhost:8080/api/documents?collection=default&ids=abc-123,def-456"

# Response:
{
  "status": "ok",
  "deleted": 5
}
```

## Tips & Best Practices

### Naming Convention for Sources

Use descriptive, versioned source names:

```bash
# Good
agentgw ingest ./docs/api-reference-v2.1.md --skills code_assistant
agentgw ingest ./docs/hr-policy-2024.pdf --skills hr_assistant

# Not as good
agentgw ingest ./doc.txt --skills code_assistant
```

### Regular Cleanup

Periodically review and clean:

```bash
# Monthly check for documents to archive
agentgw documents --limit 1000 > kb-audit-$(date +%Y%m).txt

# Review the file and delete outdated sources
```

### Skill Filtering for Privacy

Use skill filtering to prevent accidental access:

```bash
# Sensitive HR data
agentgw documents --skills hr_assistant

# Verify no other skills can access it
agentgw documents --skills code_assistant  # Should NOT show HR data
```

### Backup Before Deletion

Before deleting, optionally export the content:

```bash
# View the full content first
agentgw documents --source important-doc.md --limit 1000

# Save to file if needed (manual copy-paste from output)
# Then delete
agentgw delete-documents --source important-doc.md
```

## Troubleshooting

### "No documents found"

- Check your filters (source, skills)
- Verify the collection name
- Ensure documents were actually ingested

### Can't delete a document

- Verify the exact source name or document ID
- Check you're using the correct collection
- Ensure you have write permissions on the ChromaDB directory

### Document count is wrong

- ChromaDB groups by chunks, not files
- A single file creates multiple chunks
- Use the "total_chunks" metadata to understand grouping

### Skill filtering not working as expected

- Documents with **empty skills** match ALL skill filters
- This is by design (they're "available to all")
- To see only skill-specific docs, filter in post-processing
