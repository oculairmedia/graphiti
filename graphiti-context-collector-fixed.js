/**
 * Graphiti Automatic Context Collection Plugin for OpenCode (JavaScript)
 *
 * Groups conversation turns into logical chunks and uses OpenCode SDK
 * to create concise, AI-generated summaries for Graphiti ingestion.
 *
 * NO individual episodes - only grouped, summarized conversations.
 */

export const GraphitiContextCollector = async ({ project, client, $, directory, worktree }) => {
  const STATE_KEY = "__graphitiContextCollectorState"

  // Dispose any prior instance that might still be holding timers/state after a hot reload
  if (globalThis[STATE_KEY]?.dispose) {
    try {
      globalThis[STATE_KEY].dispose()
    } catch (error) {
      console.warn("[Graphiti] Failed to dispose previous collector instance", error)
    }
  }

  const toInt = (value, fallback) => {
    const parsed = Number.parseInt(value, 10)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  const resolveOpencodeSdkBaseUrl = () => {
    const explicit = process.env.GRAPHITI_SDK_URL?.trim()
    if (explicit) {
      return { url: explicit.replace(/\/$/, ""), source: "env" }
    }

    try {
      const base = client?._client?.getConfig?.()?.baseUrl
      if (typeof base === "string" && base.length > 0) {
        return { url: base.replace(/\/$/, ""), source: "client" }
      }
    } catch (error) {
      console.warn("[Graphiti] Failed to read OpenCode client config", error)
    }

    return { url: "http://127.0.0.1:4096", source: "default" }
  }

  const GRAPHITI_API_URL = process.env.GRAPHITI_API_URL || "http://192.168.50.90:8003"
  const { url: GRAPHITI_SDK_URL, source: SDK_URL_SOURCE } = resolveOpencodeSdkBaseUrl()

  const ENABLED = process.env.GRAPHITI_AUTO_COLLECT !== "false"
  const BUFFER_SIZE = toInt(process.env.GRAPHITI_BUFFER_SIZE || "6", 6) // Group every N messages
  const MAX_BUFFER_CAP = Math.max(BUFFER_SIZE, toInt(process.env.GRAPHITI_BUFFER_CAP || "100", 100)) // Absolute cap to avoid uncontrolled growth
  const AUTO_FLUSH_INTERVAL = toInt(process.env.GRAPHITI_FLUSH_INTERVAL || "60000", 60000) // 60s
  const MAX_SEND_RETRIES = Math.max(1, toInt(process.env.GRAPHITI_SEND_RETRIES || "3", 3))
  const RETRY_DELAY_MS = Math.max(0, toInt(process.env.GRAPHITI_RETRY_DELAY || "2000", 2000))
  const LOG_LEVEL = (process.env.GRAPHITI_LOG_LEVEL || "info").toLowerCase()

  // Dynamic GROUP_ID based on current project
  // Format: opencode-{project-name}
  // Falls back to directory name if project name unavailable
  const projectName = project?.name || directory.split('/').pop() || 'unknown'
  const GROUP_ID = process.env.GRAPHITI_GROUP_ID || `opencode-${projectName}`

  const LOG_PRIORITY = { error: 0, warn: 1, info: 2, debug: 3 }

  function log(level, message, extra) {
    const normalized = level.toLowerCase()
    if ((LOG_PRIORITY[normalized] ?? LOG_PRIORITY.info) > (LOG_PRIORITY[LOG_LEVEL] ?? LOG_PRIORITY.info)) {
      return
    }

    const payload = extra ? `${message} ${JSON.stringify(extra)}` : message

    if (normalized === "error") {
      console.error(payload)
    } else if (normalized === "warn") {
      console.warn(payload)
    } else {
      console.log(payload)
    }
  }

  if (SDK_URL_SOURCE === "default") {
    log("warn", "[Graphiti] OpenCode SDK URL fallback in use", {
      sdkUrl: GRAPHITI_SDK_URL,
    })
  } else if (SDK_URL_SOURCE === "client") {
    log("debug", "[Graphiti] OpenCode SDK URL resolved from client config", {
      sdkUrl: GRAPHITI_SDK_URL,
    })
  } else {
    log("debug", "[Graphiti] OpenCode SDK URL provided via environment", {
      sdkUrl: GRAPHITI_SDK_URL,
    })
  }

  let gitContext = null
  let conversationBuffer = [] // Buffer for grouping
  let flushTimer = null
  let disposed = false
  let flushInProgress = false
  let stateQueue = Promise.resolve()

  function createTimeoutController(timeoutMs) {
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      return { signal: AbortSignal.timeout(timeoutMs), cleanup: () => {} }
    }

    if (typeof AbortController !== "undefined") {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
      return {
        signal: controller.signal,
        cleanup: () => clearTimeout(timeoutId),
      }
    }

    return { signal: undefined, cleanup: () => {} }
  }


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
  function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  async function sendToGraphiti(name, content, source) {
    const timestamp = new Date().toISOString()
    const messagePayload = {
      content,
      uuid: (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `episode-${Date.now()}`,
      name: name || content.substring(0, 60),
      role_type: source === "opencode-session" ? "system" : "assistant",
      role: source,
      timestamp,
      source_description: source,
    }

    const requestBody = {
      group_id: GROUP_ID,
      messages: [messagePayload],
    }

    const { signal, cleanup } = createTimeoutController(15000)

    try {
      log("debug", "[Graphiti] Sending message payload", {
        groupId: GROUP_ID,
        bodyLength: content.length,
        source,
        messageCount: requestBody.messages.length,
      })

      for (let attempt = 1; attempt <= MAX_SEND_RETRIES; attempt += 1) {
        try {
          const response = await fetch(`${GRAPHITI_API_URL}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody),
            ...(signal ? { signal } : {}),
          })

          if (response.ok) {
            log("info", `[Graphiti] ✓ Sent message: ${name}`)
            return true
          }

          const responseText = await response.text().catch(() => "")
          log("warn", "[Graphiti] Failed to send", {
            attempt,
            status: response.status,
            statusText: response.statusText,
            response: responseText,
            requestBody,
          })
        } catch (networkError) {
          log("error", "[Graphiti] Network error", {
            attempt,
            name,
            message: networkError.message,
            stack: networkError.stack,
            requestBody,
          })
        }

        if (attempt < MAX_SEND_RETRIES) {
          await delay(RETRY_DELAY_MS * attempt)
        }
      }

      return false
    } finally {
      cleanup()
    }
  }



  /**
   * Use OpenCode SDK to summarize conversation
   */
  async function summarizeWithSDK(conversationText) {
    const { signal, cleanup } = createTimeoutController(10000) // 10s timeout for SDK

    try {
      const summaryPrompt = `Summarize this OpenCode development conversation in 2-3 concise sentences. Focus on: the task/problem, actions taken, and files/tools involved.

Conversation:
${conversationText}

Provide only the summary, nothing else:`

      const response = await fetch(`${GRAPHITI_SDK_URL}/api/v1/session/prompt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parts: [{ type: "text", text: summaryPrompt }],
        }),
        ...(signal ? { signal } : {}),
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
      log("debug", "[Graphiti] SDK summarization failed, using fallback", {
        message: error.message,
        sdkUrl: GRAPHITI_SDK_URL,
      })
      // Fallback: simple truncation
      return conversationText.substring(0, 500) + "..."
    } finally {
      cleanup()
    }
  }

  /**
   * Flush conversation buffer - create grouped episode with AI summary
   */
  async function flushConversationBuffer() {
    if (flushInProgress || conversationBuffer.length === 0) return

    flushInProgress = true

    // Snapshot buffer to avoid losing messages on failure
    const bufferSnapshot = conversationBuffer.slice()
    conversationBuffer = []

    try {
      // Build conversation text
      const conversationText = bufferSnapshot
      .map(msg => {
        const tools = msg.tools?.length > 0 ? ` [${msg.tools.join(", ")}]` : ""
        return `${msg.role}: ${msg.content}${tools}`
      })
      .join("\n\n")

      // Get AI summary
      const summary = await summarizeWithSDK(conversationText)

      const git = await getGitContext()
      const timestamp = new Date().toISOString()
      const messageCount = bufferSnapshot.length

      // Extract files mentioned in conversation
      const files = [...new Set(
        bufferSnapshot
          .flatMap(msg => msg.content?.match(/[\w\-\.\/]+\.(ts|js|py|md|json|txt)/g) || [])
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

      const sent = await sendToGraphiti(episodeName, episodeContent, "opencode-conversation")

      if (!sent) {
        throw new Error("Failed to send conversation to Graphiti after retries")
      }
    } catch (error) {
      log("error", "[Graphiti] Flush failed", {
        message: error.message,
        stack: error.stack,
      })

      // Restore buffered messages while keeping cap
      conversationBuffer = bufferSnapshot.concat(conversationBuffer)
      if (conversationBuffer.length > MAX_BUFFER_CAP) {
        conversationBuffer = conversationBuffer.slice(-MAX_BUFFER_CAP)
        log("warn", "[Graphiti] Conversation buffer capped", {
          maxBufferCap: MAX_BUFFER_CAP,
          currentLength: conversationBuffer.length,
        })
      }
    } finally {
      flushInProgress = false
    }
  }

  /**
   * Schedule automatic buffer flush
   */
  function scheduleFlush() {
    if (!ENABLED || disposed) return

    stopFlushTimer()

    flushTimer = setTimeout(async () => {
      try {
        await flushConversationBuffer()
      } catch (error) {
        log("error", "[Graphiti] Auto-flush failed", {
          message: error.message,
          stack: error.stack,
        })
      } finally {
        if (!disposed) {
          scheduleFlush() // Reschedule while active
        }
      }
    }, AUTO_FLUSH_INTERVAL)
  }

  function stopFlushTimer() {
    if (flushTimer) {
      clearTimeout(flushTimer)
      flushTimer = null
    }
  }

  function withLock(action) {
    const nextTask = stateQueue.then(async () => {
      if (disposed) return

      try {
        return await action()
      } catch (error) {
        log("error", "[Graphiti] Handler execution failed", {
          message: error.message,
          stack: error.stack,
        })
      }
    })

    // Prevent queue from getting stuck on rejections
    stateQueue = nextTask.catch(() => {})
    return nextTask
  }

  let currentTurnTools = []

  if (ENABLED) {
    console.log(`[Graphiti] Context collector enabled for ${projectName}`)
    console.log(`[Graphiti] Group ID: ${GROUP_ID}`)
    console.log(`[Graphiti] Grouping ${BUFFER_SIZE} messages, auto-flush every ${AUTO_FLUSH_INTERVAL}ms`)
    scheduleFlush() // Start auto-flush timer
  }

  const api = {
    "user.message": async ({ message }) => withLock(async () => {
      if (!message?.content) return

      currentTurnTools = []

      conversationBuffer.push({
        role: "user",
        content: message.content,
        timestamp: new Date().toISOString(),
      })

      if (conversationBuffer.length >= BUFFER_SIZE) {
        await flushConversationBuffer()
      } else if (conversationBuffer.length > MAX_BUFFER_CAP) {
        conversationBuffer = conversationBuffer.slice(-MAX_BUFFER_CAP)
        log("warn", "[Graphiti] Buffer truncated for user message", {
          maxBufferCap: MAX_BUFFER_CAP,
        })
      }
    }),

    "assistant.message": async ({ message }) => withLock(async () => {
      if (!message?.content) return

      conversationBuffer.push({
        role: "assistant",
        content: message.content,
        tools: currentTurnTools.length > 0 ? [...currentTurnTools] : undefined,
        timestamp: new Date().toISOString(),
      })

      currentTurnTools = []

      if (conversationBuffer.length >= BUFFER_SIZE) {
        await flushConversationBuffer()
      } else if (conversationBuffer.length > MAX_BUFFER_CAP) {
        conversationBuffer = conversationBuffer.slice(-MAX_BUFFER_CAP)
        log("warn", "[Graphiti] Buffer truncated for assistant message", {
          maxBufferCap: MAX_BUFFER_CAP,
        })
      }
    }),

    "tool.execute.after": async (input, output) => withLock(async () => {
      if (!input?.tool) return

      if (!currentTurnTools.includes(input.tool)) {
        currentTurnTools.push(input.tool)
      }
    }),

    event: async ({ event }) => withLock(async () => {
      if (!event?.type) return

      if (event.type === "session.start") {
        const git = await getGitContext()
        const timestamp = new Date().toISOString()

        const sent = await sendToGraphiti(
          `Session started: ${project?.name || 'unknown'}`,
          `OpenCode session started

Project: ${project?.name || 'unknown'}
Branch: ${git.branch}
Directory: ${directory}
Time: ${timestamp}`,
          "opencode-session"
        )

        if (!sent) {
          log("warn", "[Graphiti] Failed to record session start")
        }
      }

      if (event.type === "session.idle" || event.type === "session.end") {
        await flushConversationBuffer()

        const git = await getGitContext()
        const timestamp = new Date().toISOString()

        const sent = await sendToGraphiti(
          `Session ended: ${project?.name || 'unknown'}`,
          `OpenCode session ended

Project: ${project?.name || 'unknown'}
Branch: ${git.branch}
Directory: ${directory}
Time: ${timestamp}`,
          "opencode-session"
        )

        if (!sent) {
          log("warn", "[Graphiti] Failed to record session end")
        }

        disposed = true
        stopFlushTimer()
      }
    }),
  }

  const dispose = () => {
    disposed = true
    stopFlushTimer()
    conversationBuffer = []
    currentTurnTools = []
  }

  api.dispose = dispose
  globalThis[STATE_KEY] = { dispose }
  return api
}
