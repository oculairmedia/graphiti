import {
  GraphData,
  GraphStats,
  QueryResponse,
  QueryParams,
  SearchRequest,
  SearchResponse,
  NodeDetails,
  ErrorResponse,
  CentralityMetrics,
  CentralityStats,
  BulkCentralityResponse,
  QueueStatus,
} from './types';

export class GraphClient {
  private baseUrl = '/api';
  private readonly DEFAULT_TIMEOUT = 30000; // 30 seconds
  private readonly CENTRALITY_TIMEOUT = 120000; // 120 seconds for centrality operations
  private readonly MAX_RETRIES = 3;
  private readonly RETRY_DELAY = 1000; // 1 second

  private async fetchWithError<T>(url: string, options?: RequestInit, timeout?: number): Promise<T> {
    return this.fetchWithRetry<T>(url, options, 0, timeout);
  }

  private async fetchWithRetry<T>(url: string, options?: RequestInit, attempt: number = 0, timeout?: number): Promise<T> {
    try {
      const controller = new AbortController();
      const timeoutMs = timeout || this.DEFAULT_TIMEOUT;
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

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
        return this.fetchWithRetry<T>(url, options, attempt + 1, timeout);
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

  async getQueueStatus(): Promise<QueueStatus> {
    return this.fetchWithError<QueueStatus>(`${this.baseUrl}/queue/status`);
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

  // Centrality endpoints
  async getNodeCentrality(nodeId: string): Promise<CentralityMetrics> {
    // For now, calculate centrality for a single node by calling the all endpoint
    const response = await this.fetchWithError<any>(`${this.baseUrl}/centrality/all`, {
      method: 'POST',
      body: JSON.stringify({ 
        store_results: false 
      }),
    }, this.CENTRALITY_TIMEOUT);
    
    // Extract metrics for the specific node
    const metrics = response.scores?.[nodeId];
    if (!metrics) {
      throw new Error(`No centrality data found for node ${nodeId}`);
    }
    
    return {
      degree: metrics.degree || 0,
      betweenness: metrics.betweenness || 0,
      pagerank: metrics.pagerank || 0,
      eigenvector: metrics.eigenvector || 0,
    };
  }

  async getBulkCentrality(nodeIds: string[]): Promise<BulkCentralityResponse> {
    // Calculate centrality for all nodes and filter results
    const response = await this.fetchWithError<any>(`${this.baseUrl}/centrality/all`, {
      method: 'POST',
      body: JSON.stringify({ 
        store_results: false 
      }),
    }, this.CENTRALITY_TIMEOUT);
    
    // Filter results to only requested nodes
    const result: BulkCentralityResponse = {};
    for (const nodeId of nodeIds) {
      if (response.scores?.[nodeId]) {
        result[nodeId] = {
          degree: response.scores[nodeId].degree || 0,
          betweenness: response.scores[nodeId].betweenness || 0,
          pagerank: response.scores[nodeId].pagerank || 0,
          eigenvector: response.scores[nodeId].eigenvector || 0,
        };
      }
    }
    
    return result;
  }

  async getCentralityStats(): Promise<CentralityStats> {
    return this.fetchWithError<CentralityStats>(`${this.baseUrl}/centrality/stats`);
  }
  
  // Additional centrality calculation methods
  async calculatePageRank(options: {
    damping_factor?: number;
    iterations?: number;
    store_results?: boolean;
  } = {}): Promise<any> {
    return this.fetchWithError<any>(`${this.baseUrl}/centrality/pagerank`, {
      method: 'POST',
      body: JSON.stringify({
        damping_factor: options.damping_factor || 0.85,
        iterations: options.iterations || 20,
        store_results: options.store_results || false,
      }),
    }, this.CENTRALITY_TIMEOUT);
  }
  
  async calculateDegreeCentrality(options: {
    direction?: 'in' | 'out' | 'both';
    store_results?: boolean;
  } = {}): Promise<any> {
    return this.fetchWithError<any>(`${this.baseUrl}/centrality/degree`, {
      method: 'POST',
      body: JSON.stringify({
        direction: options.direction || 'both',
        store_results: options.store_results || false,
      }),
    }, this.CENTRALITY_TIMEOUT);
  }
  
  async calculateBetweennessCentrality(options: {
    sample_size?: number;
    store_results?: boolean;
  } = {}): Promise<any> {
    return this.fetchWithError<any>(`${this.baseUrl}/centrality/betweenness`, {
      method: 'POST',
      body: JSON.stringify({
        sample_size: options.sample_size,
        store_results: options.store_results || false,
      }),
    }, this.CENTRALITY_TIMEOUT);
  }
  
  async calculateAllCentralities(options: {
    store_results?: boolean;
  } = {}): Promise<any> {
    return this.fetchWithError<any>(`${this.baseUrl}/centrality/all`, {
      method: 'POST',
      body: JSON.stringify({
        store_results: options.store_results || false,
      }),
    }, this.CENTRALITY_TIMEOUT);
  }

  async updateNodeSummary(nodeId: string, summary: string): Promise<{ uuid: string; name: string; summary: string }> {
    return this.fetchWithError<{ uuid: string; name: string; summary: string }>(
      `${this.baseUrl}/nodes/${nodeId}/summary`,
      {
        method: 'PATCH',
        body: JSON.stringify({ summary }),
      }
    );
  }
}

// Export singleton instance
export const graphClient = new GraphClient();