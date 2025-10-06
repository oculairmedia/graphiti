import type { 
  SessionContext, 
  FilteredContext, 
  EnrichedContext, 
  ContextSubmission, 
  ProjectContext, 
  RealTimeContext, 
  ContextChange,
  ContextRelationship,
  ContextEntity,
  ContextInsight,
  ContextSubmissionConfig,
  ContextValue,
  GraphitiClient 
} from '../types'
import { PrivacyFilter } from '../privacy/privacy-filter'

export class ContextSubmissionEngine {
  private submissionQueue: ContextSubmission[] = []
  private isProcessing = false
  private config: ContextSubmissionConfig
  
  constructor(
    private graphitiClient: GraphitiClient,
    private privacyFilter: PrivacyFilter,
    config: ContextSubmissionConfig
  ) {
    this.config = config
    this.startPeriodicSubmission()
  }
  
  async submitSessionContext(context: SessionContext): Promise<void> {
    try {
      // Filter sensitive information
      const filteredContext = await this.privacyFilter.filterContext(context)
      
      // Enrich context with metadata
      const enrichedContext = await this.enrichContext(filteredContext)
      
      // Submit to Graphiti
      await this.submitToGraphiti(enrichedContext)
      
    } catch (error) {
      console.warn("Context submission failed:", error)
      // Queue for retry
      this.queueForRetry(context)
    }
  }
  
  async submitProjectContext(project: ProjectContext): Promise<void> {
    try {
      const projectInsights = await this.analyzeProjectContext(project)
      
      // Create project entities and relationships
      const episode = {
        name: `Project Context: ${project.name}`,
        content: this.buildProjectContextContent(projectInsights),
        source: "project_discovery",
        sourceDescription: `Automatic project context analysis for ${project.name}`,
        timestamp: new Date().toISOString()
      }
      
      await this.graphitiClient.addEpisode(episode)
      
      // Submit project structure as entities
      await this.submitProjectStructure(projectInsights.structure)
      
    } catch (error) {
      console.warn("Project context submission failed:", error)
    }
  }
  
  async submitRealTimeContext(context: RealTimeContext): Promise<void> {
    if (!this.config.realTimeSubmission.enabled) return
    
    try {
      // Analyze context for immediate value
      const contextValue = await this.assessContextValue(context)
      
      if (contextValue.score > this.config.realTimeSubmission.threshold) {
        const submission: ContextSubmission = {
          type: 'real_time',
          context: context,
          timestamp: Date.now(),
          priority: contextValue.priority
        }
        
        this.submissionQueue.push(submission)
        
        // Process high-priority items immediately
        if (contextValue.priority === 'high') {
          await this.processSubmissionQueue()
        }
      }
    } catch (error) {
      console.warn("Real-time context submission failed:", error)
    }
  }
  
  private async enrichContext(context: FilteredContext): Promise<EnrichedContext> {
    const enriched: EnrichedContext = {
      ...context,
      metadata: {
        submissionTime: new Date().toISOString(),
        openCodeVersion: await this.getOpenCodeVersion(),
        projectHash: await this.generateProjectHash(context.project),
        sessionId: context.sessionId,
        userAgent: process.platform
      },
      relationships: await this.detectRelationships(context),
      entities: await this.extractEntities(context),
      insights: await this.generateInsights(context)
    }
    
    return enriched
  }
  
  private async detectRelationships(context: FilteredContext): Promise<ContextRelationship[]> {
    const relationships: ContextRelationship[] = []
    
    // File-to-file relationships
    if (context.files && context.files.length > 1) {
      for (let i = 0; i < context.files.length; i++) {
        for (let j = i + 1; j < context.files.length; j++) {
          const relationship = await this.analyzeFileRelationship(
            context.files[i], 
            context.files[j]
          )
          if (relationship) {
            relationships.push(relationship)
          }
        }
      }
    }
    
    // Tool-to-file relationships
    context.toolExecutions?.forEach(execution => {
      if (execution.filePath) {
        relationships.push({
          type: 'tool_operates_on_file',
          source: execution.tool,
          target: execution.filePath,
          properties: {
            operation: execution.operation,
            timestamp: execution.timestamp,
            success: execution.success
          }
        })
      }
    })
    
    // User-to-project relationships
    relationships.push({
      type: 'user_works_on_project',
      source: 'current_user',
      target: context.project?.name || 'unknown_project',
      properties: {
        sessionDuration: context.sessionDuration,
        activityLevel: context.activityLevel,
        focusAreas: context.focusAreas
      }
    })
    
    return relationships
  }
  
