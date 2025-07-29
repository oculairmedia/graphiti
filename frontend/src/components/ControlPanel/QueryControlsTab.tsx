import React from 'react';
import { Database, RefreshCw, Cpu, Zap } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface QueryControlsTabProps {
  config: {
    queryType: string;
    nodeLimit: number;
  };
  isRefreshing: boolean;
  onQueryTypeChange: (value: string) => void;
  onNodeLimitChange: (value: number) => void;
  onRefreshGraph: () => void;
  onQuickQuery: (queryType: string, limit: number) => void;
}

export const QueryControlsTab: React.FC<QueryControlsTabProps> = ({
  config,
  isRefreshing,
  onQueryTypeChange,
  onNodeLimitChange,
  onRefreshGraph,
  onQuickQuery,
}) => {
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
    </div>
  );
};