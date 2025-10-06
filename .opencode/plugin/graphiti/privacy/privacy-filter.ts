import type { 
  SessionContext, 
  FilteredContext, 
  ProjectInfo, 
  FileInfo, 
  ToolExecution, 
  PrivacyConfig 
} from '../types'

export class PrivacyFilter {
  private sensitivePatterns: RegExp[]
  private allowedFileExtensions: Set<string>
  private blockedDirectories: Set<string>
  
  constructor(private config: PrivacyConfig) {
    this.sensitivePatterns = [
      /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g, // emails
      /\b(?:\d{4}[-\s]?){3}\d{4}\b/g, // credit cards
      /\b\d{3}-?\d{2}-?\d{4}\b/g, // SSN
      /\b[A-Z0-9]{20,}\b/g, // potential API keys
      /password["\s]*[:=]["\s]*[^\s"]+/gi, // passwords
      /token["\s]*[:=]["\s]*[^\s"]+/gi, // tokens
      /key["\s]*[:=]["\s]*[^\s"]+/gi, // keys
      /sk-[a-zA-Z0-9]{48}/g, // OpenAI API keys
      /[A-Za-z0-9+/]{32,}={0,2}/g, // potential base64 encoded secrets
    ]
    
    this.allowedFileExtensions = new Set([
      '.js', '.ts', '.jsx', '.tsx', '.py', '.java', '.cpp', '.c', '.h',
      '.css', '.scss', '.html', '.md', '.json', '.yaml', '.yml',
      '.toml', '.cfg', '.ini', '.txt', '.go', '.rs', '.rb', '.php',
      '.sh', '.bat', '.ps1', '.sql', '.xml', '.csv'
    ])
    
    this.blockedDirectories = new Set([
      'node_modules', '.git', '.env', 'dist', 'build', 'coverage',
      '.nyc_output', 'logs', 'tmp', 'temp', '.vscode', '.idea',
      'vendor', '__pycache__', '.pytest_cache', '.cache'
    ])
  }
  
  async filterContext(context: SessionContext): Promise<FilteredContext> {
    const filtered: FilteredContext = {
      sessionId: context.sessionId,
      sessionDuration: context.sessionDuration,
      activityLevel: context.activityLevel,
      project: await this.filterProject(context.project),
      files: await this.filterFiles(context.files || []),
      toolExecutions: await this.filterToolExecutions(context.toolExecutions || []),
      focusAreas: context.focusAreas.map(area => this.sanitizeContent(area))
    }
    
    return filtered
  }
  
  private async filterProject(project?: ProjectInfo): Promise<ProjectInfo | undefined> {
    if (!project) return undefined
    
    return {
      name: this.sanitizeProjectName(project.name),
      path: this.sanitizePath(project.path),
      primaryLanguage: project.primaryLanguage,
      framework: project.framework
      // Remove sensitive project details like absolute paths, user info
    }
  }
  
  private async filterFiles(files: FileInfo[]): Promise<FileInfo[]> {
    return files
      .filter(file => this.isAllowedFile(file))
      .map(file => ({
        path: this.sanitizePath(file.path),
        extension: file.extension,
        size: this.config.strictMode ? this.roundFileSize(file.size) : file.size,
        lastModified: file.lastModified,
        linesOfCode: file.linesOfCode
        // Remove absolute paths, replace with relative paths
      }))
      .slice(0, 100) // Limit number of files for privacy
  }
  
  private async filterToolExecutions(executions: ToolExecution[]): Promise<ToolExecution[]> {
    return executions
      .map(execution => ({
        tool: execution.tool,
        operation: this.sanitizeOperation(execution.operation),
        filePath: execution.filePath ? this.sanitizePath(execution.filePath) : undefined,
        timestamp: execution.timestamp,
        success: execution.success,
        duration: execution.duration
        // Remove command arguments that might contain sensitive data
      }))
      .slice(0, 200) // Limit number of executions for privacy
  }
  
  private isAllowedFile(file: FileInfo): boolean {
    // Check file extension
    if (!this.allowedFileExtensions.has(file.extension)) {
      return false
    }
    
    // Check if file is in blocked directory
    const pathParts = file.path.split('/')
    for (const part of pathParts) {
      if (this.blockedDirectories.has(part)) {
        return false
      }
    }
    
    // Check for sensitive file names
    const fileName = pathParts[pathParts.length - 1].toLowerCase()
    const sensitiveFileNames = [
      '.env', '.secret', 'password', 'config.json', 'credentials',
      'private', 'secret', 'auth', 'token', 'key'
    ]
    
    if (sensitiveFileNames.some(sensitive => fileName.includes(sensitive))) {
      return false
    }
    
    // Check file size (avoid huge files)
    if (file.size > this.config.maxFileSize) {
      return false
    }
    
    return true
  }
  
  private sanitizePath(path: string): string {
    // Convert absolute paths to relative paths
    // Remove username and other identifying information
    let sanitized = path
      .replace(/\/Users\/[^\/]+/, '/Users/[user]')
      .replace(/\/home\/[^\/]+/, '/home/[user]')
      .replace(/C:\\Users\\[^\\]+/, 'C:\\Users\\[user]')
      .replace(/\/opt\/stacks\/[^\/]+/, '/opt/stacks/[project]')
    
    // Remove any remaining potential usernames or identifying info
    sanitized = sanitized.replace(/\/[a-zA-Z0-9_-]{8,32}\//, '/[user]/')
    
    // If in strict mode, further anonymize
    if (this.config.strictMode) {
      sanitized = this.furtherAnonymizePath(sanitized)
    }
    
    return sanitized
  }
  
  private sanitizeContent(content: string): string {
    let sanitized = content
    
    // Remove sensitive patterns
    this.sensitivePatterns.forEach(pattern => {
      sanitized = sanitized.replace(pattern, '[REDACTED]')
    })
    
    // In strict mode, apply additional sanitization
    if (this.config.strictMode) {
      // Remove IP addresses
      sanitized = sanitized.replace(/\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b/g, '[IP_ADDRESS]')
      
      // Remove URLs with potential sensitive info
      sanitized = sanitized.replace(/https?:\/\/[^\s]+/g, '[URL]')
      
      // Remove UUIDs
      sanitized = sanitized.replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '[UUID]')
    }
    
    return sanitized
  }
  
  private sanitizeProjectName(name: string): string {
    // Remove potentially identifying information from project names
    let sanitized = name
    
    // Remove common personal identifiers
    sanitized = sanitized.replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/, '[email]')
    
    // In strict mode, further anonymize
    if (this.config.strictMode) {
      // Replace with generic project names if contains personal info
      const personalPatterns = [
        /personal/i, /private/i, /secret/i, /confidential/i,
        /internal/i, /proprietary/i
      ]
      
      if (personalPatterns.some(pattern => pattern.test(sanitized))) {
        sanitized = `project_${this.hashString(sanitized).substring(0, 8)}`
      }
    }
    
    return sanitized
  }
  
  private sanitizeOperation(operation: string): string {
    // Remove sensitive information from operation descriptions
    let sanitized = operation
    
    // Remove file contents that might be included in operation descriptions
    sanitized = this.sanitizeContent(sanitized)
    
    // Remove long strings that might contain sensitive data
    sanitized = sanitized.replace(/\b[A-Za-z0-9+/]{50,}={0,2}\b/g, '[LONG_STRING]')
    
    return sanitized
  }
  
  private roundFileSize(size: number): number {
    // Round file sizes to nearest KB for privacy
    return Math.round(size / 1024) * 1024
  }
  
  private furtherAnonymizePath(path: string): string {
    // Replace specific path segments with generic ones
    return path
      .replace(/\/[a-zA-Z0-9_-]+\.git/, '/[repo].git')
      .replace(/\/[a-zA-Z0-9_-]+\.js/, '/[file].js')
      .replace(/\/[a-zA-Z0-9_-]+\.ts/, '/[file].ts')
      .replace(/\/[a-zA-Z0-9_-]+\.py/, '/[file].py')
  }
  
  private hashString(str: string): string {
    // Simple hash function for anonymization
    let hash = 0
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i)
      hash = ((hash << 5) - hash) + char
      hash = hash & hash // Convert to 32-bit integer
    }
    return Math.abs(hash).toString(16)
  }
  
