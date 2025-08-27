import React from 'react';
import { Database, RefreshCw, Cpu, Zap, Activity, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useQueueStatus } from '@/hooks/useQueueStatus';

interface QueryControlsTabProps {
  config: {
    queryType: string;
    nodeLimit: number;
    searchTerm?: string;
  };
  isRefreshing: boolean;
  onQueryTypeChange: (value: string) => void;
  onNodeLimitChange: (value: number) => void;
  onSearchTermChange?: (value: string) => void;
  onRefreshGraph: () => void;
  onQuickQuery: (queryType: string, limit: number) => void;
}

export const QueryControlsTab: React.FC<QueryControlsTabProps> = ({
  config,
  isRefreshing,
  onQueryTypeChange,
  onNodeLimitChange,
  onSearchTermChange,
  onRefreshGraph,
  onQuickQuery,
}) => {
  const { 
    queueStatus, 
    isLoading: queueLoading, 
    isRefreshing: queueRefreshing, 
    error: queueError,
    isStale,
    lastUpdatedAgo
  } = useQueueStatus();
  return (
    <div className="space-y-4">
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Database className="h-4 w-4 text-primary" />
            <span>Query Controls</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs text-muted-foreground">Query Type</Label>
            <Select value={config.queryType} onValueChange={onQueryTypeChange}>
              <SelectTrigger className="h-8 bg-secondary/30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="glass">
                <SelectItem value="entire_graph">🌐 Entire Graph</SelectItem>
                <SelectItem value="high_degree">⭐ High Degree Nodes</SelectItem>
                <SelectItem value="agents">🤖 Agent Networks</SelectItem>
                <SelectItem value="search">🔍 Search Mode</SelectItem>
              </SelectContent>
            </Select>
          </div>
          
          <div>
            <Label className="text-xs text-muted-foreground">Node Limit</Label>
            <Input
              type="number"
              value={config.nodeLimit}
              onChange={(e) => onNodeLimitChange(parseInt(e.target.value) || 1000)}
              className="h-8 bg-secondary/30"
              placeholder="1000"
            />
          </div>

          {config.queryType === 'search' && (
            <div>
              <Label className="text-xs text-muted-foreground">Search Term</Label>
              <Input
                type="text"
                value={config.searchTerm || ''}
                onChange={(e) => onSearchTermChange?.(e.target.value)}
                placeholder="Enter search term..."
                className="h-8 bg-secondary/30"
              />
            </div>
          )}

          <div className="space-y-2">
            <Button 
              className="w-full h-8 bg-primary hover:bg-primary/90"
              onClick={onRefreshGraph}
              disabled={isRefreshing}
            >
              {isRefreshing ? (
                <RefreshCw className="h-3 w-3 mr-2 animate-spin" />
              ) : (
                <Database className="h-3 w-3 mr-2" />
              )}
              {isRefreshing ? 'Loading...' : 'Refresh Graph'}
            </Button>
            
            <div className="grid grid-cols-2 gap-2">
              <Button 
                variant="outline" 
                className="h-8 text-xs"
                onClick={() => onQuickQuery('high_degree', 200)}
              >
                ⚡ Top 200
              </Button>
              <Button 
                variant="outline" 
                className="h-8 text-xs"
                onClick={() => onQuickQuery('agents', 500)}
              >
                🤖 Agents
              </Button>
            </div>
            
            <Button 
              variant="destructive" 
              className="w-full h-8"
              onClick={() => onQuickQuery('entire_graph', 50000)}
            >
              <Cpu className="h-3 w-3 mr-2" />
              Load Full Graph (GPU)
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Advanced Query Options */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Zap className="h-4 w-4 text-primary" />
            <span>Quick Queries</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <Button 
              variant="outline" 
              size="sm" 
              className="h-8 text-xs"
              onClick={() => onQuickQuery('high_degree', 1000)}
            >
              📊 High Centrality
            </Button>
            <Button 
              variant="outline" 
              size="sm" 
              className="h-8 text-xs"
              onClick={() => onQuickQuery('agents', 300)}
            >
              🤖 AI Agents
            </Button>
          </div>
          
          <div className="grid grid-cols-1 gap-2">
            <Button 
              variant="outline" 
              size="sm" 
              className="h-8 text-xs"
              onClick={() => onQuickQuery('entire_graph', 10000)}
            >
              🌐 Medium Graph (10K)
            </Button>
            <Button 
              variant="outline" 
              size="sm" 
              className="h-8 text-xs"
              onClick={() => onQuickQuery('entire_graph', 5000)}
            >
              ⚡ Fast Load (5K)
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* System Status */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Activity className="h-4 w-4 text-primary" />
            <span>Queue Status</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 min-h-[100px]">
          {queueLoading && !queueStatus ? (
            // Initial-only skeleton matching final layout heights
            <div className="space-y-2">
              <div className="h-5 w-24 bg-muted/30 rounded animate-pulse" />
              <div className="grid grid-cols-2 gap-2">
                <div className="h-4 bg-muted/30 rounded animate-pulse" />
                <div className="h-4 bg-muted/30 rounded animate-pulse" />
              </div>
            </div>
          ) : queueStatus ? (
            <div className={`space-y-2 motion-safe:transition-opacity motion-safe:duration-300 ${isStale ? 'opacity-75' : 'opacity-100'}`}>
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Status</span>
                  {queueRefreshing && (
                    <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                  )}
                </div>
                <Badge 
                  variant={queueStatus.status === 'processing' ? 'default' : 'secondary'}
                  className={`text-xs h-5 transition-colors duration-200 ${
                    queueStatus.status === 'processing' ? 'bg-green-500/20 text-green-400 border-green-500/30' :
                    queueStatus.status === 'idle' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
                    'bg-gray-500/20 text-gray-400 border-gray-500/30'
                  }`}
                >
                  {queueStatus.status}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Pending</span>
                  <span className="text-primary font-mono motion-safe:transition-all motion-safe:duration-300 ease-out">
                    {queueStatus.visible_messages}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Processing</span>
                  <span className="text-primary font-mono motion-safe:transition-all motion-safe:duration-300 ease-out">
                    {queueStatus.invisible_messages}
                  </span>
                </div>
              </div>
              {queueStatus.total_processed > 0 && (
                <div className="flex justify-between items-center text-xs">
                  <span className="text-muted-foreground">Success Rate</span>
                  <Badge 
                    variant="outline"
                    className={`text-xs h-5 motion-safe:transition-colors motion-safe:duration-300 ease-out font-mono ${
                      queueStatus.success_rate >= 95 ? 'text-green-400 border-green-500/30' :
                      queueStatus.success_rate >= 80 ? 'text-yellow-400 border-yellow-500/30' :
                      'text-red-400 border-red-500/30'
                    }`}
                  >
                    {queueStatus.success_rate.toFixed(0)}%
                  </Badge>
                </div>
              )}
              {(queueError || isStale) && (
                <div className={`text-[10px] ${queueError ? 'text-amber-400' : 'text-muted-foreground'}`}>
                  {queueError ? 'Connection issue; showing last update' : 
                   `Updated ${lastUpdatedAgo}s ago`}
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-muted-foreground">
              No queue data available
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};