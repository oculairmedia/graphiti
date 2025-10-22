import type { Plugin } from "@opencode-ai/plugin"

/**
 * Graphiti Automatic Context Collection Plugin for OpenCode
 *
 * Sends small, focused episodes to Graphiti for better entity extraction.
 * Each interaction (message, tool call, file change) becomes a separate episode.
 *
 * Features:
 * - Individual episodes per message/action
 * - Concise, focused content
 * - Temporal context via timestamps
 * - Efficient entity extraction
 * - No large batches
 */

interface QueueItem {
  name: string
  content: string
  source: string
  timestamp: string
}

export const GraphitiContextCollector: Plugin = async ({ project, client, $, directory, worktree }) => {
  const GRAPHITI_API_URL = process.env.GRAPHITI_API_URL || "http://localhost:8003"
  const GROUP_ID = process.env.GRAPHITI_GROUP_ID || `opencode-${project.name}`
  const MAX_CONTENT_LENGTH = parseInt(process.env.GRAPHITI_MAX_CONTENT || "500") // Max chars per episode
  const ENABLED = process.env.GRAPHITI_AUTO_COLLECT !== "false"

  let gitContext: { branch: string; commit: string } | null = null
  let pendingQueue: QueueItem[] = []
  let isProcessing = false

  /**
   * Get git context (cached)
   */
  async function getGitContext() {
    if (gitContext) return gitContext

    try {
      const branch = await $`git rev-parse --abbrev-ref HEAD`.text()
      const commit = await $`git rev-parse --short HEAD`.text()
      gitContext = {
        branch: branch.trim(),
        commit: commit.trim(),
      }
      return gitContext
    } catch {
      gitContext = { branch: "unknown", commit: "unknown" }
      return gitContext
    }
  }

  /**
   * Truncate content to max length
   */
  function truncateContent(content: string, maxLength: number): string {
    if (content.length <= maxLength) return content
    return content.substring(0, maxLength - 3) + "..."
  }

  /**
   * Send a single episode to Graphiti
   */
  async function sendEpisode(name: string, content: string, source: string) {
    try {
      const response = await fetch(`${GRAPHITI_API_URL}/v1/add-episode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          episode_body: content,
          source,
          group_id: GROUP_ID,
        }),
        signal: AbortSignal.timeout(15000),
      })

      if (!response.ok) {
        console.warn(`[Graphiti] Failed to send: ${name} (${response.status})`)
        return false
      }

      console.debug(`[Graphiti] ✓ ${name}`)
      return true
    } catch (error) {
      console.warn(`[Graphiti] Error: ${(error as Error).message}`)
      return false
    }
  }

  /**
   * Process queue sequentially to avoid overwhelming Graphiti
   */
  async function processQueue() {
    if (isProcessing || pendingQueue.length === 0) return

    isProcessing = true

    while (pendingQueue.length > 0) {
      const item = pendingQueue.shift()!
      await sendEpisode(item.name, item.content, item.source)

      // Small delay between sends to prevent rate limiting
      if (pendingQueue.length > 0) {
        await new Promise(resolve => setTimeout(resolve, 100))
      }
    }

    isProcessing = false
  }

  /**
   * Queue an episode for sending
   */
  function queueEpisode(name: string, content: string, source: string) {
    if (!ENABLED) return

    const timestamp = new Date().toISOString()
    pendingQueue.push({ name, content, source, timestamp })

    // Start processing if not already running
    setTimeout(() => processQueue(), 0)
  }

  /**
   * Create a concise episode for a user message
   */
  async function captureUserMessage(content: string) {
    const git = await getGitContext()
    const timestamp = new Date().toISOString()

    const truncated = truncateContent(content, MAX_CONTENT_LENGTH)
    const episodeName = `User: ${truncated.substring(0, 50)}...`

    const episodeContent = `User asked: "${truncated}"

Project: ${project.name}
Branch: ${git.branch}
Time: ${timestamp}`

    queueEpisode(episodeName, episodeContent, "opencode-user")
  }

  /**
   * Create a concise episode for an assistant message
   */
  async function captureAssistantMessage(content: string, tools: string[] = []) {
    const git = await getGitContext()
    const timestamp = new Date().toISOString()

    const truncated = truncateContent(content, MAX_CONTENT_LENGTH)
    const episodeName = `Assistant: ${truncated.substring(0, 50)}...`

    const toolsUsed = tools.length > 0 ? `\nTools: ${tools.join(", ")}` : ""

    const episodeContent = `Assistant responded: "${truncated}"${toolsUsed}

Project: ${project.name}
Branch: ${git.branch}
Time: ${timestamp}`

    queueEpisode(episodeName, episodeContent, "opencode-assistant")
  }

  /**
   * Create a concise episode for tool usage
   */
  async function captureToolUse(toolName: string, args: any, result?: any) {
    const git = await getGitContext()
    const timestamp = new Date().toISOString()

    // Simplify args representation
    const argsStr = JSON.stringify(args, null, 2)
    const truncatedArgs = truncateContent(argsStr, 200)

    const episodeName = `Tool: ${toolName}`

    const episodeContent = `Used tool: ${toolName}
Args: ${truncatedArgs}

Project: ${project.name}
Branch: ${git.branch}
Time: ${timestamp}`

    queueEpisode(episodeName, episodeContent, "opencode-tool")
  }

  /**
   * Create a concise episode for file changes
   */
  async function captureFileChange(operation: string, filePath: string) {
    const git = await getGitContext()
    const timestamp = new Date().toISOString()

    const episodeName = `${operation}: ${filePath}`

    const episodeContent = `File ${operation}: ${filePath}

Project: ${project.name}
Branch: ${git.branch}
Commit: ${git.commit}
Time: ${timestamp}`

    queueEpisode(episodeName, episodeContent, "opencode-file")
  }

  /**
   * Create a session marker episode
   */
  async function captureSessionEvent(eventType: string) {
    const git = await getGitContext()
    const timestamp = new Date().toISOString()

    const episodeName = `Session ${eventType}: ${project.name}`

    const episodeContent = `OpenCode session ${eventType}

Project: ${project.name}
Branch: ${git.branch}
Directory: ${directory}
Time: ${timestamp}`

    queueEpisode(episodeName, episodeContent, "opencode-session")
  }

  // Track current conversation turn for tool attribution
  let currentTurnTools: string[] = []

  if (ENABLED) {
    console.log(`[Graphiti] Context collector enabled for ${project.name}`)
  }

  return {
    /**
     * Capture user messages
     */
    "user.message": async ({ message }) => {
      if (!message.content) return

      // Flush any pending assistant message with tools before new user message
      if (currentTurnTools.length > 0) {
        currentTurnTools = []
      }

      await captureUserMessage(message.content)
    },

    /**
     * Capture AI responses
     */
    "assistant.message": async ({ message }) => {
      if (!message.content) return

      // Capture with any tools that were used in this turn
      await captureAssistantMessage(message.content, currentTurnTools)

      // Reset tool tracking for next turn
      currentTurnTools = []
    },

    /**
     * Capture tool executions
     */
    "tool.execute.after": async (input, output) => {
      const toolName = input.tool

      // Track tool for current assistant turn
      currentTurnTools.push(toolName)

      // Capture tool usage as separate episode
      await captureToolUse(toolName, output.args, output.result)

      // Special handling for file operations
      if (toolName === "write" || toolName === "edit") {
        const filePath = output.args.filePath || output.args.file_path
        if (filePath) {
          await captureFileChange(toolName === "write" ? "created" : "edited", filePath)
        }
      }
    },

    /**
     * Handle session events
     */
    event: async ({ event }) => {
      if (event.type === "session.start") {
        await captureSessionEvent("started")
      }

      if (event.type === "session.idle" || event.type === "session.end") {
        await captureSessionEvent("ended")

        // Wait for queue to finish processing
        while (isProcessing || pendingQueue.length > 0) {
          await new Promise(resolve => setTimeout(resolve, 100))
        }
      }
    },
  }
}

export default GraphitiContextCollector
