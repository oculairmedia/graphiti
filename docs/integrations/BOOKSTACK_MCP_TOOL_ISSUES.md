# BookStack MCP Tool Issues Report

**Date**: 2025-10-09  
**Reporter**: Roo AI Assistant  
**BookStack MCP Server**: bookstack  
**Context**: Attempting to create a new page in the "Graphiti Architecture" book (ID: 85)

## Executive Summary

Multiple attempts to create a page using the BookStack MCP server tools failed due to API parameter conflicts and unclear tool specifications. The primary issues involve:

1. Conflicting parameter requirements between tool schema and actual implementation
2. Unclear documentation about which parameters are truly required
3. Inconsistent handling of markdown vs HTML content
4. Confusing error messages that don't match the tool's input schema

## Tool Used

**Tool Name**: `bookstack_content_crud`  
**Operation**: `create_page`

## Issue Timeline

### Attempt 1: Using HTML in nested data object

**Tool Call**:
```json
{
  "action": "create_page",
  "name": "OpenCode Plugin Integration",
  "data": "{\"book_id\": 85, \"html\": \"<h1>OpenCode Plugin Integration</h1>...\"}"
}
```

**Error**:
```
fastmcp_server.bookstack.tools._build_content_operation() got multiple values for keyword argument 'html'
```

**Analysis**: The tool appears to be extracting `html` from the JSON data string AND also receiving it as a direct parameter, causing a conflict.

---

### Attempt 2: Using markdown in nested data object

**Tool Call**:
```json
{
  "action": "create_page",
  "name": "OpenCode Plugin Integration",
  "data": "{\"book_id\": 85, \"markdown\": \"# OpenCode Plugin Integration...\"}"
}
```

**Error**:
```
fastmcp_server.bookstack.tools._build_content_operation() got multiple values for keyword argument 'markdown'
```

**Analysis**: Same issue as with HTML - parameter duplication between JSON data and extracted parameters.

---

### Attempt 3: Adding description field

**Tool Call**:
```json
{
  "action": "create_page",
  "name": "OpenCode Plugin Integration",
  "description": "Documentation for the OpenCode plugin integration...",
  "data": "{\"book_id\": 85, \"markdown\": \"...\"}"
}
```

**Error**:
```
fastmcp_server.bookstack.tools._build_content_operation() got multiple values for keyword argument 'markdown'
```

**Analysis**: Adding description didn't resolve the core parameter conflict issue.

---

### Attempt 4: Using bookstack_batch_operations (simple)

**Tool Call**:
```json
{
  "operation": "bulk_create",
  "entity_type": "page",
  "items": [
    {
      "data": "{\"name\": \"OpenCode Plugin Integration\", \"book_id\": 85, \"markdown\": \"...\"}"
    }
  ]
}
```

**Error**:
```
_build_content_operation() missing 9 required keyword-only arguments: 'description', 'content', 'html', 'cover_image', 'chapter_id', 'books', 'tags', 'image_id', and 'priority'
```

**Analysis**: Reveals that the underlying function requires many more parameters than the tool schema indicates.

---

### Attempt 5: Using bookstack_batch_operations (with all fields)

**Tool Call**:
```json
{
  "operation": "bulk_create",
  "entity_type": "page",
  "items": [
    {
      "data": "{\"name\": \"...\", \"book_id\": 85, \"description\": \"...\", \"markdown\": \"...\", \"html\": \"\", \"content\": \"\", \"chapter_id\": 0, \"tags\": [], \"priority\": 8, \"books\": [], \"cover_image\": null, \"image_id\": null}"
    }
  ]
}
```

**Error**:
```
'chapter_id' must be a positive integer
Hint: Provide a numeric value greater than zero for 'chapter_id'.
Context: {"received": 0}
```

**Analysis**: When trying to create a page directly in a book (not in a chapter), `chapter_id: 0` is rejected. Pages not in chapters should likely not require this field or should accept 0/null.

---

### Attempt 6: Removing chapter_id

**Tool Call**:
```json
{
  "data": "{\"name\": \"...\", \"book_id\": 85, \"description\": \"...\", \"markdown\": \"...\", \"html\": \"\", \"content\": \"\", \"tags\": [], \"priority\": 8, \"books\": [], \"cover_image\": null, \"image_id\": null}"
}
```

**Error**:
```
_build_content_operation() missing 1 required keyword-only argument: 'chapter_id'
```

**Analysis**: Catch-22 situation - chapter_id is required but 0 is not accepted.

## Root Causes Identified

### 1. Parameter Extraction Logic Issue

The `_build_content_operation()` function appears to:
- Parse the `data` JSON string
- Extract fields from the parsed JSON
- Pass them as keyword arguments
- BUT also receive some of the same fields as direct parameters from the tool call