  private async extractEntities(context: FilteredContext): Promise<ContextEntity[]> {
    const entities: ContextEntity[] = []
    
    // Project entity
    if (context.project) {
      entities.push({
        type: 'Project',
        name: context.project.name,
        properties: {
          path: context.project.path,
          language: context.project.primaryLanguage,
          framework: context.project.framework,
          lastActive: new Date().toISOString()
        }
      })
    }
    
    // File entities
    context.files?.forEach(file => {
      entities.push({
        type: 'File',
        name: file.path,
        properties: {
          extension: file.extension,
          size: file.size,
          lastModified: file.lastModified,
          linesOfCode: file.linesOfCode
        }
      })
    })
    
    // Tool entities
    const uniqueTools = [...new Set(context.toolExecutions?.map(e => e.tool) || [])]
    uniqueTools.forEach(tool => {
      entities.push({
        type: 'Tool',
        name: tool,
        properties: {
          usageCount: context.toolExecutions?.filter(e => e.tool === tool).length || 0,
          lastUsed: new Date().toISOString()
        }
      })
    })
    
    return entities
  }
  
  private async generateInsights(context: FilteredContext): Promise<ContextInsight[]> {
    const insights: ContextInsight[] = []
    
    // Analyze tool usage patterns
    if (context.toolExecutions && context.toolExecutions.length > 0) {
      const toolStats = this.analyzeToolUsage(context.toolExecutions)
      
      // High tool usage insight
      if (toolStats.totalExecutions > 20) {
        insights.push({
          type: 'productivity_pattern',
          description: `High activity session with ${toolStats.totalExecutions} tool executions`,
          confidence: 0.9,
          evidence: [`${toolStats.totalExecutions} total executions`, `${toolStats.uniqueTools} unique tools used`]
        })
      }
      
      // Failed executions insight
      if (toolStats.failureRate > 0.2) {
        insights.push({
          type: 'error_pattern',
          description: `High failure rate (${(toolStats.failureRate * 100).toFixed(1)}%) may indicate debugging session`,
          confidence: 0.8,
          evidence: [`${toolStats.failures} failed executions out of ${toolStats.totalExecutions}`]
        })
      }
    }
    
    // Analyze file access patterns
    if (context.files && context.files.length > 0) {
      const fileExtensions = [...new Set(context.files.map(f => f.extension))]
      
      if (fileExtensions.length === 1) {
        insights.push({
          type: 'focus_pattern',
          description: `Focused session on ${fileExtensions[0]} files`,
          confidence: 0.7,
          evidence: [`All ${context.files.length} files have ${fileExtensions[0]} extension`]
        })
      }
    }
    
    // Analyze session duration patterns
    if (context.sessionDuration > 3600000) { // > 1 hour
      insights.push({
        type: 'session_pattern',
        description: 'Extended work session indicates deep focus or complex task',
        confidence: 0.8,
        evidence: [`Session duration: ${Math.round(context.sessionDuration / 60000)} minutes`]
      })
    }
    
    return insights
  }
  
  private async submitToGraphiti(enrichedContext: EnrichedContext): Promise<void> {
    // Submit main episode
    const episode = {
      name: `Session Context: ${enrichedContext.sessionId}`,
      content: this.buildContextContent(enrichedContext),
      source: "session_context",
      sourceDescription: "Automatic OpenCode session context submission",
      timestamp: enrichedContext.metadata.submissionTime
    }
    
    await this.graphitiClient.addEpisode(episode)
    
    // Submit entities and relationships separately for better graph structure
    await this.submitContextEntities(enrichedContext.entities)
    await this.submitContextRelationships(enrichedContext.relationships)
  }
  
