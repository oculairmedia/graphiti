/**
 * Graphiti Knowledge Graph Integration Plugin for OpenCode (JavaScript)
 *
 * This plugin provides tools to interact with the Graphiti knowledge graph.
 * Converted to JavaScript to avoid module import issues in global plugins.
 */

export const GraphitiPlugin = async ({ project, client, $, directory, worktree }) => {
  const GRAPHITI_API_URL = process.env.GRAPHITI_API_URL || "http://localhost:8003"
  const GROUP_ID = process.env.GRAPHITI_GROUP_ID || "opencode-session"

  /**
   * Send episode to Graphiti
   */
  async function sendToGraphiti(name, content, source = "opencode") {
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

      return true
    } catch (error) {
      console.warn(`[Graphiti] Error: ${error.message}`)
      return false
    }
  }

  /**
   * Search Graphiti
   */
  async function searchGraphiti(query, maxResults = 10) {
    try {
      const response = await fetch(`${GRAPHITI_API_URL}/v1/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          group_ids: [GROUP_ID],
          max_facts: maxResults,
        }),
        signal: AbortSignal.timeout(15000),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      return await response.json()
    } catch (error) {
      throw new Error(`Search failed: ${error.message}`)
    }
  }

  console.log(`[Graphiti] Integration plugin loaded for ${project?.name || 'unknown'}`)

  return {
    // No custom tools - use the MCP server for that
    // This plugin focuses on automatic capture only
  }
}
