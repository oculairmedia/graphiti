// Graphiti API client for communicating with the Python server
import type { NodeResult } from './types';

export interface GraphitiNodeSearchQuery {
  query: string;
  max_nodes?: number;
  group_ids?: string[];
  center_node_uuid?: string;
  entity?: string;
}

export interface GraphitiNodeSearchResults {
  nodes: NodeResult[];
}

export interface GraphitiEdgeResult {
  uuid: string;
  name: string;
  fact: string;
  valid_at: string | null;
  invalid_at: string | null;
  created_at: string;
  expired_at: string | null;
}

export interface GraphitiEdgesByNodeResponse {
  edges: GraphitiEdgeResult[];
  source_edges: GraphitiEdgeResult[];
  target_edges: GraphitiEdgeResult[];
}

export class GraphitiClient {
  private baseUrl = '/graphiti';
  private readonly DEFAULT_TIMEOUT = 30000; // 30 seconds

  private async fetchWithError<T>(url: string, options?: RequestInit): Promise<T> {
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
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText || response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof Error) {
        throw new Error(`Graphiti API request failed: ${error.message}`);
      }
      throw new Error('Graphiti API request failed: Unknown error');
    }
  }

  async searchNodes(query: GraphitiNodeSearchQuery): Promise<GraphitiNodeSearchResults> {
    return this.fetchWithError<GraphitiNodeSearchResults>(`${this.baseUrl}/search/nodes`, {
      method: 'POST',
      body: JSON.stringify(query),
    });
  }

  async getEdgesByNode(nodeUuid: string): Promise<GraphitiEdgesByNodeResponse> {
    return this.fetchWithError<GraphitiEdgesByNodeResponse>(
      `${this.baseUrl}/edges/by-node/${nodeUuid}`
    );
  }

  async updateNodeSummary(nodeUuid: string, summary: string): Promise<NodeResult> {
    return this.fetchWithError<NodeResult>(
      `${this.baseUrl}/nodes/${nodeUuid}/summary`,
      {
        method: 'PATCH',
        body: JSON.stringify({ summary }),
      }
    );
  }
}

// Export singleton instance
export const graphitiClient = new GraphitiClient();