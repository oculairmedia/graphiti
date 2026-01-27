/**
 * Graphiti Context Collector Plugin for OpenCode
 * 
 * Todo-Boundary Episode Model:
 * - Emits one episode per completed todo item
 * - High information density: Request → Actions → Outcome → Files
 * - Tracks tools and files during task execution
 * - Flushes on todo completion or session end
 */

export const GraphitiContextCollector = async ({ project, client, $, directory, worktree }) => {
  try {
    const STATE_KEY = "__graphitiContextCollectorState"

    // Dispose any prior instance
    if (globalThis[STATE_KEY]?.dispose) {
      try {
        globalThis[STATE_KEY].dispose()
      } catch (error) {
        console.warn("[Graphiti] Failed to dispose previous collector instance", error)
      }
    }

    // Configuration
    const GRAPHITI_API_URL = process.env.GRAPHITI_API_URL || "http://192.168.50.90:8003"
    const ENABLED = process.env.GRAPHITI_AUTO_COLLECT !== "false"
    const LOG_LEVEL = (process.env.GRAPHITI_LOG_LEVEL || "info").toLowerCase()
    const MAX_EPISODE_LENGTH = 2000

    // Dynamic GROUP_ID based on project
    const projectName = project?.name || directory?.split('/').pop() || 'unknown'
    const GROUP_ID = process.env.GRAPHITI_GROUP_ID || `opencode-${projectName}`

    const LOG_PRIORITY = { error: 0, warn: 1, info: 2, debug: 3 }

    function log(level, message, extra) {
      const normalized = level.toLowerCase()
      if ((LOG_PRIORITY[normalized] ?? 2) > (LOG_PRIORITY[LOG_LEVEL] ?? 2)) return
      const payload = extra ? `${message} ${JSON.stringify(extra)}` : message
      if (normalized === "error") console.error(payload)
      else if (normalized === "warn") console.warn(payload)
      else console.log(payload)
    }

    // State
    let gitContext = null
    let disposed = false
    let sentHashes = new Set()
    
    // Task tracking state
    let currentTask = null        // The in_progress todo
    let taskTools = new Set()     // Tools used during this task
    let taskFiles = new Set()     // Files touched during this task
    let taskActions = []          // Key actions/decisions
    let userRequest = null        // The user's original request
    let previousTodos = new Map() // Track todo states to detect completions
    let pendingTodoArgs = null    // Store todowrite args from before hook

    function simpleHash(str) {
      let hash = 0
      for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i)
        hash = ((hash << 5) - hash) + char
        hash = hash & hash
      }
      return hash.toString(36)
    }

    async function getGitContext() {
      if (gitContext) return gitContext
      try {
        const branch = await $`git rev-parse --abbrev-ref HEAD`.text()
        const commit = await $`git rev-parse --short HEAD`.text()
        gitContext = { branch: branch.trim(), commit: commit.trim() }
      } catch {
        gitContext = { branch: "unknown", commit: "unknown" }
      }
      return gitContext
    }

    async function sendToGraphiti(name, content, source, metadata = {}) {
      const hash = simpleHash(content)
      if (sentHashes.has(hash)) {
        log("debug", "[Graphiti] Skipping duplicate content")
        return true
      }

      const messagePayload = {
        content: content.slice(0, MAX_EPISODE_LENGTH),
        uuid: crypto?.randomUUID?.() || `ep-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        name: name?.slice(0, 100) || content.slice(0, 60),
        role_type: source === "session" ? "system" : "assistant",
        role: source,
        timestamp: new Date().toISOString(),
        source_description: `opencode-${source}`,
        metadata
      }

      const requestBody = {
        group_id: GROUP_ID,
        messages: [messagePayload]
      }

      // Log sample output to file for analysis
      try {
        const { existsSync, mkdirSync, appendFileSync } = await import('fs')
        const { join } = await import('path')
        const logDir = '/root/.config/opencode/plugin/logs'
        const logFile = join(logDir, 'graphiti-samples.jsonl')
        
        if (!existsSync(logDir)) {
          mkdirSync(logDir, { recursive: true })
        }
        
        const sample = {
          timestamp: new Date().toISOString(),
          name,
          source,
          group_id: GROUP_ID,
          content_length: content.length,
          content,
          metadata
        }
        appendFileSync(logFile, JSON.stringify(sample) + '\n')
        log("debug", `[Graphiti] Logged sample to ${logFile}`)
      } catch (logErr) {
        log("warn", `[Graphiti] Failed to log sample: ${logErr.message}`)
      }

      try {
        const controller = new AbortController()
        const timeout = setTimeout(() => controller.abort(), 10000)
        
        const response = await fetch(`${GRAPHITI_API_URL}/messages`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
          signal: controller.signal
        })
        
        clearTimeout(timeout)

        if (response.ok) {
          sentHashes.add(hash)
          if (sentHashes.size > 100) {
            const arr = [...sentHashes]
            sentHashes = new Set(arr.slice(-50))
          }
          log("info", `[Graphiti] Sent episode: ${name?.slice(0, 50)}`)
          return true
        }
        
        log("warn", `[Graphiti] Send failed (${response.status})`)
      } catch (err) {
        log("warn", `[Graphiti] Network error: ${err.message}`)
      }
      return false
    }

    function buildTaskEpisode(task, git) {
      const parts = []
      
      // Requestor - who asked (from env)
      const requestor = process.env.GRAPHITI_REQUESTOR || process.env.USER || 'user'
      parts.push(`[Requestor] ${requestor}`)
      
      // Request - what the user wanted
      parts.push(`[Request] ${userRequest || task.content}`)
      
      // Actions - what was done
      if (taskActions.length > 0) {
        parts.push(`[Actions] ${taskActions.slice(0, 5).join(' -> ')}`)
      } else if (taskTools.size > 0) {
        parts.push(`[Actions] Used ${[...taskTools].join(', ')}`)
      }
      
      // Outcome - the task itself
      parts.push(`[Outcome] ${task.content}`)
      
      // Files - what was touched
      if (taskFiles.size > 0) {
        const files = [...taskFiles].slice(0, 10)
        parts.push(`[Files] ${files.join(', ')}${taskFiles.size > 10 ? ` +${taskFiles.size - 10} more` : ''}`)
      }
      
      // Tools summary
      if (taskTools.size > 0) {
        parts.push(`[Tools] ${[...taskTools].join(', ')}`)
      }

      const content = parts.join('\n')
      
      return {
        name: `Task: ${task.content.slice(0, 60)}`,
        content,
        metadata: {
          project: projectName,
          branch: git.branch,
          taskId: task.id,
          tools: [...taskTools],
          files: [...taskFiles],
          priority: task.priority,
          requestor
        }
      }
    }

    async function emitTaskEpisode(task) {
      if (!task) return
      
      const git = await getGitContext()
      const { name, content, metadata } = buildTaskEpisode(task, git)
      
      await sendToGraphiti(name, content, "task", metadata)
      
      // Reset task tracking state
      taskTools.clear()
      taskFiles.clear()
      taskActions = []
      currentTask = null
    }

    function extractFilesFromInput(input) {
      // Extract file paths from tool inputs
      if (input?.filePath) taskFiles.add(input.filePath)
      if (input?.target_filepath) taskFiles.add(input.target_filepath)
      if (input?.file) taskFiles.add(input.file)
      if (input?.path) taskFiles.add(input.path)
      
      // Extract from command strings
      if (input?.command) {
        const fileMatches = input.command.match(/[\w\-\.\/]+\.(ts|js|py|md|json|yml|yaml|sh|css|html|jsx|tsx)/g)
        if (fileMatches) fileMatches.forEach(f => taskFiles.add(f))
      }
    }

    function extractActionFromTool(toolName, input) {
      // Map tool usage to human-readable actions
      const actionMap = {
        'read': `Read ${input?.filePath?.split('/').pop() || 'file'}`,
        'write': `Created ${input?.filePath?.split('/').pop() || 'file'}`,
        'edit': `Edited ${input?.filePath?.split('/').pop() || 'file'}`,
        'morph_edit': `Modified ${input?.target_filepath?.split('/').pop() || 'file'}`,
        'bash': input?.description || 'Ran command',
        'glob': 'Searched files',
        'grep': 'Searched content',
        'task': 'Delegated subtask'
      }
      
      const action = actionMap[toolName]
      if (action && !taskActions.includes(action)) {
        taskActions.push(action)
        // Keep actions list manageable
        if (taskActions.length > 10) taskActions = taskActions.slice(-10)
      }
    }

    if (ENABLED) {
      log("info", `[Graphiti] Todo-boundary collector enabled: ${GROUP_ID}`)
    } else {
      log("info", `[Graphiti] Context collector disabled`)
    }

    const hooks = {
      // Capture user requests
      "chat.message": async (input, output) => {
        if (disposed) return
        
        // Extract user message as potential request context
        const userMsg = input?.message
        if (userMsg) {
          let content = null
          if (typeof userMsg === 'string') {
            content = userMsg
          } else if (userMsg.content && typeof userMsg.content === 'string') {
            content = userMsg.content
          } else if (userMsg.parts && Array.isArray(userMsg.parts)) {
            content = userMsg.parts
              .filter(p => p.type === 'text' && p.text)
              .map(p => p.text)
              .join('\n')
          }
          
          // Store as potential task request (most recent user message)
          if (content && content.trim()) {
            userRequest = content.trim().slice(0, 200)
            log("debug", `[Graphiti] Captured user request: ${userRequest.slice(0, 50)}...`)
          }
        }
      },

      // Capture tool args BEFORE execution (args only available here)
      "tool.execute.before": async (input, output) => {
        if (disposed || !input?.tool) return
        
        const toolName = input.tool
        
        // Store todowrite args for processing in after hook
        if (toolName === 'todowrite' && output?.args?.todos) {
          pendingTodoArgs = output.args.todos
          log("debug", `[Graphiti] Captured todowrite args`)
        }
        
        // Extract files from tool args
        if (output?.args) {
          extractFilesFromInput(output.args)
        }
      },

      // Track tool executions AFTER completion
      "tool.execute.after": async (input, output) => {
        if (disposed || !input?.tool) return
        
        const toolName = input.tool
        
        // Skip internal/meta tools
        if (toolName === 'todoread' || toolName === 'discard' || toolName === 'extract') return
        
        taskTools.add(toolName)
        extractActionFromTool(toolName, output?.metadata || {})
        
        // Process todowrite using args captured from before hook
        if (toolName === 'todowrite' && pendingTodoArgs) {
          const todos = Array.isArray(pendingTodoArgs) 
            ? pendingTodoArgs 
            : (typeof pendingTodoArgs === 'string' ? JSON.parse(pendingTodoArgs) : [])
          
          for (const todo of todos) {
            const prevState = previousTodos.get(todo.id)
            
            // Detect task starting (-> in_progress)
            if (todo.status === 'in_progress' && prevState !== 'in_progress') {
              currentTask = todo
              taskTools.clear()
              taskFiles.clear()
              taskActions = []
              log("info", `[Graphiti] Task started: ${todo.content.slice(0, 50)}`)
            }
            
            // Detect task completion (-> completed)
            if (todo.status === 'completed' && prevState !== 'completed') {
              log("info", `[Graphiti] Task completed: ${todo.content.slice(0, 50)}`)
              await emitTaskEpisode(todo)
            }
            
            // Update state tracking
            previousTodos.set(todo.id, todo.status)
          }
          
          pendingTodoArgs = null  // Clear after processing
        }
        
        log("debug", `[Graphiti] Tool: ${toolName}, Files: ${taskFiles.size}, Actions: ${taskActions.length}`)
      },

      // Handle session lifecycle
      event: async ({ event }) => {
        if (disposed || !event?.type) return

        log("debug", `[Graphiti] Event: ${event.type}`)

        if (event.type === "session.created") {
          const git = await getGitContext()
          await sendToGraphiti(
            `Session: ${projectName}`,
            `OpenCode session started\nProject: ${projectName}\nBranch: ${git.branch}`,
            "session",
            { project: projectName, branch: git.branch, directory }
          )
        }

        if (event.type === "session.deleted" || event.type === "session.idle") {
          // Emit any in-progress task as partial episode
          if (currentTask) {
            log("info", `[Graphiti] Session ending, emitting partial task episode`)
            currentTask.content = `(Partial) ${currentTask.content}`
            await emitTaskEpisode(currentTask)
          }
          disposed = true
        }
      }
    }

    hooks.dispose = () => {
      disposed = true
      taskTools.clear()
      taskFiles.clear()
      taskActions = []
      previousTodos.clear()
      sentHashes.clear()
    }

    globalThis[STATE_KEY] = { dispose: hooks.dispose }
    return hooks

  } catch (error) {
    console.error(`[Graphiti] Init failed: ${error?.message}`)
    return { dispose: () => {} }
  }
}

export default GraphitiContextCollector
