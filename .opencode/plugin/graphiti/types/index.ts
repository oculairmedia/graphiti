// Core type definitions for Graphiti OpenCode integration

export interface GraphitiPluginConfig {
  // Connection settings
  endpoint: string
  groupId: string
  apiKey?: string
  
  // Behavior settings
  preResponseSearch: {
    enabled: boolean
    relevanceThreshold: number
    maxResults: number
    entityTypes: string[]
  }
  
  interCallSearch: {
    enabled: boolean
    toolWhitelist: string[]
    confidenceThreshold: number
  }
  
  knowledgePersistence: {
    enabled: boolean
    autoSaveInsights: boolean
    episodeRetention: number // days
  }
  
  contextSubmission: {
    enabled: boolean
    realTimeSubmission: {
      enabled: boolean
      threshold: number
      maxQueueSize: number
    }
    batchSubmission: {
      enabled: boolean
      intervalMs: number
      batchSize: number
    }
    privacy: {
      enableFiltering: boolean
      maxFileSize: number
      allowedExtensions: string[]
      blockedDirectories: string[]
      strictMode?: boolean
      auditLogging?: boolean
      dataClassification?: boolean
    }
  }
  
  // Project-specific overrides
  projectOverrides: Record<string, Partial<GraphitiPluginConfig>>
}

export interface SessionContext {
  sessionId: string
  sessionDuration: number
  activityLevel: 'low' | 'medium' | 'high'
  project?: ProjectInfo
  files?: FileInfo[]
  toolExecutions?: ToolExecution[]
  focusAreas: string[]
}

export interface ProjectInfo {
  name: string
  path: string
  primaryLanguage?: string
  framework?: string
}

export interface FileInfo {
  path: string
  extension: string
  size: number
  lastModified: string
  linesOfCode?: number
}

export interface ToolExecution {
  tool: string
  operation: string
  filePath?: string
  timestamp: string
  success: boolean
  duration?: number
}

export interface FilteredContext {
  sessionId: string
  sessionDuration: number
  activityLevel: 'low' | 'medium' | 'high'
  project?: ProjectInfo
  files: FileInfo[]
  toolExecutions: ToolExecution[]
  focusAreas: string[]
}

export interface EnrichedContext extends FilteredContext {
  metadata: {
    submissionTime: string
    openCodeVersion: string
    projectHash: string
    sessionId: string
    userAgent: string
  }
  relationships: ContextRelationship[]
  entities: ContextEntity[]
  insights: ContextInsight[]
}

export interface ContextRelationship {
  type: string
  source: string
  target: string
  properties: Record<string, any>
}

export interface ContextEntity {
  type: string
  name: string
  properties: Record<string, any>
}

export interface ContextInsight {
  type: string
  description: string
  confidence: number
  evidence: string[]
}

export interface ContextSubmission {
  type: 'session' | 'real_time' | 'project'
  context: any
  timestamp: number
  priority: 'low' | 'medium' | 'high'
}

export interface ProjectContext {
  name: string
  path: string
  structure: ProjectStructure
  dependencies: DependencyInfo[]
  configuration: ConfigurationInfo
  recentActivity: ActivityInfo
}

export interface ProjectStructure {
  directories: string[]
  fileTypes: Record<string, number>
  totalFiles: number
  totalLines: number
}

export interface DependencyInfo {
  name: string
  version: string
  type: 'dependency' | 'devDependency' | 'peerDependency'
}

export interface ConfigurationInfo {
  packageManager: string
  buildTool?: string
  testFramework?: string
  linter?: string
  formatter?: string
}

export interface ActivityInfo {
  recentFiles: string[]
  recentCommits: string[]
  activeHours: number[]
}

export interface RealTimeContext {
  type: string
  data: any
  timestamp: number
  source: string
}

export interface ContextChange {
  type: 'file_opened' | 'file_edited' | 'tool_executed' | 'project_changed'
  data: any
  timestamp: number
}

export interface PrivacyConfig {
  enableFiltering: boolean
  maxFileSize: number
  allowedExtensions: Set<string>
  blockedDirectories: Set<string>
  sensitivePatterns: RegExp[]
  strictMode: boolean
  auditLogging: boolean
}

export interface ContextSubmissionConfig {
  realTimeSubmission: {
    enabled: boolean
    threshold: number
    maxQueueSize: number
  }
  batchSubmission: {
    enabled: boolean
    intervalMs: number
    batchSize: number
  }
}

export interface ContextValue {
  score: number
  priority: 'low' | 'medium' | 'high'
  reasons: string[]
}

// Graphiti client types
export interface GraphitiClient {
  searchNodes(query: any): Promise<any>
  searchFacts(query: any): Promise<any>
  addEpisode(episode: any): Promise<any>
  getRecentEpisodes(query: any): Promise<any>
}

// Knowledge types
export interface KnowledgeContext {
  relevanceScore: number
  preferences: Array<{description: string}>
  procedures: Array<{description: string}>
  requirements: Array<{description: string}>
  facts: Array<{description: string}>
}

export interface ExtractedInsights {
  preferences: Array<{
    category: string
    description: string
    confidence: number
  }>
  procedures: Array<{
    description: string
    steps: string[]
    whenToUse: string
  }>
  requirements: Array<{
    projectName: string
    description: string
    priority: string
  }>
  patterns: Array<{
    type: string
    description: string
    frequency: number
  }>
}

export interface ToolContextAnalysis {
  operation: string
  filePath?: string
  fileType?: string
  confidenceScore: number
  relevantConcepts: string[]
  suggestedKnowledge: string[]
}

export interface ContextualKnowledge {
  isRelevant: boolean
  knowledge: any[]
  confidence: number
}