  private buildContextContent(context: EnrichedContext): string {
    const content = []
    
    content.push(`# Session Context`)
    content.push(`**Session ID**: ${context.sessionId}`)
    content.push(`**Duration**: ${context.sessionDuration}ms`)
    content.push(`**Project**: ${context.project?.name || 'Unknown'}`)
    content.push(`**Activity Level**: ${context.activityLevel}`)
    
    if (context.files && context.files.length > 0) {
      content.push(`\n## Files Accessed`)
      context.files.forEach(file => {
        content.push(`- ${file.path} (${file.extension}, ${file.size} bytes)`)
      })
    }
    
    if (context.toolExecutions && context.toolExecutions.length > 0) {
      content.push(`\n## Tool Usage`)
      const toolStats = this.summarizeToolUsage(context.toolExecutions)
      Object.entries(toolStats).forEach(([tool, stats]) => {
        content.push(`- ${tool}: ${stats.count} executions, ${stats.successRate}% success rate`)
      })
    }
    
    if (context.insights && context.insights.length > 0) {
      content.push(`\n## Session Insights`)
      context.insights.forEach(insight => {
        content.push(`- ${insight.description} (confidence: ${insight.confidence})`)
      })
    }
    
    content.push(`\n## Metadata`)
    content.push(`- OpenCode Version: ${context.metadata.openCodeVersion}`)
    content.push(`- Platform: ${context.metadata.userAgent}`)
    content.push(`- Project Hash: ${context.metadata.projectHash}`)
    
    return content.join('\n')
  }
  
  private async assessContextValue(context: RealTimeContext): Promise<ContextValue> {
    let score = 0
    let priority: 'low' | 'medium' | 'high' = 'low'
    const reasons: string[] = []
    
    // Assess based on context type
    switch (context.type) {
      case 'file_opened':
        score += 0.3
        reasons.push('File access indicates active work')
        break
      case 'file_edited':
        score += 0.7
        priority = 'medium'
        reasons.push('File edit indicates content creation')
        break
      case 'tool_executed':
        score += 0.5
        reasons.push('Tool execution indicates active development')
        break
      case 'project_changed':
        score += 0.9
        priority = 'high'
        reasons.push('Project change is significant context shift')
        break
    }
    
    // Assess based on data content
    if (context.data) {
      if (context.data.error) {
        score += 0.4
        reasons.push('Error context valuable for debugging patterns')
      }
      if (context.data.duration && context.data.duration > 5000) {
        score += 0.3
        reasons.push('Long operation may indicate complex task')
      }
    }
    
    // Boost priority for high scores
    if (score > 0.8) priority = 'high'
    else if (score > 0.5) priority = 'medium'
    
    return { score, priority, reasons }
  }
  
  private analyzeToolUsage(executions: any[]) {
    const stats = {
      totalExecutions: executions.length,
      uniqueTools: new Set(executions.map(e => e.tool)).size,
      failures: executions.filter(e => !e.success).length,
      failureRate: 0
    }
    
    stats.failureRate = stats.failures / stats.totalExecutions
    
    return stats
  }
  
  private summarizeToolUsage(executions: any[]) {
    const summary: Record<string, any> = {}
    
    executions.forEach(execution => {
      if (!summary[execution.tool]) {
        summary[execution.tool] = { count: 0, successes: 0 }
      }
      summary[execution.tool].count++
      if (execution.success) {
        summary[execution.tool].successes++
      }
    })
    
    Object.keys(summary).forEach(tool => {
      summary[tool].successRate = Math.round(
        (summary[tool].successes / summary[tool].count) * 100
      )
    })
    
    return summary
  }
  
  private startPeriodicSubmission(): void {
    setInterval(async () => {
      if (this.submissionQueue.length > 0 && !this.isProcessing) {
        await this.processSubmissionQueue()
      }
    }, this.config.batchSubmission.intervalMs)
  }
  
  private async processSubmissionQueue(): Promise<void> {
    if (this.isProcessing) return
    
    this.isProcessing = true
    
    try {
      const batch = this.submissionQueue.splice(0, this.config.batchSubmission.batchSize)
      
      // Group by type for efficient processing
      const groupedBatch = this.groupSubmissionsByType(batch)
      
      // Process each group
      await Promise.all([
        this.processBatchedSessions(groupedBatch.sessions || []),
        this.processBatchedRealTime(groupedBatch.realTime || []),
        this.processBatchedProjects(groupedBatch.projects || [])
      ])
      
    } catch (error) {
      console.error("Batch submission processing failed:", error)
    } finally {
      this.isProcessing = false
    }
  }
  
