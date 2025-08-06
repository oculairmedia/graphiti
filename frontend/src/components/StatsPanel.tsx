import React from 'react';
import { X, BarChart3, PieChart, Activity, TrendingUp, Network, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import type { GraphData, GraphStats } from '../types/graph';

// Performance monitoring hook with proper unmount detection
const usePerformanceMonitoring = () => {
  const [performanceData, setPerformanceData] = React.useState({
    fps: 0,
    memory: 0,
    queryTime: 0,
    renderTime: 0
  });

  React.useEffect(() => {
    let frameCount = 0;
    let lastTime = performance.now();
    let animationId: number;
    let isMounted = true;

    const measureFPS = () => {
      // Check if component is still mounted before updating state
      if (!isMounted) return;
      
      frameCount++;
      const now = performance.now();
      
      if (now - lastTime >= 1000) {
        const fps = Math.round((frameCount * 1000) / (now - lastTime));
        
        // Only update state if component is still mounted
        if (isMounted) {
          // Safe memory monitoring with proper type checking
          const memoryUsage = typeof performance !== 'undefined' && 
            'memory' in performance && 
            typeof (performance as { memory?: { usedJSHeapSize?: number } }).memory === 'object' &&
            (performance as { memory: { usedJSHeapSize?: number } }).memory?.usedJSHeapSize
            ? Math.round((performance as { memory: { usedJSHeapSize: number } }).memory.usedJSHeapSize / 1024 / 1024)
            : 0;

          setPerformanceData(prev => ({
            ...prev,
            fps,
            memory: memoryUsage
          }));
        }
        
        frameCount = 0;
        lastTime = now;
      }
      
      // Only continue animation loop if component is still mounted
      if (isMounted) {
        animationId = requestAnimationFrame(measureFPS);
      }
    };

    animationId = requestAnimationFrame(measureFPS);

    return () => {
      isMounted = false;
      if (animationId) {
        cancelAnimationFrame(animationId);
      }
    };
  }, []);

  return performanceData;
};

interface StatsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  data?: GraphData;
}

// Compute real statistics from graph data
const computeGraphStats = (data?: GraphData): GraphStats | null => {
  console.log('[StatsPanel] Computing stats from data:', {
    hasData: !!data,
    hasNodes: !!data?.nodes,
    nodeCount: data?.nodes?.length || 0,
    hasEdges: !!data?.edges,
    edgeCount: data?.edges?.length || 0
  });
  
  if (!data || !data.nodes || !data.edges) {
    return null;
  }

  const { nodes, edges } = data;
  const totalNodes = nodes.length;
  const totalEdges = edges.length;
  const avgDegree = totalNodes > 0 ? (totalEdges * 2) / totalNodes : 0;
  const maxPossibleEdges = totalNodes * (totalNodes - 1) / 2;
  const density = maxPossibleEdges > 0 ? totalEdges / maxPossibleEdges : 0;

  // Calculate node type distribution
  const typeCount: Record<string, number> = {};
  nodes.forEach(node => {
    const type = node.node_type || 'Unknown';
    typeCount[type] = (typeCount[type] || 0) + 1;
  });

  const nodeTypes = Object.entries(typeCount).map(([type, count]) => ({
    type,
    count,
    percentage: Math.round((count / totalNodes) * 100),
    color: {
      'Entity': 'bg-node-entity',
      'Episodic': 'bg-node-episodic', 
      'Agent': 'bg-node-agent',
      'Community': 'bg-node-community'
    }[type] || 'bg-primary'
  }));

  // Calculate degree for each node and find top connected
  const degreeMap: Record<string, number> = {};
  edges.forEach(edge => {
    degreeMap[edge.from] = (degreeMap[edge.from] || 0) + 1;
    degreeMap[edge.to] = (degreeMap[edge.to] || 0) + 1;
  });

  const topNodes = nodes
    .map(node => ({
      name: node.label || node.id,
      degree: degreeMap[node.id] || 0,
      type: node.node_type || 'Unknown'
    }))
    .sort((a, b) => b.degree - a.degree)
    .slice(0, 5);

  return {
    overview: {
      totalNodes,
      totalEdges,
      avgDegree: Math.round(avgDegree * 100) / 100,
      density: Math.round(density * 10000) / 10000
    },
    nodeTypes,
    topNodes,
    performance: {
      queryTime: data.stats?.query_time || 0,
      renderTime: data.stats?.render_time || 0,
      fps: 0, // Will be filled with real data
      memory: data.stats?.memory_usage || 0
    }
  };
};

