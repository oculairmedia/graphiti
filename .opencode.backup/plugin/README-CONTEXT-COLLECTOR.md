# Graphiti Automatic Context Collector

Automatically sends **small, focused episodes** to Graphiti for optimal entity extraction and knowledge graph building.

## Design Philosophy

✅ **Small Episodes** - Each interaction is a separate, concise episode
✅ **Focused Content** - Max 500 characters per episode (configurable)
✅ **Better Extraction** - Smaller episodes = better entity/relationship extraction
✅ **Temporal Links** - Episodes linked via timestamps and git context
✅ **No Batching** - Individual events sent as they happen

## What Gets Captured

### 1. User Messages (Individual Episodes)
```
Episode Name: "User: Fix the authentication bug in login.ts..."
Content:
User asked: "Fix the authentication bug in login.ts"

Project: myapp
Branch: fix/auth
Time: 2025-01-08T21:45:00Z
```

### 2. Assistant Responses (Individual Episodes)
```
Episode Name: "Assistant: I'll analyze the login.ts file and fix..."
Content:
Assistant responded: "I'll analyze the login.ts file and fix the null check issue"
Tools: read, edit

Project: myapp
Branch: fix/auth
Time: 2025-01-08T21:45:15Z
```

### 3. Tool Usage (Individual Episodes)
```
Episode Name: "Tool: read"
Content:
Used tool: read
Args: {
  "file_path": "src/login.ts"
}

Project: myapp
Branch: fix/auth
Time: 2025-01-08T21:45:16Z
```

### 4. File Changes (Individual Episodes)
```
Episode Name: "edited: src/login.ts"
Content:
File edited: src/login.ts

Project: myapp
Branch: fix/auth
Commit: abc1234
Time: 2025-01-08T21:45:20Z
```

### 5. Session Markers (Individual Episodes)
```
Episode Name: "Session started: myapp"
Content:
OpenCode session started

Project: myapp
Branch: fix/auth
Directory: /home/user/projects/myapp
Time: 2025-01-08T21:44:00Z
```

## Why Small Episodes?

### Better Entity Extraction
Graphiti's LLM can extract entities more accurately from focused content:

**❌ Large Episode (1000+ chars):**
```
"User asked about auth, then we discussed the bug,
then looked at 3 files, then made changes, then..."
→ Extracts: Project, maybe File
```

**✅ Small Episode (< 500 chars):**
```
"File edited: src/login.ts in myapp on branch fix/auth"
→ Extracts: File, Project, Branch, Action, Timestamp
```

### Better Relationships
Smaller episodes create cleaner entity relationships:
- `File (login.ts) -> MODIFIED_IN -> Branch (fix/auth)`
- `User -> ASKED_ABOUT -> Issue (auth bug)`
- `Tool (read) -> USED_ON -> File (login.ts)`

### Faster Processing
- Smaller LLM calls = faster entity extraction
- Less context to process per episode
- Parallel processing of independent episodes

## Configuration

```bash
# Graphiti API endpoint (default: http://localhost:8003)
export GRAPHITI_API_URL="http://localhost:8003"

# Group ID (default: opencode-{project-name})
export GRAPHITI_GROUP_ID="myapp-context"

# Max characters per episode (default: 500)
export GRAPHITI_MAX_CONTENT="500"

# Enable/disable auto-collection (default: true)
export GRAPHITI_AUTO_COLLECT="true"
```

## Example Conversation Flow

**User:** "Add error handling to the API client"

**Episodes Created:**

1. **User Message:**
   - Name: `User: Add error handling to the API client`
   - Entities: `Feature (error handling)`, `Component (API client)`

2. **Assistant Response:**
   - Name: `Assistant: I'll add try-catch blocks and proper error...`
   - Entities: `Technique (try-catch)`, `Pattern (error handling)`
   - Tools: `[read, edit]`

3. **Tool: read**
   - Name: `Tool: read`
   - Entities: `Tool (read)`, `File (api-client.ts)`

4. **Tool: edit**
   - Name: `Tool: edit`
   - Entities: `Tool (edit)`, `File (api-client.ts)`

5. **File Change:**
   - Name: `edited: src/api-client.ts`
   - Entities: `File (api-client.ts)`, `Branch (main)`, `Action (edited)`

**Result:** 5 focused episodes, 10+ entities, 15+ relationships