  private groupSubmissionsByType(submissions: ContextSubmission[]) {
    return submissions.reduce((groups, submission) => {
      if (!groups[submission.type]) {
        groups[submission.type] = []
      }
      groups[submission.type].push(submission)
      return groups
    }, {} as Record<string, ContextSubmission[]>)
  }
  
  private async processBatchedSessions(sessions: ContextSubmission[]): Promise<void> {
    for (const session of sessions) {
      await this.submitSessionContext(session.context)
    }
  }
  
  private async processBatchedRealTime(realTime: ContextSubmission[]): Promise<void> {
    // Combine real-time contexts for efficiency
    const combinedContext = this.combineRealTimeContexts(realTime.map(r => r.context))
    await this.submitRealTimeContext(combinedContext)
  }
  
  private async processBatchedProjects(projects: ContextSubmission[]): Promise<void> {
    for (const project of projects) {
      await this.submitProjectContext(project.context)
    }
  }
  
  // Helper methods
  private async getOpenCodeVersion(): Promise<string> {
    // Implementation to get OpenCode version
    return "1.0.0" // placeholder
  }
  
  private async generateProjectHash(project: any): Promise<string> {
    // Generate a hash of project structure for identification
    return `proj_${Date.now()}` // placeholder
  }
  
  private async analyzeFileRelationship(file1: any, file2: any): Promise<ContextRelationship | null> {
    // Analyze if two files are related
    // Return null for now, implement based on file analysis
    return null
  }
  
  private async analyzeProjectContext(project: ProjectContext): Promise<ProjectContext> {
    // Additional project analysis
    return project
  }
  
  private buildProjectContextContent(project: ProjectContext): string {
    return `Project analysis for ${project.name}`
  }
  
  private async submitProjectStructure(structure: any): Promise<void> {
    // Submit project structure as entities
  }
  
  private async submitContextEntities(entities: ContextEntity[]): Promise<void> {
    // Submit entities to Graphiti
  }
  
  private async submitContextRelationships(relationships: ContextRelationship[]): Promise<void> {
    // Submit relationships to Graphiti
  }
  
  private queueForRetry(context: SessionContext): void {
    // Queue failed submissions for retry
  }
  
  private combineRealTimeContexts(contexts: RealTimeContext[]): RealTimeContext {
    // Combine multiple real-time contexts
    return contexts[0] // placeholder
  }
}

// Context submission handler functions
export async function handleContextSubmission(
  context: ContextChange,
  engine: ContextSubmissionEngine
): Promise<void> {
  await engine.submitRealTimeContext({
    type: context.type,
    data: context.data,
    timestamp: Date.now(),
    source: 'context_change_hook'
  })
}

export async function handleProjectContextSubmission(
  project: any,
  engine: ContextSubmissionEngine
): Promise<void> {
  const projectContext = await analyzeProjectContext(project)
  await engine.submitProjectContext(projectContext)
}

async function analyzeProjectContext(project: any): Promise<ProjectContext> {
  return {
    name: project.name,
    path: project.path,
    structure: await analyzeProjectStructure(project.path),
    dependencies: await analyzeDependencies(project.path),
    configuration: await analyzeConfiguration(project.path),
    recentActivity: await analyzeRecentActivity(project.path)
  }
}

async function analyzeProjectStructure(path: string) {
  // Analyze project structure
  return {
    directories: [],
    fileTypes: {},
    totalFiles: 0,
    totalLines: 0
  }
}

async function analyzeDependencies(path: string) {
  // Analyze project dependencies
  return []
}

async function analyzeConfiguration(path: string) {
  // Analyze project configuration
  return {
    packageManager: 'npm',
    buildTool: undefined,
    testFramework: undefined,
    linter: undefined,
    formatter: undefined
  }
}

async function analyzeRecentActivity(path: string) {
  // Analyze recent project activity
  return {
    recentFiles: [],
    recentCommits: [],
    activeHours: []
  }
}