export const StatsPanel: React.FC<StatsPanelProps> = React.memo(({ 
  isOpen, 
  onClose,
  data
}) => {
  // Get real performance metrics
  const realPerformance = usePerformanceMonitoring();

  // Memoize expensive statistics computation
  const stats = React.useMemo(() => {
    const baseStats = computeGraphStats(data);
    if (baseStats) {
      // Replace fake performance metrics with real ones
      return {
        ...baseStats,
        performance: {
          queryTime: data?.stats?.query_time || baseStats.performance.queryTime,
          renderTime: data?.stats?.render_time || baseStats.performance.renderTime,
          fps: realPerformance.fps,
          memory: realPerformance.memory
        }
      };
    }
    return baseStats;
  }, [data, realPerformance]);

  if (!isOpen) return null;

  // Show loading state if no data available
  if (!stats) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
        <Card className="glass-panel w-full max-w-md">
          <CardContent className="p-6 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-4 mx-auto"></div>
            <p className="text-muted-foreground">Loading graph statistics...</p>
            <Button onClick={onClose} className="mt-4">Close</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card className="glass-panel w-full max-w-4xl max-h-[85vh] overflow-hidden animate-scale-in">
        <CardHeader className="pb-3 border-b border-border/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <BarChart3 className="h-5 w-5 text-primary" />
              <CardTitle className="text-lg">Graph Statistics</CardTitle>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="hover:bg-destructive/10"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-6 max-h-[75vh] overflow-y-auto custom-scrollbar">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            
            {/* Overview Stats */}
            <Card className="glass border-border/30">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center space-x-2">
                  <Network className="h-4 w-4 text-primary" />
                  <span>Graph Overview</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="text-center p-3 rounded-lg bg-secondary/20">
                    <div className="text-2xl font-bold text-primary">
                      {stats.overview.totalNodes.toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">Total Nodes</div>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-secondary/20">
                    <div className="text-2xl font-bold text-accent">
                      {stats.overview.totalEdges.toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">Total Edges</div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Avg Degree:</span>
                    <Badge variant="outline">{stats.overview.avgDegree}</Badge>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Density:</span>
                    <Badge variant="outline">{stats.overview.density}</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Node Type Distribution */}
            <Card className="glass border-border/30">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center space-x-2">
                  <PieChart className="h-4 w-4 text-primary" />
                  <span>Node Type Distribution</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {stats.nodeTypes.map((type) => (
                  <div key={type.type} className="space-y-2">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center space-x-2">
                        <div className={`w-3 h-3 rounded-full ${type.color}`} />
                        <span className="text-sm">{type.type}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <span className="text-xs text-muted-foreground">
                          {type.count.toLocaleString()}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {type.percentage}%
                        </Badge>
                      </div>
                    </div>
                    <Progress value={type.percentage} className="h-1.5" />
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Top Connected Nodes */}
            <Card className="glass border-border/30">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center space-x-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  <span>Most Connected Nodes</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {stats.topNodes.map((node, index) => (
                  <div key={`${node.name}-${index}-${node.degree}`} className="flex items-center justify-between p-2 rounded-lg hover:bg-secondary/20">
                    <div className="flex items-center space-x-3">
                      <Badge variant="outline" className="w-6 h-6 p-0 flex items-center justify-center text-xs">
                        {index + 1}
                      </Badge>
                      <div>
                        <div className="text-sm font-medium">{node.name}</div>
                        <div className="text-xs text-muted-foreground">{node.type}</div>
                      </div>
                    </div>
                    <Badge variant="secondary" className="text-xs">
                      {node.degree} connections
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>

            {/* Performance Metrics */}
            <Card className="glass border-border/30">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center space-x-2">
                  <Activity className="h-4 w-4 text-primary" />
                  <span>Performance</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="text-center p-3 rounded-lg bg-secondary/20">
                    <div className="text-lg font-bold text-accent">
                      {stats.performance.fps}
                    </div>
                    <div className="text-xs text-muted-foreground">FPS</div>
                  </div>
                  <div className="text-center p-3 rounded-lg bg-secondary/20">
                    <div className="text-lg font-bold text-warning">
                      {stats.performance.memory}MB
                    </div>
                    <div className="text-xs text-muted-foreground">Memory</div>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Query Time:</span>
                    <Badge variant="outline">{stats.performance.queryTime}ms</Badge>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Render Time:</span>
                    <Badge variant="outline">{stats.performance.renderTime}ms</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Graph Summary */}
            <Card className="glass border-border/30 lg:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center space-x-2">
                  <Clock className="h-4 w-4 text-primary" />
                  <span>Graph Summary</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="text-center p-4 rounded-lg bg-secondary/20">
                    <div className="text-lg font-bold text-primary">
                      {stats.nodeTypes.length}
                    </div>
                    <div className="text-xs text-muted-foreground">Node Types</div>
                  </div>
                  <div className="text-center p-4 rounded-lg bg-secondary/20">
                    <div className="text-lg font-bold text-accent">
                      {stats.topNodes.length > 0 ? stats.topNodes[0].degree : 0}
                    </div>
                    <div className="text-xs text-muted-foreground">Max Connections</div>
                  </div>
                  <div className="text-center p-4 rounded-lg bg-secondary/20">
                    <div className="text-lg font-bold text-warning">
                      {stats.nodeTypes.find(t => t.count === Math.max(...stats.nodeTypes.map(n => n.count)))?.type || 'N/A'}
                    </div>
                    <div className="text-xs text-muted-foreground">Dominant Type</div>
                  </div>
                </div>
              </CardContent>
            </Card>

          </div>
        </CardContent>

        <div className="p-4 border-t border-border/20 flex justify-end bg-secondary/20">
          <Button onClick={onClose}>
            Close
          </Button>
        </div>
      </Card>
    </div>
  );
}, (prevProps, nextProps) => {
  // Only re-render if panel visibility changes
  return prevProps.isOpen === nextProps.isOpen;
});