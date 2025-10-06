import type { Plugin, tool } from "@opencode-ai/plugin"
import { ContextSubmissionEngine, handleContextSubmission, handleProjectContextSubmission } from './handlers/context-submission'
import { handlePreResponseSearch, handleInterCallSearch, handleKnowledgePersistence, handleSessionLearning } from './handlers/core-handlers'
import { ContextAnalyzer } from './analysis/context-analyzer'
import { KnowledgeManager } from './handlers/knowledge-manager'
import { GraphitiClient } from './clients/graphiti-client'
import { createPrivacyFilter } from './privacy/privacy-filter'
import { loadGraphitiConfig } from './config/graphiti-config'
import type { GraphitiPluginConfig, SessionContext, ContextChange } from './types'

export const GraphitiIntegrationPlugin: Plugin = async ({ 
  project, 
  client, 
  $, 
  directory, 
  worktree 
}) => {
  // Load configuration
  const config = loadGraphitiConfig(project)
  
  // Initialize core components
  const graphitiClient = new GraphitiClient({
    endpoint: config.endpoint,
    groupId: config.groupId,
    apiKey: config.apiKey
  })
  
  const privacyFilter = createPrivacyFilter()
  const contextAnalyzer = new ContextAnalyzer()
  const knowledgeManager = new KnowledgeManager(graphitiClient)
  
  // Initialize context submission engine
  const contextSubmissionEngine = new ContextSubmissionEngine(
    graphitiClient,
    privacyFilter,
    config.contextSubmission
  )
  
  // Session context tracking
  const sessionContext: SessionContext = {
    sessionId: generateSessionId(),
    sessionDuration: 0,
    activityLevel: 'low',
    project: project ? {
      name: project.name,
      path: project.path,
      primaryLanguage: detectPrimaryLanguage(project.path),
      framework: detectFramework(project.path)
    } : undefined,
    files: [],
    toolExecutions: [],
    focusAreas: []
  }
  
  // Start session tracking
  const sessionStartTime = Date.now()
  
  return {
    // Pre-response knowledge retrieval
    "chat.before": async (input, context) => {
      if (!config.preResponseSearch.enabled) return input
      
      try {
        const enhancedInput = await handlePreResponseSearch(input, context, graphitiClient, config)
        
        // Update session context
        sessionContext.focusAreas.push(extractTopicsFromMessage(input.message))
        updateSessionActivity(sessionContext, 'chat')
        
        return enhancedInput
      } catch (error) {
        console.warn("Pre-response search failed:", error)
        return input
      }
    },
    
    // Inter-call contextual search
    "tool.execute.before": async (input, context) => {
      if (!config.interCallSearch.enabled) return input
      
      try {
        const enhancedInput = await handleInterCallSearch(input, context, graphitiClient, contextAnalyzer, config)
        
        // Track tool execution
        sessionContext.toolExecutions?.push({
          tool: input.tool,
          operation: extractOperation(input.tool, input.args),
          filePath: extractFilePath(input.args),
          timestamp: new Date().toISOString(),
          success: true, // Will be updated in after hook
          duration: 0
        })
        
        // Update session activity
        updateSessionActivity(sessionContext, 'tool')
        
        return enhancedInput
      } catch (error) {
        console.warn("Inter-call search failed:", error)
        return input
      }
    },
    
    // Track tool execution results
    "tool.execute.after": async (input, output, context) => {
      const lastExecution = sessionContext.toolExecutions?.[sessionContext.toolExecutions.length - 1]
      if (lastExecution) {
        lastExecution.success = !output.error
        lastExecution.duration = Date.now() - new Date(lastExecution.timestamp).getTime()
      }
      
      // Track file access
      const filePath = extractFilePath(input.args)
      if (filePath && input.tool === 'read') {
        sessionContext.files?.push({
          path: filePath,
          extension: getFileExtension(filePath),
          size: output.result?.length || 0,
          lastModified: new Date().toISOString()
        })
      }
      
      // Submit real-time context for significant operations
      if (config.contextSubmission.enabled) {
        await contextSubmissionEngine.submitRealTimeContext({
          type: 'tool_executed',
          data: {
            tool: input.tool,
            success: !output.error,
            filePath: filePath,
            duration: lastExecution?.duration
          },
          timestamp: Date.now(),
          source: 'tool_execution_hook'
        })
      }
    },
    
    // Knowledge persistence after responses
    "chat.after": async (input, output, context) => {
      if (!config.knowledgePersistence.enabled) return
      
      try {
        await handleKnowledgePersistence(input, output, context, knowledgeManager, config)
        
        // Update session duration
        sessionContext.sessionDuration = Date.now() - sessionStartTime
        
        // Submit session context periodically
        if (config.contextSubmission.enabled && shouldSubmitSessionContext(sessionContext)) {
          await contextSubmissionEngine.submitSessionContext(sessionContext)
        }
      } catch (error) {
        console.warn("Knowledge persistence failed:", error)
      }
    },
    
    // Session learning and summarization
    "session.idle": async ({ session }) => {
      try {
        // Final session context submission
        sessionContext.sessionDuration = Date.now() - sessionStartTime
        
        if (config.contextSubmission.enabled) {
          await contextSubmissionEngine.submitSessionContext(sessionContext)
        }
        
        // Session learning
        await handleSessionLearning(session, knowledgeManager, config)
      } catch (error) {
        console.warn("Session learning failed:", error)
      }
    },
    
    // Real-time context submission
    "context.change": async (context: ContextChange) => {
      if (!config.contextSubmission.enabled) return
      
      try {
        await handleContextSubmission(context, contextSubmissionEngine)
      } catch (error) {
        console.warn("Context submission failed:", error)
      }
    },
    
    // Project context discovery
    "project.open": async ({ project }) => {
      if (!config.contextSubmission.enabled) return
      
      try {
        await handleProjectContextSubmission(project, contextSubmissionEngine)
        
        // Update session project context
        sessionContext.project = {
          name: project.name,
          path: project.path,
          primaryLanguage: detectPrimaryLanguage(project.path),
          framework: detectFramework(project.path)
        }
      } catch (error) {
        console.warn("Project context submission failed:", error)
      }
    },
    
    // Custom tools for direct Graphiti interaction
    tool: {
      searchMemory: tool({
        description: "Search Graphiti knowledge graph for relevant information",
        args: {
          query: tool.schema.string({
            description: "Search query for knowledge graph"
          }),
          entityTypes: tool.schema.array(tool.schema.string()).optional({
            description: "Filter by specific entity types (Requirement, Preference, Procedure, etc.)"
          }),
          maxResults: tool.schema.number().default(10).min(1).max(50)({
            description: "Maximum number of results to return"
          }),
          includeRelationships: tool.schema.boolean().default(false)({
            description: "Include relationship information in results"
          })
        },
        async execute(args, ctx) {
          try {
            const results = await graphitiClient.searchNodes({
              query: args.query,
              entityTypes: args.entityTypes,
              maxResults: args.maxResults
            })
            
            if (args.includeRelationships) {
              const facts = await graphitiClient.searchFacts({
                query: args.query,
                maxResults: Math.min(args.maxResults, 10)
              })
              
              return {
                nodes: results,
                relationships: facts,
                summary: `Found ${results.nodes?.length || 0} entities and ${facts.facts?.length || 0} relationships`
              }
            }
            
            return {
              nodes: results,
              summary: `Found ${results.nodes?.length || 0} entities matching "${args.query}"`
            }
          } catch (error) {
            throw new Error(`Knowledge search failed: ${error.message}`)
          }
        }
      }),
      
      saveInsight: tool({
        description: "Save an insight or learning to the knowledge graph",
        args: {
          title: tool.schema.string({
            description: "Title or brief description of the insight"
          }),
          content: tool.schema.string({
            description: "Detailed content of the insight"
          }),
          category: tool.schema.string().default("general")({
            description: "Category: technical, business, process, lesson_learned, best_practice, general"
          }),
          tags: tool.schema.array(tool.schema.string()).optional({
            description: "Tags or keywords related to the insight"
          }),
          priority: tool.schema.enum(["low", "medium", "high", "critical"]).default("medium")({
            description: "Priority level of the insight"
          })
        },
        async execute(args, ctx) {
          try {
            const result = await knowledgeManager.saveInsight({
              title: args.title,
              content: args.content,
              category: args.category,
              relatedEntities: args.tags?.join(", ") || "",
              priority: args.priority,
              groupId: config.groupId
            })
            
            return {
              success: true,
              message: `Insight "${args.title}" saved successfully`,
              category: args.category,
              priority: args.priority,
              searchTips: [
                `Search for: "${args.title}"`,
                `Category search: "${args.category}"`,
                ...(args.tags || []).map(tag => `Tag search: "${tag}"`)
              ]
            }
          } catch (error) {
            throw new Error(`Failed to save insight: ${error.message}`)
          }
        }
      }),
      
      queryKnowledge: tool({
        description: "Query knowledge graph for comprehensive information on a topic",
        args: {
          topic: tool.schema.string({
            description: "Topic or domain to query comprehensive information about"
          }),
          maxResults: tool.schema.number().default(10).min(1).max(20)({
            description: "Maximum number of results to return"
          }),
          includeFacts: tool.schema.boolean().default(true)({
            description: "Include factual relationships in the response"
          }),
          focusAreas: tool.schema.array(tool.schema.string()).optional({
            description: "Specific focus areas within the topic"
          })
        },
        async execute(args, ctx) {
          try {
            // This would use the query_knowledge prompt from the MCP server
            const query = args.focusAreas ? 
              `${args.topic} ${args.focusAreas.join(' ')}` : 
              args.topic
            
            const [nodes, facts] = await Promise.all([
              graphitiClient.searchNodes({
                query,
                maxResults: args.maxResults
              }),
              args.includeFacts ? graphitiClient.searchFacts({
                query,
                maxResults: Math.min(args.maxResults, 15)
              }) : Promise.resolve({ facts: [] })
            ])
            
            return {
              topic: args.topic,
              entities: nodes.nodes || [],
              relationships: facts.facts || [],
              summary: `Found ${nodes.nodes?.length || 0} entities and ${facts.facts?.length || 0} relationships related to "${args.topic}"`,
              searchedFor: query
            }
          } catch (error) {
            throw new Error(`Knowledge query failed: ${error.message}`)
          }
        }
      }),
      
      submitContext: tool({
        description: "Manually submit current context to knowledge graph",
        args: {
          includeFiles: tool.schema.boolean().default(true)({
            description: "Include file information in context submission"
          }),
          includeToolHistory: tool.schema.boolean().default(true)({
            description: "Include tool execution history"
          }),
          description: tool.schema.string().optional({
            description: "Optional description of the current context"
          })
        },
        async execute(args, ctx) {
          try {
            // Update session context with current information
            sessionContext.sessionDuration = Date.now() - sessionStartTime
            
            // Filter context based on arguments
            const contextToSubmit = {
              ...sessionContext,
              files: args.includeFiles ? sessionContext.files : [],
              toolExecutions: args.includeToolHistory ? sessionContext.toolExecutions : []
            }
            
            if (args.description) {
              contextToSubmit.focusAreas.push(args.description)
            }
            
            await contextSubmissionEngine.submitSessionContext(contextToSubmit)
            
            return {
              success: true,
              message: "Context submitted successfully to knowledge graph",
              submittedAt: new Date().toISOString(),
              contextSummary: {
                sessionDuration: `${Math.round(sessionContext.sessionDuration / 1000)}s`,
                filesAccessed: contextToSubmit.files?.length || 0,
                toolsUsed: contextToSubmit.toolExecutions?.length || 0,
                activityLevel: sessionContext.activityLevel
              }
            }
          } catch (error) {
            throw new Error(`Context submission failed: ${error.message}`)
          }
        }
      })
    }
  }
}

