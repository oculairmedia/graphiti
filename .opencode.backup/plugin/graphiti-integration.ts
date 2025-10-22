import type { Plugin, tool } from "@opencode-ai/plugin"

/**
 * Graphiti Knowledge Graph Integration Plugin for OpenCode
 *
 * This plugin provides tools to interact with the Graphiti knowledge graph,
 * allowing OpenCode to store and retrieve context from long-term memory.
 *
 * Features:
 * - Automatic context capture (file ops, commands, git info)
 * - Retry logic with exponential backoff
 * - Rate limiting and request throttling
 * - MCP server support as alternative to REST API
 * - Health checks and configuration validation
 */

interface RetryOptions {
  maxRetries: number
  initialDelay: number
  maxDelay: number
  backoffMultiplier: number
}

interface RateLimiter {
  tokens: number
  lastRefill: number
  capacity: number
  refillRate: number
}

export const GraphitiPlugin: Plugin = async ({ project, client, $, directory, worktree }) => {
  // Configuration
  const GRAPHITI_API_URL = process.env.GRAPHITI_API_URL || "http://localhost:8003"
  const GRAPHITI_MCP_URL = process.env.GRAPHITI_MCP_URL || "http://localhost:3010"
  const USE_MCP = process.env.GRAPHITI_USE_MCP === "true"
  const GROUP_ID = process.env.GRAPHITI_GROUP_ID || "opencode-session"
  const ENABLE_AUTO_CAPTURE = process.env.GRAPHITI_AUTO_CAPTURE !== "false"

  // Retry configuration
  const retryOptions: RetryOptions = {
    maxRetries: 3,
    initialDelay: 1000,
    maxDelay: 10000,
    backoffMultiplier: 2,
  }

  // Rate limiter (10 requests per second)
  const rateLimiter: RateLimiter = {
    tokens: 10,
    lastRefill: Date.now(),
    capacity: 10,
    refillRate: 10, // tokens per second
  }

  /**
   * Refill rate limiter tokens based on elapsed time
   */
  function refillTokens() {
    const now = Date.now()
    const elapsed = (now - rateLimiter.lastRefill) / 1000
    const tokensToAdd = elapsed * rateLimiter.refillRate

    rateLimiter.tokens = Math.min(rateLimiter.capacity, rateLimiter.tokens + tokensToAdd)
    rateLimiter.lastRefill = now
  }

  /**
   * Wait for rate limiter token availability
   */
  async function waitForToken(): Promise<void> {
    refillTokens()

    if (rateLimiter.tokens >= 1) {
      rateLimiter.tokens -= 1
      return
    }

    // Calculate wait time
    const tokensNeeded = 1 - rateLimiter.tokens
    const waitMs = (tokensNeeded / rateLimiter.refillRate) * 1000

    await new Promise(resolve => setTimeout(resolve, waitMs))
    rateLimiter.tokens = 0 // We'll use the token immediately after waiting
  }

  /**
   * Retry wrapper with exponential backoff
   */
  async function withRetry<T>(
    fn: () => Promise<T>,
    options: RetryOptions = retryOptions,
    context = "operation"
  ): Promise<T> {
    let lastError: Error | null = null
    let delay = options.initialDelay

    for (let attempt = 0; attempt <= options.maxRetries; attempt++) {
      try {
        await waitForToken()
        return await fn()
      } catch (error) {
        lastError = error as Error

        if (attempt < options.maxRetries) {
          console.warn(
            `[Graphiti] ${context} failed (attempt ${attempt + 1}/${options.maxRetries + 1}), ` +
            `retrying in ${delay}ms: ${lastError.message}`
          )
          await new Promise(resolve => setTimeout(resolve, delay))
          delay = Math.min(delay * options.backoffMultiplier, options.maxDelay)
        }
      }
    }

    throw new Error(`[Graphiti] ${context} failed after ${options.maxRetries + 1} attempts: ${lastError?.message}`)
  }

  /**
   * Get current git information
   */
  async function getGitInfo() {
    try {
      const branch = await $`git rev-parse --abbrev-ref HEAD`.text()
      const commit = await $`git rev-parse --short HEAD`.text()
      const remote = await $`git config --get remote.origin.url`.text()

      return {
        branch: branch.trim(),
        commit: commit.trim(),
        remote: remote.trim(),
      }
    } catch {
      return null
    }
  }

  /**
   * Health check for Graphiti API
   */
  async function healthCheck(): Promise<boolean> {
    try {
      const endpoint = USE_MCP ? GRAPHITI_MCP_URL : GRAPHITI_API_URL
      const response = await fetch(`${endpoint}/health`, {
        signal: AbortSignal.timeout(5000)
      })
      return response.ok
    } catch (error) {
      console.warn(`[Graphiti] Health check failed: ${(error as Error).message}`)
      return false
    }
  }

  /**
   * Add an episode to Graphiti memory via REST API
   */
  async function addMemoryREST(name: string, content: string, source = "opencode") {
    return await withRetry(
      async () => {
        const response = await fetch(`${GRAPHITI_API_URL}/v1/add-episode`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name,
            episode_body: content,
            source,
            group_id: GROUP_ID,
          }),
          signal: AbortSignal.timeout(30000),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        return await response.json()
      },
      retryOptions,
      `addMemory(${name})`
    )
  }

  /**
   * Add an episode to Graphiti memory via MCP server
   */
  async function addMemoryMCP(name: string, content: string, source = "opencode") {
    return await withRetry(
      async () => {
        const response = await fetch(`${GRAPHITI_MCP_URL}/mcp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0",
            id: Date.now(),
            method: "tools/call",
            params: {
              name: "add_memory",
              arguments: {
                name,
                episode_body: content,
                source,
                group_id: GROUP_ID,
              },
            },
          }),
          signal: AbortSignal.timeout(30000),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const result = await response.json()
        if (result.error) {
          throw new Error(result.error.message)
        }

        return result.result
      },
      retryOptions,
      `addMemoryMCP(${name})`
    )
  }

  /**
   * Add memory using configured method (REST or MCP)
   */
  async function addMemory(name: string, content: string, source = "opencode") {
    return USE_MCP
      ? await addMemoryMCP(name, content, source)
      : await addMemoryREST(name, content, source)
  }

  /**
   * Search Graphiti memory via REST API
   */
  async function searchMemoryREST(query: string, maxResults = 10) {
    return await withRetry(
      async () => {
        const response = await fetch(`${GRAPHITI_API_URL}/v1/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            group_ids: [GROUP_ID],
            max_facts: maxResults,
          }),
          signal: AbortSignal.timeout(30000),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        return await response.json()
      },
      retryOptions,
      `searchMemory(${query})`
    )
  }

  /**
   * Search Graphiti memory via MCP server
   */
  async function searchMemoryMCP(query: string, maxResults = 10) {
    return await withRetry(
      async () => {
        const response = await fetch(`${GRAPHITI_MCP_URL}/mcp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jsonrpc: "2.0",
            id: Date.now(),
            method: "tools/call",
            params: {
              name: "search_memory_facts",
              arguments: {
                query,
                group_ids: [GROUP_ID],
                max_facts: maxResults,
              },
            },
          }),
          signal: AbortSignal.timeout(30000),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const result = await response.json()
        if (result.error) {
          throw new Error(result.error.message)
        }

        return result.result
      },
      retryOptions,
      `searchMemoryMCP(${query})`
    )
  }

  /**
   * Search memory using configured method (REST or MCP)
   */
  async function searchMemory(query: string, maxResults = 10) {
    return USE_MCP
      ? await searchMemoryMCP(query, maxResults)
      : await searchMemoryREST(query, maxResults)
  }

  // Run health check on initialization
  const isHealthy = await healthCheck()
  if (!isHealthy) {
    console.warn(
      `[Graphiti] Warning: Unable to connect to Graphiti API at ${USE_MCP ? GRAPHITI_MCP_URL : GRAPHITI_API_URL}. ` +
      `Plugin will continue but features may be unavailable.`
    )
  } else {
    console.log(
      `[Graphiti] ✓ Connected to Graphiti ${USE_MCP ? 'MCP server' : 'API'} at ${USE_MCP ? GRAPHITI_MCP_URL : GRAPHITI_API_URL}`
    )
  }

  return {
    // Hook into session events to store context
    event: async ({ event }) => {
      if (!ENABLE_AUTO_CAPTURE) return

      if (event.type === "session.idle") {
        try {
          const gitInfo = await getGitInfo()
          const timestamp = new Date().toISOString()

          const contextData = {
            project: project.name,
            directory,
            timestamp,
            git: gitInfo,
          }

          await addMemory(
            `OpenCode session completed - ${project.name}`,
            `Session completed at ${timestamp}. Project: ${project.name}, Branch: ${gitInfo?.branch || 'unknown'}, Directory: ${directory}`,
            "opencode-session"
          )

          console.log("📊 [Graphiti] Session context stored in knowledge graph")
        } catch (error) {
          console.error("[Graphiti] Failed to store session context:", (error as Error).message)
        }
      }
    },

    // Hook into tool execution to capture important operations
    "tool.execute.after": async (input, output) => {
      if (!ENABLE_AUTO_CAPTURE) return

      try {
        // Capture file edits and writes to memory
        if (input.tool === "edit" || input.tool === "write") {
          const filePath = output.args.filePath || output.args.file_path
          const operation = input.tool === "edit" ? "edited" : "created"
          const gitInfo = await getGitInfo()
          const timestamp = new Date().toISOString()

          await addMemory(
            `File ${operation}: ${filePath}`,
            `[${timestamp}] OpenCode ${operation} file: ${filePath}\n` +
            `Project: ${project.name}\n` +
            `Branch: ${gitInfo?.branch || 'unknown'}\n` +
            `Commit: ${gitInfo?.commit || 'unknown'}`,
            "opencode-tool"
          )
        }

        // Capture bash command executions
        if (input.tool === "bash") {
          const command = output.args.command
          const gitInfo = await getGitInfo()
          const timestamp = new Date().toISOString()

          await addMemory(
            `Command: ${command.substring(0, 50)}${command.length > 50 ? '...' : ''}`,
            `[${timestamp}] Executed in ${directory}:\n` +
            `Command: ${command}\n` +
            `Project: ${project.name}\n` +
            `Branch: ${gitInfo?.branch || 'unknown'}`,
            "opencode-tool"
          )
        }
      } catch (error) {
        // Silent failure for auto-capture to avoid disrupting workflow
        console.debug("[Graphiti] Auto-capture failed:", (error as Error).message)
      }
    },

    // Custom tools for Graphiti integration
    tool: {
      graphiti_add_memory: tool({
        description: "Store information in Graphiti knowledge graph for long-term context retention",
        args: {
          name: tool.schema.string().describe("Short name/title for this memory"),
          content: tool.schema.string().describe("The content to store in memory"),
          source: tool.schema.string().optional().describe("Source type (default: opencode)"),
        },
        async execute(args, ctx) {
          try {
            const gitInfo = await getGitInfo()
            const timestamp = new Date().toISOString()

            const enrichedContent = `[${timestamp}]\n${args.content}\n\n` +
              `Context: ${project.name} (${gitInfo?.branch || 'unknown'})`

            await addMemory(args.name, enrichedContent, args.source || "opencode")

            return `✓ Memory stored in Graphiti: ${args.name}`
          } catch (error) {
            return `✗ Failed to store memory: ${(error as Error).message}`
          }
        },
      }),

      graphiti_search: tool({
        description: "Search Graphiti knowledge graph for relevant context and facts",
        args: {
          query: tool.schema.string().describe("Search query to find relevant information"),
          max_results: tool.schema.number().optional().describe("Maximum number of results (default: 10)"),
        },
        async execute(args, ctx) {
          try {
            const results = await searchMemory(args.query, args.max_results || 10)

            if (!results.edges || results.edges.length === 0) {
              return "No relevant memories found in Graphiti"
            }

            const facts = results.edges.map((edge: any, i: number) =>
              `${i + 1}. ${edge.fact} (relevance: ${edge.score?.toFixed(2) || 'N/A'})`
            ).join("\n")

            return `Found ${results.edges.length} relevant facts:\n\n${facts}`
          } catch (error) {
            return `✗ Search failed: ${(error as Error).message}`
          }
        },
      }),

      graphiti_get_context: tool({
        description: "Get recent context from Graphiti for the current project",
        args: {
          limit: tool.schema.number().optional().describe("Number of recent items to retrieve (default: 5)"),
        },
        async execute(args, ctx) {
          try {
            const gitInfo = await getGitInfo()
            const searchQuery = `Recent activity in ${project.name} ${gitInfo?.branch ? `on branch ${gitInfo.branch}` : ''}`
            const results = await searchMemory(searchQuery, args.limit || 5)

            if (!results.edges || results.edges.length === 0) {
              return "No recent context found in Graphiti for this project"
            }

            const context = results.edges.map((edge: any, i: number) =>
              `${i + 1}. ${edge.fact}`
            ).join("\n")

            return `Recent project context (${project.name}, ${gitInfo?.branch || 'unknown'}):\n\n${context}`
          } catch (error) {
            return `✗ Failed to get context: ${(error as Error).message}`
          }
        },
      }),

      graphiti_health: tool({
        description: "Check Graphiti API health and configuration status",
        args: {},
        async execute(args, ctx) {
          try {
            const isHealthy = await healthCheck()
            const gitInfo = await getGitInfo()

            return [
              `Graphiti Health Status`,
              `=====================`,
              `API Endpoint: ${USE_MCP ? GRAPHITI_MCP_URL : GRAPHITI_API_URL}`,
              `Connection Type: ${USE_MCP ? 'MCP Server' : 'REST API'}`,
              `Status: ${isHealthy ? '✓ Healthy' : '✗ Unreachable'}`,
              `Group ID: ${GROUP_ID}`,
              `Auto-capture: ${ENABLE_AUTO_CAPTURE ? 'Enabled' : 'Disabled'}`,
              `Rate Limit: ${rateLimiter.capacity} req/sec`,
              ``,
              `Current Context:`,
              `- Project: ${project.name}`,
              `- Directory: ${directory}`,
              `- Git Branch: ${gitInfo?.branch || 'N/A'}`,
              `- Git Commit: ${gitInfo?.commit || 'N/A'}`,
            ].join("\n")
          } catch (error) {
            return `✗ Health check failed: ${(error as Error).message}`
          }
        },
      }),
    },
  }
}

export default GraphitiPlugin
