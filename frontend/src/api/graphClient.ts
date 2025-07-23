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

  private async fetchWithError<T>(url: string, options?: RequestInit): Promise<T> {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error: ErrorResponse = await response.json().catch(() => ({
        error: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(error.error || 'API request failed');
    }

    return response.json();
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