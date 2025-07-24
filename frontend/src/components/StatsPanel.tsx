import React from 'react';
import { X, BarChart3, PieChart, Activity, TrendingUp, Network, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

interface StatsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

// Memoized mock data to prevent re-creation on every render
const MOCK_STATS = {
  overview: {
    totalNodes: 4247,
    totalEdges: 18392,
    avgDegree: 8.66,
    density: 0.002
  },
  nodeTypes: [
    { type: 'Entity', count: 2847, percentage: 67, color: 'bg-node-entity' },
    { type: 'Episodic', count: 1024, percentage: 24, color: 'bg-node-episodic' },
    { type: 'Agent', count: 892, percentage: 21, color: 'bg-node-agent' },
    { type: 'Community', count: 156, percentage: 4, color: 'bg-node-community' }
  ],
  topNodes: [
    { name: 'Neural Network Research', degree: 247, type: 'Entity' },
    { name: 'Dr. Sarah Chen', degree: 189, type: 'Agent' },
    { name: 'MIT AI Lab', degree: 156, type: 'Community' },
    { name: 'Deep Learning Conference 2024', degree: 134, type: 'Episodic' },
    { name: 'Machine Learning Framework', degree: 128, type: 'Entity' }
  ],
  performance: {
    queryTime: 247,
    renderTime: 1340,
    fps: 60,
    memory: 156
  }
} as const;

export const StatsPanel: React.FC<StatsPanelProps> = React.memo(({ 
  isOpen, 
  onClose 
}) => {
  const stats = MOCK_STATS;

  if (!isOpen) return null;

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
                  <div key={node.name} className="flex items-center justify-between p-2 rounded-lg hover:bg-secondary/20">
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

            {/* Activity Timeline */}
            <Card className="glass border-border/30 lg:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center space-x-2">
                  <Clock className="h-4 w-4 text-primary" />
                  <span>Recent Activity</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-secondary/20">
                    <div className="flex items-center space-x-3">
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                      <span className="text-sm">Query executed: High Degree Nodes</span>
                    </div>
                    <span className="text-xs text-muted-foreground">2 minutes ago</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-secondary/20">
                    <div className="flex items-center space-x-3">
                      <div className="w-2 h-2 rounded-full bg-accent" />
                      <span className="text-sm">Layout changed: Force-Directed</span>
                    </div>
                    <span className="text-xs text-muted-foreground">5 minutes ago</span>
                  </div>
                  <div className="flex items-center justify-between p-3 rounded-lg bg-secondary/20">
                    <div className="flex items-center space-x-3">
                      <div className="w-2 h-2 rounded-full bg-warning" />
                      <span className="text-sm">Filters applied: Entity nodes only</span>
                    </div>
                    <span className="text-xs text-muted-foreground">8 minutes ago</span>
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