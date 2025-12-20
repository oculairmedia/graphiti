import React, { useState, useEffect } from 'react';
import { X, Activity, Database, Network, Clock, CheckCircle2, XCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { monitoringClient, type MonitoringData, type SyncHealthResponse, type GraphVisualizerStats } from '@/api/monitoringClient';

interface MonitoringDashboardProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MonitoringDashboard: React.FC<MonitoringDashboardProps> = ({ isOpen, onClose }) => {
  const [data, setData] = useState<MonitoringData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch monitoring data
  const fetchData = async (silent = false) => {
    if (!silent) setIsRefreshing(true);
    try {
      const metrics = await monitoringClient.getAllMetrics();
      setData(metrics);
      setIsLoading(false);
    } catch (error) {
      console.error('[MonitoringDashboard] Failed to fetch metrics:', error);
      setIsLoading(false);
    } finally {
      if (!silent) setIsRefreshing(false);
    }
  };

  // Initial load
  useEffect(() => {
    if (isOpen) {
      fetchData();
    }
  }, [isOpen]);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    if (!isOpen || !autoRefresh) return;

    const interval = setInterval(() => {
      fetchData(true); // Silent refresh
    }, 5000);

    return () => clearInterval(interval);
  }, [isOpen, autoRefresh]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm">
      <div className="fixed right-0 top-0 h-full w-full max-w-2xl bg-background shadow-2xl overflow-y-auto">
        <div className="sticky top-0 z-10 bg-background border-b px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Activity className="h-5 w-5 text-primary" />
            <h2 className="text-xl font-semibold">System Monitoring</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => fetchData()}
              disabled={isRefreshing}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button
              variant={autoRefresh ? "default" : "outline"}
              size="sm"
              onClick={() => setAutoRefresh(!autoRefresh)}
            >
              {autoRefresh ? 'Auto' : 'Manual'}
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : data ? (
            <>
              {/* Sync Service Status */}
              <SyncServiceCard syncHealth={data.syncHealth} error={data.errors.sync} />

              {/* Graph Visualizer Stats */}
              <GraphVisualizerCard stats={data.visualizerStats} error={data.errors.visualizer} />

              {/* Last Updated */}
              <div className="text-sm text-muted-foreground text-center">
                Last updated: {new Date(data.lastUpdated).toLocaleTimeString()}
              </div>
            </>
          ) : (
            <div className="text-center text-muted-foreground">
              Failed to load monitoring data
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Sync Service Card
const SyncServiceCard: React.FC<{ syncHealth: SyncHealthResponse | null; error?: string }> = ({ syncHealth, error }) => {
  if (error) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <XCircle className="h-5 w-5 text-destructive" />
            Sync Service - Offline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!syncHealth) return null;

  const { status, version, uptime_seconds, databases, sync } = syncHealth;
  const isHealthy = status === 'healthy';
  const successPercent = Math.round(sync.success_rate * 100);

  return (
    <Card className={isHealthy ? 'border-green-500' : 'border-yellow-500'}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-primary" />
            Sync Service
          </div>
          <Badge variant={isHealthy ? 'default' : 'secondary'} className="bg-green-500">
            {status.toUpperCase()}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Version and Uptime */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-sm text-muted-foreground">Version</div>
            <div className="text-lg font-semibold">{version}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Uptime</div>
            <div className="text-lg font-semibold">
              {monitoringClient.constructor['formatUptime'](uptime_seconds)}
            </div>
          </div>
        </div>

        {/* Database Connections */}
        <div className="space-y-2">
          <div className="text-sm font-medium">Database Connections</div>
          <div className="grid grid-cols-2 gap-2">
            <DatabaseStatus name="FalkorDB" db={databases.falkordb} />
            <DatabaseStatus name="Neo4j" db={databases.neo4j} />
          </div>
        </div>

        {/* Sync Status */}
        <div className="space-y-2">
          <div className="text-sm font-medium">Sync Status</div>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">State</span>
              <Badge variant={sync.state === 'running' ? 'default' : 'secondary'}>
                {sync.state}
              </Badge>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Direction</span>
              <span className="font-medium">{sync.last_direction}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Last Sync</span>
              <span className="font-medium">
                {monitoringClient.constructor['formatRelativeTime'](sync.last_sync)}
              </span>
            </div>
          </div>
        </div>

        {/* Sync Statistics */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Success Rate</span>
            <span className="font-semibold text-green-500">{successPercent}%</span>
          </div>
          <Progress value={successPercent} className="h-2" />
        </div>

        <div className="grid grid-cols-3 gap-4 pt-2">
          <div>
            <div className="text-sm text-muted-foreground">Items Synced</div>
            <div className="text-xl font-bold">{sync.items_synced.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Nodes</div>
            <div className="text-xl font-bold">{sync.nodes_synced.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Edges</div>
            <div className="text-xl font-bold">{sync.edges_synced.toLocaleString()}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// Database Status Badge
const DatabaseStatus: React.FC<{
  name: string;
  db: { name: string; connected: boolean; response_time_ms: number };
}> = ({ name, db }) => (
  <div className="flex items-center justify-between p-2 bg-muted rounded-lg">
    <div className="flex items-center gap-2">
      {db.connected ? (
        <CheckCircle2 className="h-4 w-4 text-green-500" />
      ) : (
        <XCircle className="h-4 w-4 text-destructive" />
      )}
      <span className="text-sm font-medium">{name}</span>
    </div>
    <span className="text-xs text-muted-foreground">{db.response_time_ms}ms</span>
  </div>
);

// Graph Visualizer Card
const GraphVisualizerCard: React.FC<{ stats: GraphVisualizerStats | null; error?: string }> = ({ stats, error }) => {
  if (error) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <XCircle className="h-5 w-5 text-destructive" />
            Graph Visualizer - Offline
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  if (!stats) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Network className="h-5 w-5 text-primary" />
          Graph Visualizer
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Graph Statistics */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-sm text-muted-foreground">Total Nodes</div>
            <div className="text-2xl font-bold">{stats.total_nodes.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Total Edges</div>
            <div className="text-2xl font-bold">{stats.total_edges.toLocaleString()}</div>
          </div>
        </div>

        {/* Node Types */}
        <div className="space-y-2">
          <div className="text-sm font-medium">Node Types</div>
          <div className="space-y-1">
            {Object.entries(stats.node_types).map(([type, count]) => (
              <div key={type} className="flex justify-between text-sm">
                <span className="text-muted-foreground">{type}</span>
                <span className="font-medium">{count.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Graph Metrics */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-sm text-muted-foreground">Avg Degree</div>
            <div className="text-lg font-semibold">{stats.avg_degree.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-sm text-muted-foreground">Max Degree</div>
            <div className="text-lg font-semibold">{stats.max_degree.toFixed(1)}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default MonitoringDashboard;