  // Content analysis and filtering
  async filterFileContent(content: string, filePath: string): Promise<string | null> {
    // Don't process if file type not allowed
    const extension = '.' + filePath.split('.').pop()
    if (!this.allowedFileExtensions.has(extension)) {
      return null
    }
    
    // Check for sensitive content patterns
    if (this.containsSensitiveData(content)) {
      if (this.config.strictMode) {
        return null // Don't include at all
      } else {
        return this.sanitizeContent(content)
      }
    }
    
    // Truncate very long content
    if (content.length > 10000) {
      content = content.substring(0, 10000) + '\n[TRUNCATED]'
    }
    
    return this.sanitizeContent(content)
  }
  
  private containsSensitiveData(content: string): boolean {
    // Check for high concentration of sensitive patterns
    let sensitiveMatches = 0
    
    this.sensitivePatterns.forEach(pattern => {
      const matches = content.match(pattern)
      if (matches) {
        sensitiveMatches += matches.length
      }
    })
    
    // If more than 3 sensitive patterns found, consider content sensitive
    return sensitiveMatches > 3
  }
  
  // Audit logging for compliance
  logDataAccess(action: string, dataType: string, context: any): void {
    if (this.config.auditLogging) {
      const logEntry = {
        timestamp: new Date().toISOString(),
        action,
        dataType,
        sessionId: context.sessionId || 'unknown',
        sanitized: true,
        filterApplied: this.config.enableFiltering
      }
      
      // In a real implementation, this would go to a secure audit log
      console.log('[AUDIT]', JSON.stringify(logEntry))
    }
  }
  