## Performance

### Queued Processing
- Episodes queued and sent sequentially
- 100ms delay between sends to prevent rate limiting
- Non-blocking - doesn't slow down OpenCode

### Smart Truncation
- Content automatically truncated to max length
- Preserves essential information
- Indicates truncation with `...`

### Minimal Overhead
```
User message → Queue → Send (async) → ✓
Assistant reply → Queue → Send (async) → ✓
Tool use → Queue → Send (async) → ✓
```

Total delay: ~0ms (all async)

## Benefits

### 1. Rich Knowledge Graph
Every interaction creates entities:
- **Files** mentioned or modified
- **Concepts** discussed (bugs, features, patterns)
- **Actions** taken (edited, created, fixed)
- **Branches** worked on
- **Tools** used

### 2. Temporal Context
Graphiti can answer:
- "What files were changed after we discussed the auth bug?"
- "Which tools do we use most when fixing bugs?"
- "What features were added in the last week?"

### 3. Pattern Recognition
Graphiti learns:
- Common workflows (read → edit → test)
- File modification patterns
- Tool usage habits
- Branch naming conventions

### 4. Project Memory
Never lose context:
- "When did we last work on authentication?"
- "What was the conversation about error handling?"
- "Which files are related to the API client?"

## Monitoring

### Console Output
```
[Graphiti] Context collector enabled for myapp
[Graphiti] ✓ User: Fix the authentication bug...
[Graphiti] ✓ Assistant: I'll analyze the login.ts file...
[Graphiti] ✓ Tool: read
[Graphiti] ✓ edited: src/login.ts
```

### Graphiti Dashboard
Check your Graphiti instance to see:
- Individual episodes appearing in real-time
- Entity graph growing with each interaction
- Relationships forming between entities

### Search Examples
Query Graphiti after a session:
```
"authentication bug" → finds user message episode
"login.ts" → finds file change episodes
"error handling" → finds related conversations
```

## Advanced Configuration

### Adjust Episode Size
Smaller episodes (more granular):
```bash
export GRAPHITI_MAX_CONTENT="300"
```

Larger episodes (more context):
```bash
export GRAPHITI_MAX_CONTENT="800"
```

### Disable for Specific Projects
```bash
# In specific project directory
export GRAPHITI_AUTO_COLLECT="false"
```

### Custom Group IDs
Organize by feature or sprint:
```bash
export GRAPHITI_GROUP_ID="myapp-sprint-24"
export GRAPHITI_GROUP_ID="myapp-feature-auth"
```

## Troubleshooting

### Episodes not appearing

1. Check Graphiti is running:
   ```bash
   curl http://localhost:8003/health
   ```

2. Check console for `[Graphiti]` messages:
   ```
   [Graphiti] ✓ User: ...  ← Working
   [Graphiti] Failed to send: ... ← Problem
   ```

3. Verify environment:
   ```bash
   echo $GRAPHITI_API_URL
   echo $GRAPHITI_AUTO_COLLECT
   ```

### Too many episodes

Increase max content length to reduce episode count:
```bash
export GRAPHITI_MAX_CONTENT="1000"
```

### Episodes too small

Decrease max content length for more granular tracking:
```bash
export GRAPHITI_MAX_CONTENT="250"
```

### Rate limiting errors

Increase delay between sends in plugin code:
```typescript
// Line ~105: Change from 100ms to 200ms
await new Promise(resolve => setTimeout(resolve, 200))
```

## Comparison: Old vs New

### Old Approach (Batched)
```
5 messages → 1 large episode → 3-4 entities
```

### New Approach (Individual)
```
5 messages → 5 small episodes → 15-20 entities
```

**3-5x more entities** with focused episodes!

## Integration

Works alongside other Graphiti plugins:

- **graphiti-integration.ts** - Manual tools for search/storage
- **graphiti-context-collector.ts** - Automatic background collection

Use both for full-featured Graphiti integration!

## Privacy

Captures:
- ✅ Message content (user questions, AI responses)
- ✅ Tool names and arguments
- ✅ File paths (not contents)
- ✅ Git metadata (branch, commit)

Does NOT capture:
- ❌ File contents (unless in conversation)
- ❌ Secrets or environment variables
- ❌ System information beyond git

## License

Follows the Graphiti project license.
