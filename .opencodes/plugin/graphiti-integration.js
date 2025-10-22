/**
 * Graphiti Knowledge Graph Integration Plugin for OpenCode (JavaScript)
 *
 * This plugin provides tools to interact with the Graphiti knowledge graph.
 * Converted to JavaScript to avoid module import issues in global plugins.
 */

export const GraphitiPlugin = async ({ project, client, $, directory, worktree }) => {
  const GRAPHITI_API_URL = process.env.GRAPHITI_API_URL || "http://192.168.50.90:8003"

  const GROUP_ID = process.env.GRAPHITI_GROUP_ID || "opencode-session"

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

  function buildMessagePayload(name, content, source = "opencode") {
    return {
      content,
      uuid: (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `episode-${Date.now()}`,
      name: name || content.substring(0, 60),
      role_type: source === "system" ? "system" : "assistant",
      role: source,
      timestamp: new Date().toISOString(),
      source_description: source,
    }
  }

  /**
   * Send episode to Graphiti
   */
  async function sendToGraphiti(name, content, source = "opencode") {
    try {
      const payload = {
        group_id: GROUP_ID,
        messages: [buildMessagePayload(name, content, source)],
      }

      const { signal, cleanup } = createTimeoutController(15000)

      try {
        const response = await fetch(`${GRAPHITI_API_URL}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          ...(signal ? { signal } : {}),
        })

        if (!response.ok) {
          console.warn(`[Graphiti] Failed to send: ${response.statusText}`)
          return false
        }

        return true
      } finally {
        cleanup()
      }
    } catch (error) {
      console.warn(`[Graphiti] Error: ${error.message}`)
      return false
    }
  }


  /**
   * Search Graphiti
   */
  async function searchGraphiti(query, maxResults = 10) {
    const { signal, cleanup } = createTimeoutController(15000)

    try {
      const response = await fetch(`${GRAPHITI_API_URL}/v1/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          group_ids: [GROUP_ID],
          max_facts: maxResults,
        }),
        ...(signal ? { signal } : {}),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      return await response.json()
    } catch (error) {
      throw new Error(`Search failed: ${error.message}`)
    } finally {
      cleanup()
    }
  }

  console.log(`[Graphiti] Integration plugin loaded for ${project?.name || 'unknown'}`)

  return {
    // No custom tools - use the MCP server for that
    // This plugin focuses on automatic capture only
  }
}