  // Data classification for enterprise compliance
  classifyData(data: any): DataClassification {
    let classification: DataClassification = 'public'
    
    const dataString = JSON.stringify(data).toLowerCase()
    
    // Check for personal information
    if (this.sensitivePatterns.some(pattern => pattern.test(dataString))) {
      classification = 'restricted'
    }
    
    // Check for internal keywords
    const internalKeywords = ['internal', 'confidential', 'proprietary', 'private']
    if (internalKeywords.some(keyword => dataString.includes(keyword))) {
      if (classification === 'public') {
        classification = 'internal'
      }
    }
    
    return classification
  }
}

type DataClassification = 'public' | 'internal' | 'confidential' | 'restricted'

// Factory function for creating privacy filter with environment-based config
export function createPrivacyFilter(): PrivacyFilter {
  const config: PrivacyConfig = {
    enableFiltering: process.env.GRAPHITI_PRIVACY_FILTERING !== 'false',
    maxFileSize: parseInt(process.env.GRAPHITI_MAX_FILE_SIZE || '1048576'), // 1MB default
    allowedExtensions: new Set([
      '.js', '.ts', '.jsx', '.tsx', '.py', '.java', '.cpp', '.c', '.h',
      '.css', '.scss', '.html', '.md', '.json', '.yaml', '.yml',
      '.toml', '.cfg', '.ini', '.txt', '.go', '.rs', '.rb', '.php'
    ]),
    blockedDirectories: new Set([
      'node_modules', '.git', '.env', 'dist', 'build', 'coverage',
      '.nyc_output', 'logs', 'tmp', 'temp'
    ]),
    sensitivePatterns: [], // Will be set by constructor
    strictMode: process.env.GRAPHITI_STRICT_MODE === 'true',
    auditLogging: process.env.GRAPHITI_AUDIT_LOGGING === 'true'
  }
  
  return new PrivacyFilter(config)
}