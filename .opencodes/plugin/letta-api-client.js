/**
 * Letta API Client Plugin for OpenCode (JavaScript)
 *
 * Direct API integration with Letta server for agent and memory management.
 * No MCP middleware - direct HTTP calls for better performance.
 */

export const LettaApiClient = async ({ project, client, $, directory }) => {
  const LETTA_API_URL = process.env.LETTA_API_URL || "https://letta.oculair.ca"
  const LETTA_PASSWORD = process.env.LETTA_PASSWORD
  const LOG_LEVEL = (process.env.LETTA_LOG_LEVEL || "info").toLowerCase()

  const LOG_PRIORITY = { error: 0, warn: 1, info: 2, debug: 3 }

  function log(level, message, extra) {
    const normalized = level.toLowerCase()
    if ((LOG_PRIORITY[normalized] ?? LOG_PRIORITY.info) > (LOG_PRIORITY[LOG_LEVEL] ?? LOG_PRIORITY.info)) {
      return
    }

    const prefix = "[Letta]"
    const payload = extra ? `${prefix} ${message} ${JSON.stringify(extra)}` : `${prefix} ${message}`

    if (normalized === "error") {
      console.error(payload)
    } else if (normalized === "warn") {
      console.warn(payload)
    } else {
      console.log(payload)
    }
  }

  if (!LETTA_PASSWORD) {
    log("warn", "LETTA_PASSWORD not set - API calls will fail")
  }

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

  async function lettaRequest(endpoint, options = {}) {
    const { signal, cleanup } = createTimeoutController(options.timeout || 10000)

    try {
      const url = `${LETTA_API_URL}/v1/${endpoint.replace(/^\//, "")}`
      const headers = {
        "Authorization": `Bearer ${LETTA_PASSWORD}`,
        "Content-Type": "application/json",
        ...(options.headers || {}),
      }

      log("debug", `API Request: ${options.method || "GET"} ${url}`)

      const response = await fetch(url, {
        method: options.method || "GET",
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
        ...(signal ? { signal } : {}),
      })

      if (!response.ok) {
        const errorText = await response.text().catch(() => "")
        throw new Error(`Letta API error ${response.status}: ${errorText}`)
      }

      const data = await response.json()
      log("debug", `API Response: ${url}`, { status: response.status })
      return data
    } catch (error) {
      log("error", "API request failed", {
        endpoint,
        message: error.message,
        stack: error.stack,
      })
      throw error
    } finally {
      cleanup()
    }
  }

  const api = {
    // Agents
    async listAgents() {
      return await lettaRequest("agents/")
    },

    async getAgent(agentId) {
      return await lettaRequest(`agents/${agentId}`)
    },

    async createAgent(config) {
      return await lettaRequest("agents/", {
        method: "POST",
        body: config,
      })
    },

    async updateAgent(agentId, updates) {
      return await lettaRequest(`agents/${agentId}`, {
        method: "PUT",
        body: updates,
      })
    },

    async deleteAgent(agentId) {
      return await lettaRequest(`agents/${agentId}`, {
        method: "DELETE",
      })
    },

    // Tools
    async listTools() {
      return await lettaRequest("tools/")
    },

    async getTool(toolId) {
      return await lettaRequest(`tools/${toolId}`)
    },

    async createTool(toolConfig) {
      return await lettaRequest("tools/", {
        method: "POST",
        body: toolConfig,
      })
    },

    async attachToolToAgent(agentId, toolId) {
      return await lettaRequest(`agents/${agentId}/tools`, {
        method: "POST",
        body: { tool_id: toolId },
      })
    },

    async detachToolFromAgent(agentId, toolId) {
      return await lettaRequest(`agents/${agentId}/tools/${toolId}`, {
        method: "DELETE",
      })
    },

    async listAgentTools(agentId) {
      return await lettaRequest(`agents/${agentId}/tools`)
    },

    // MCP Servers & Tools
    async listMcpServers() {
      return await lettaRequest("tools/mcp/servers")
    },

    async listMcpServerTools(serverName) {
      return await lettaRequest(`tools/mcp/servers/${serverName}/tools`)
    },

    // Memory Management
    async getAgentMemory(agentId) {
      return await lettaRequest(`agents/${agentId}/memory`)
    },

    async updateAgentMemory(agentId, memory) {
      return await lettaRequest(`agents/${agentId}/memory`, {
        method: "POST",
        body: memory,
      })
    },

    async listMemoryBlocks(agentId) {
      return await lettaRequest(`agents/${agentId}/memory/blocks`)
    },

    async createMemoryBlock(agentId, block) {
      return await lettaRequest(`agents/${agentId}/memory/blocks`, {
        method: "POST",
        body: block,
      })
    },

    async updateMemoryBlock(agentId, blockId, updates) {
      return await lettaRequest(`agents/${agentId}/memory/blocks/${blockId}`, {
        method: "PUT",
        body: updates,
      })
    },

    async deleteMemoryBlock(agentId, blockId) {
      return await lettaRequest(`agents/${agentId}/memory/blocks/${blockId}`, {
        method: "DELETE",
      })
    },

    // Messages
    async sendMessage(agentId, messages) {
      return await lettaRequest(`agents/${agentId}/messages`, {
        method: "POST",
        body: { messages },
        timeout: 30000, // 30s for message processing
      })
    },

    async listMessages(agentId, params = {}) {
      const query = new URLSearchParams(params).toString()
      return await lettaRequest(`agents/${agentId}/messages${query ? `?${query}` : ""}`)
    },

    async getMessage(agentId, messageId) {
      return await lettaRequest(`agents/${agentId}/messages/${messageId}`)
    },

    // Utility
    log,
  }

  log("info", `Letta API client initialized: ${LETTA_API_URL}`)

  return api
}
