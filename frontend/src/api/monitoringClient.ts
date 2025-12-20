/**
 * Monitoring API Client
 *
 * Fetches health and metrics data from Graphiti stack services:
 * - Sync Service (port 18080): Database sync status and performance
 * - Graph Visualizer (port 3000): Graph statistics
 */

export interface SyncHealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  databases: {
    falkordb: {
      name: string;
      connected: boolean;
      response_time_ms: number;
    };
    neo4j: {
      name: string;
      connected: boolean;
      response_time_ms: number;
    };
  };
  sync: {
    state: string;
    last_sync: string;
    items_synced: number;
    success_rate: number;
    last_direction: string;
    nodes_synced: number;
    edges_synced: number;
  };
}

export interface GraphVisualizerStats {
  total_nodes: number;
  total_edges: number;
  node_types: {
    [key: string]: number;
  };
  avg_degree: number;
  max_degree: number;
}

export interface MonitoringData {
  syncHealth: SyncHealthResponse | null;
  visualizerStats: GraphVisualizerStats | null;
  lastUpdated: number;
  errors: {
    sync?: string;
    visualizer?: string;
  };
}

export class MonitoringClient {
  private syncBaseUrl: string;
  private visualizerBaseUrl: string;
  private readonly DEFAULT_TIMEOUT = 10000; // 10 seconds

  constructor() {
    // Use environment variables or default to localhost
    this.syncBaseUrl = import.meta.env.VITE_SYNC_URL || 'http://localhost:18080';
    this.visualizerBaseUrl = import.meta.env.VITE_VISUALIZER_URL || 'http://localhost:3000';
  }

  /**
   * Fetch with timeout and error handling
   */
  private async fetchWithTimeout<T>(url: string, timeout = this.DEFAULT_TIMEOUT): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(url, {
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  /**
   * Get sync service health and status
   */
  async getSyncHealth(): Promise<SyncHealthResponse> {
    return this.fetchWithTimeout<SyncHealthResponse>(`${this.syncBaseUrl}/health`);
  }

  /**
   * Get graph visualizer statistics
   */
  async getVisualizerStats(): Promise<GraphVisualizerStats> {
    return this.fetchWithTimeout<GraphVisualizerStats>(`${this.visualizerBaseUrl}/api/stats`);
  }

  /**
   * Get all monitoring data in parallel
   */
  async getAllMetrics(): Promise<MonitoringData> {
    const errors: MonitoringData['errors'] = {};

    // Fetch all metrics in parallel with individual error handling
    const [syncHealth, visualizerStats] = await Promise.all([
      this.getSyncHealth().catch(error => {
        errors.sync = error instanceof Error ? error.message : 'Unknown error';
        return null;
      }),
      this.getVisualizerStats().catch(error => {
        errors.visualizer = error instanceof Error ? error.message : 'Unknown error';
        return null;
      }),
    ]);

    return {
      syncHealth,
      visualizerStats,
      lastUpdated: Date.now(),
      errors,
    };
  }

  /**
   * Format uptime seconds into human-readable string
   */
  static formatUptime(seconds: number): string {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    const parts: string[] = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0) parts.push(`${minutes}m`);

    return parts.length > 0 ? parts.join(' ') : '<1m';
  }

  /**
   * Format timestamp to relative time
   */
  static formatRelativeTime(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);

    if (diffSecs < 60) return `${diffSecs}s ago`;
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  }
}

// Export singleton instance
export const monitoringClient = new MonitoringClient();
