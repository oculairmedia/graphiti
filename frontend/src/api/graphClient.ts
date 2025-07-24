import {
  GraphData,
  GraphStats,
  QueryResponse,
  QueryParams,
  SearchRequest,
  SearchResponse,
  NodeDetails,
  ErrorResponse,
} from './types';

export class GraphClient {
  private baseUrl = '/api';
  private readonly DEFAULT_TIMEOUT = 30000; // 30 seconds
  private readonly MAX_RETRIES = 3;
  private readonly RETRY_DELAY = 1000; // 1 second

  private async fetchWithError<T>(url: string, options?: RequestInit): Promise<T> {
    return this.fetchWithRetry<T>(url, options, 0);
  }

  private async fetchWithRetry<T>(url: string, options?: RequestInit, attempt: number = 0): Promise<T> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), this.DEFAULT_TIMEOUT);

      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const error: ErrorResponse = await this.safeJsonParse(response);
        throw new Error(error.error || `HTTP ${response.status}: ${response.statusText}`);
      }

      return await this.safeJsonParse<T>(response);
    } catch (error) {
      // Retry on network errors or timeouts
      if (attempt < this.MAX_RETRIES && this.isRetryableError(error)) {
        await this.delay(this.RETRY_DELAY * Math.pow(2, attempt)); // Exponential backoff
        return this.fetchWithRetry<T>(url, options, attempt + 1);
      }
      
      // Re-throw with enhanced error information
      throw new Error(this.formatError(error, url, attempt));
    }
  }

  private async safeJsonParse<T>(response: Response): Promise<T> {
    try {
      return await response.json();
    } catch (error) {
      throw new Error(`Failed to parse JSON response: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  private isRetryableError(error: unknown): boolean {
    if (error instanceof Error) {
      return error.name === 'AbortError' || 
             error.message.includes('fetch') ||
             error.message.includes('network') ||
             error.message.includes('timeout');
    }
    return false;
  }

  private formatError(error: unknown, url: string, attempts: number): string {
    const baseMessage = error instanceof Error ? error.message : 'Unknown error';
    return `API request failed after ${attempts + 1} attempts to ${url}: ${baseMessage}`;
  }

  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async getGraphData(params: QueryParams = {}): Promise<GraphData> {
    const queryParams = new URLSearchParams();
    
    if (params.query_type) queryParams.append('query_type', params.query_type);
    if (params.limit) queryParams.append('limit', params.limit.toString());
    if (params.offset) queryParams.append('offset', params.offset.toString());
    if (params.search) queryParams.append('search', params.search);

    const response = await this.fetchWithError<QueryResponse>(
      `${this.baseUrl}/visualize?${queryParams}`
    );

    return response.data;
  }

  async getStats(): Promise<GraphStats> {
    return this.fetchWithError<GraphStats>(`${this.baseUrl}/stats`);
  }

  async searchNodes(request: SearchRequest): Promise<SearchResponse> {
    return this.fetchWithError<SearchResponse>(`${this.baseUrl}/search`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getNodeDetails(nodeId: string): Promise<NodeDetails> {
    return this.fetchWithError<NodeDetails>(`${this.baseUrl}/nodes/${nodeId}`);
  }

  async getNodeConnections(nodeId: string): Promise<{ edges: GraphData['edges'] }> {
    return this.fetchWithError<{ edges: GraphData['edges'] }>(
      `${this.baseUrl}/edges/by-node/${nodeId}`
    );
  }
}

// Export singleton instance
export const graphClient = new GraphClient();