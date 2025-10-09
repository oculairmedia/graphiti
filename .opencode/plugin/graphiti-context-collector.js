/**
 * Graphiti Automatic Context Collection Plugin for OpenCode (JavaScript)
 *
 * Groups conversation turns into logical chunks and uses OpenCode SDK
 * to create concise, AI-generated summaries for Graphiti ingestion.
 *
 * NO individual episodes - only grouped, summarized conversations.
 */

export const GraphitiContextCollector = async ({ project, client, $, directory, worktree }) => {
  const GRAPHITI_API_URL = process.env.GRAPHITI_API_URL || "http://localhost:8003"
  const ENABLED = process.env.GRAPHITI_AUTO_COLLECT !== "false"
  const BUFFER_SIZE = parseInt(process.env.GRAPHITI_BUFFER_SIZE || "6") // Group every N messages
  const AUTO_FLUSH_INTERVAL = parseInt(process.env.GRAPHITI_FLUSH_INTERVAL || "60000") // 60s

  // Dynamic GROUP_ID based on current project
  // Format: opencode-{project-name}
  // Falls back to directory name if project name unavailable
  const projectName = project?.name || directory.split('/').pop() || 'unknown'
  const GROUP_ID = process.env.GRAPHITI_GROUP_ID || `opencode-${projectName}`

  let gitContext = null
  let conversationBuffer = [] // Buffer for grouping
  let flushTimer = null

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
   * Send episode to Graphiti
   */
  async function sendToGraphiti(name, content, source) {
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
        console.warn(`[Graphiti] Failed to send: ${response.statusText}`)
        return false
      }

      console.log(`[Graphiti] ✓ Sent: ${name}`)
      return true
    } catch (error) {
      console.warn(`[Graphiti] Error: ${error.message}`)
      return false
    }
  }

  /**
   * Use OpenCode SDK to summarize conversation
   */
  async function summarizeWithSDK(conversationText) {
    try {
      const summaryPrompt = `Summarize this OpenCode development conversation in 2-3 concise sentences. Focus on: the task/problem, actions taken, and files/tools involved.

Conversation:
${conversationText}

Provide only the summary, nothing else:`

      const response = await fetch("http://localhost:4096/api/v1/session/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parts: [{ type: "text", text: summaryPrompt }],
        }),
      })

      if (!response.ok) throw new Error("SDK request failed")

      const result = await response.json()
      const summary = result.parts
        ?.filter(p => p.type === "text")
        ?.map(p => p.text)
        ?.join(" ")
        ?.trim()

      return summary || conversationText.substring(0, 500)
    } catch (error) {
      console.debug("[Graphiti] SDK summarization failed, using fallback")
      // Fallback: simple truncation
      return conversationText.substring(0, 500) + "..."
    }
  }

  /**
   * Flush conversation buffer - create grouped episode with AI summary
   */
  async function flushConversationBuffer() {
    if (conversationBuffer.length === 0) return

    // Build conversation text
    const conversationText = conversationBuffer
      .map(msg => {
        const tools = msg.tools?.length > 0 ? ` [${msg.tools.join(", ")}]` : ""
        return `${msg.role}: ${msg.content}${tools}`
      })
      .join("\n\n")

    // Get AI summary
    const summary = await summarizeWithSDK(conversationText)

    const git = await getGitContext()
    const timestamp = new Date().toISOString()
    const messageCount = conversationBuffer.length

    // Extract files mentioned in conversation
    const filesPattern = /(?:edited|created|modified|file|src\/|\.ts|\.js|\.py|\.md)/gi
    const files = [...new Set(
      conversationBuffer
        .flatMap(msg => msg.content.match(/[\w\-\.\/]+\.(ts|js|py|md|json|txt)/g) || [])
    )]

    const filesInfo = files.length > 0 ? `\nFiles: ${files.join(", ")}` : ""

    // Create episode name from summary
    const episodeName = `${summary.substring(0, 60)}...`

    const episodeContent = `${summary}

Project: ${project?.name || 'unknown'}
Branch: ${git.branch}
Commit: ${git.commit}
Messages: ${messageCount}${filesInfo}
Time: ${timestamp}`

    await sendToGraphiti(episodeName, episodeContent, "opencode-conversation")

    // Clear buffer
    conversationBuffer = []
  }

  /**
   * Schedule automatic buffer flush
   */
  function scheduleFlush() {
    if (flushTimer) clearTimeout(flushTimer)

    flushTimer = setTimeout(async () => {
      await flushConversationBuffer()
      scheduleFlush() // Reschedule
    }, AUTO_FLUSH_INTERVAL)
  }

  let currentTurnTools = []

  if (ENABLED) {
    console.log(`[Graphiti] Context collector enabled for ${projectName}`)
    console.log(`[Graphiti] Group ID: ${GROUP_ID}`)
    console.log(`[Graphiti] Grouping ${BUFFER_SIZE} messages, auto-flush every ${AUTO_FLUSH_INTERVAL}ms`)
    scheduleFlush() // Start auto-flush timer
  }

  return {
    "user.message": async ({ message }) => {
      if (!message.content) return

      // Reset tool tracking
      if (currentTurnTools.length > 0) {
        currentTurnTools = []
      }

      // Add to conversation buffer
      conversationBuffer.push({
        role: "user",
        content: message.content,
        timestamp: new Date().toISOString(),
      })

      // Flush if buffer is full
      if (conversationBuffer.length >= BUFFER_SIZE) {
        await flushConversationBuffer()
      }
    },

    "assistant.message": async ({ message }) => {
      if (!message.content) return

      // Add to conversation buffer with tools
      conversationBuffer.push({
        role: "assistant",
        content: message.content,
        tools: [...currentTurnTools], // Copy tools array
        timestamp: new Date().toISOString(),
      })

      // Reset tool tracking for next turn
      currentTurnTools = []

      // Flush if buffer is full
      if (conversationBuffer.length >= BUFFER_SIZE) {
        await flushConversationBuffer()
      }
    },

    "tool.execute.after": async (input, output) => {
      // Track tool for current assistant turn
      currentTurnTools.push(input.tool)
    },

    event: async ({ event }) => {
      if (event.type === "session.start") {
        const git = await getGitContext()
        const timestamp = new Date().toISOString()

        // Send session start marker
        await sendToGraphiti(
          `Session started: ${project?.name || 'unknown'}`,
          `OpenCode session started

Project: ${project?.name || 'unknown'}
Branch: ${git.branch}
Directory: ${directory}
Time: ${timestamp}`,
          "opencode-session"
        )
      }

      if (event.type === "session.idle" || event.type === "session.end") {
        // Flush any remaining conversation
        await flushConversationBuffer()

        const git = await getGitContext()
        const timestamp = new Date().toISOString()

        // Send session end marker
        await sendToGraphiti(
          `Session ended: ${project?.name || 'unknown'}`,
          `OpenCode session ended

Project: ${project?.name || 'unknown'}
Branch: ${git.branch}
Directory: ${directory}
Time: ${timestamp}`,
          "opencode-session"
        )

        // Clear timer
        if (flushTimer) {
          clearTimeout(flushTimer)
          flushTimer = null
        }
      }
    },
  }
}