This creates conflicts when fields like `html`, `markdown`, `name`, etc. appear in both places.

### 2. Unclear Required vs Optional Fields

The tool schema doesn't clearly indicate:
- Which fields are truly required for page creation
- Whether `markdown` OR `html` is sufficient (not both)
- How to handle pages not in chapters (chapter_id issue)
- Whether empty strings are acceptable for unused fields

### 3. BookStack API Inconsistency

Based on the working `read_page` response, BookStack pages have:
- `markdown` field (for editing)
- `html` field (for rendering)
- `raw_html` field (for display)

But the creation flow seems to require:
- Both `html` AND `markdown` AND `content`
- All as separate required fields

### 4. Chapter Requirement Logic

For pages directly in books (not in chapters):
- `chapter_id` should probably be optional or accept 0/null
- Current implementation requires it AND rejects 0
- No clear way to create a page outside of a chapter

## Successful Operations (For Reference)

### Reading a Book
```json
{
  "action": "read_book",
  "content_id": 85
}
```
✅ **Success**: Returns complete book structure with contents array

### Reading a Page
```json
{
  "action": "read_page",
  "content_id": 178
}
```
✅ **Success**: Returns page with `markdown`, `html`, and `raw_html` fields

### Searching
```json
{
  "query": "Graphiti Architecture"
}
```
✅ **Success**: Returns search results with page summaries

### Listing Content
```json
{
  "entity_type": "pages",
  "book_id": 85,
  "count": 1
}
```
✅ **Success**: Returns paginated list of pages

## Recommendations for MCP Server Developer

### 1. Fix Parameter Passing
- Decide if `data` should be a JSON string or if parameters should be passed directly
- Avoid extracting parameters from `data` JSON that conflict with direct parameters
- Document the expected structure clearly

### 2. Simplify Page Creation
Suggest one of these approaches:

**Option A: Direct Parameters** (Recommended)
```json
{
  "action": "create_page",
  "book_id": 85,
  "name": "Page Title",
  "markdown": "# Content here",
  "description": "Optional description",
  "chapter_id": null  // or omit for book-level pages
}
```

**Option B: Clean Data Object**
```json
{
  "action": "create_page",
  "data": {
    "book_id": 85,
    "name": "Page Title",
    "markdown": "# Content here",
    "description": "Optional description"
  }
}
```

### 3. Fix Chapter ID Handling
- Make `chapter_id` optional for pages directly in books
- Accept `null`, `0`, or omission to indicate "no chapter"
- Update validation to allow this use case

### 4. Clarify Content Fields
- Document whether `markdown` OR `html` is sufficient
- Explain what `content` field is for (seems redundant)
- Allow users to provide only the content format they have

### 5. Update Tool Schema
Ensure the MCP tool schema accurately reflects:
- All required fields
- All optional fields
- Valid values for each field
- Examples of successful usage

### 6. Improve Error Messages
Current errors like "got multiple values for keyword argument" are confusing because:
- Users don't see the internal function signature
- The tool schema doesn't show these parameters as duplicates
- Suggest errors like: "Parameter 'html' should not be in both 'data' and direct parameters"

## Example of Expected Behavior

Based on BookStack's API documentation, page creation should work like:

```json
{
  "action": "create_page",
  "book_id": 85,
  "name": "OpenCode Plugin Integration",
  "markdown": "# OpenCode Plugin Integration\n\nContent here...",
  "description": "Optional description"
}
```

And return:
```json
{
  "success": true,
  "data": {
    "id": 189,
    "name": "OpenCode Plugin Integration",
    "slug": "opencode-plugin-integration",
    "book_id": 85,
    "chapter_id": 0,
    "url": "https://knowledge.oculair.ca/books/graphiti-architecture/page/opencode-plugin-integration",
    "markdown": "# OpenCode Plugin Integration...",
    "html": "<h1>OpenCode Plugin Integration</h1>..."
  }
}
```

## Additional Context

### What Was Attempted
Creating a page titled "OpenCode Plugin Integration" in the "Graphiti Architecture" book (ID: 85) with markdown content from the local file `docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md`.

### Current Workaround
Manual creation through BookStack web interface is the only reliable method currently.

### Impact
The BookStack MCP integration is valuable for automation but the page creation functionality is currently unusable, limiting its utility for documentation workflows.

---

## Files for Developer Reference

1. **Source content**: `/opt/stacks/graphiti/docs/integrations/OPENCODE_PLUGIN_INTEGRATION.md`
2. **This report**: `/opt/stacks/graphiti/docs/integrations/BOOKSTACK_MCP_TOOL_ISSUES.md`
3. **Target book**: https://knowledge.oculair.ca/books/graphiti-architecture (ID: 85)

## Contact

If you need clarification on any of these issues or want to test fixes, please reach out to the Graphiti project maintainers.