// Helper functions
function generateSessionId(): string {
  return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

function extractTopicsFromMessage(message: string): string {
  // Simple topic extraction - in production, use more sophisticated NLP
  const words = message.toLowerCase().split(/\s+/)
  const topics = words.filter(word => 
    word.length > 4 && 
    !['about', 'could', 'would', 'should', 'there', 'where', 'which'].includes(word)
  )
  return topics.slice(0, 3).join(' ')
}

function updateSessionActivity(context: SessionContext, activityType: 'chat' | 'tool'): void {
  const now = Date.now()
  const recentActivity = context.toolExecutions?.filter(
    exec => now - new Date(exec.timestamp).getTime() < 60000 // Last minute
  ).length || 0
  
  if (recentActivity > 5) {
    context.activityLevel = 'high'
  } else if (recentActivity > 2) {
    context.activityLevel = 'medium'
  } else {
    context.activityLevel = 'low'
  }
}

function extractOperation(tool: string, args: any): string {
  switch (tool) {
    case 'read':
      return 'reading file'
    case 'write':
      return 'writing file'
    case 'edit':
      return 'editing file'
    case 'bash':
      return 'executing command'
    case 'glob':
      return 'searching files'
    case 'grep':
      return 'searching content'
    default:
      return tool
  }
}

function extractFilePath(args: any): string | undefined {
  return args?.filePath || args?.path || args?.file
}

function getFileExtension(filePath: string): string {
  const parts = filePath.split('.')
  return parts.length > 1 ? `.${parts.pop()}` : ''
}

function detectPrimaryLanguage(projectPath: string): string | undefined {
  // Simple detection based on common files - enhance as needed
  if (projectPath.includes('package.json')) return 'JavaScript'
  if (projectPath.includes('pyproject.toml') || projectPath.includes('requirements.txt')) return 'Python'
  if (projectPath.includes('Cargo.toml')) return 'Rust'
  if (projectPath.includes('go.mod')) return 'Go'
  return undefined
}

function detectFramework(projectPath: string): string | undefined {
  // Simple framework detection - enhance as needed
  if (projectPath.includes('next.config')) return 'Next.js'
  if (projectPath.includes('nuxt.config')) return 'Nuxt.js'
  if (projectPath.includes('angular.json')) return 'Angular'
  if (projectPath.includes('svelte.config')) return 'Svelte'
  return undefined
}

function shouldSubmitSessionContext(context: SessionContext): boolean {
  // Submit context every 10 minutes or after significant activity
  return context.sessionDuration > 600000 || // 10 minutes
         (context.toolExecutions?.length || 0) % 20 === 0 || // Every 20 tool executions
         context.activityLevel === 'high'
}