import React from 'react';
import { X, Pin, Eye, EyeOff, Copy, Download, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { GraphNode } from '../api/types';
import { useGraphConfig } from '../contexts/GraphConfigContext';

interface NodeDetailsPanelProps {
  node: GraphNode;
  onClose: () => void;
  onShowNeighbors?: (nodeId: string) => void;
}

export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose,
  onShowNeighbors
}) => {
  const { config } = useGraphConfig();
  
  const getNodeTypeColor = (type: string): string => {
    // Use the actual color from the dynamic configuration
    return config.nodeTypeColors[type] || '#9CA3AF'; // Fallback to gray if not found
  };

  // Determine the best text color for contrast
  const getContrastColor = (backgroundColor: string): string => {
    // Convert hex to RGB
    const hex = backgroundColor.replace('#', '');
    const r = parseInt(hex.substr(0, 2), 16);
    const g = parseInt(hex.substr(2, 2), 16);
    const b = parseInt(hex.substr(4, 2), 16);
    
    // Calculate luminance
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    
    // Return white for dark backgrounds, black for light backgrounds
    return luminance > 0.5 ? '#000000' : '#ffffff';
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Use real node data
  const data = {
    id: node.id,
    name: node.label || node.id,
    type: node.node_type || 'Unknown',
    summary: node.summary || node.description || '',
    properties: node.properties || {},
    centrality: {
      degree: node.properties?.degree_centrality || 0,
      betweenness: node.properties?.betweenness_centrality || 0,
      pagerank: node.properties?.pagerank_centrality || node.properties?.pagerank || 0,
      eigenvector: node.properties?.eigenvector_centrality || 0
    },
    timestamps: {
      created: node.created_at || node.properties?.created || new Date().toISOString(),
      updated: node.updated_at || node.properties?.updated || new Date().toISOString()
    },
    connections: node.properties?.degree || node.properties?.connections || 0
  };

  return (
    <Card className="glass-panel w-96 max-h-[80vh] overflow-hidden animate-fade-in flex flex-col">
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex items-start justify-between">
          <div className="flex-1 pr-2">
            <CardTitle className="text-lg leading-tight mb-2">
              {data.name}
            </CardTitle>
            <div className="flex items-center space-x-2 mb-2">
              <Badge 
                className="text-xs border-0"
                style={{ 
                  backgroundColor: getNodeTypeColor(data.type),
                  color: getContrastColor(getNodeTypeColor(data.type))
                }}
              >
                {data.type}
              </Badge>
              <Badge variant="outline" className="text-xs">
                ID: {data.id.slice(-6)}
              </Badge>
            </div>
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

      <CardContent className="flex-1 overflow-y-auto custom-scrollbar space-y-4 min-h-0">
        
        {/* Summary */}
        {data.summary && (
          <div>
            <h4 className="text-sm font-medium mb-2 text-muted-foreground">Summary</h4>
            <p className="text-sm leading-relaxed">{data.summary}</p>
          </div>
        )}

        <Separator />

        {/* Properties */}
        <div>
          <h4 className="text-sm font-medium mb-3 text-muted-foreground">Properties</h4>
          <div className="space-y-2">
            {Object.entries(data.properties).map(([key, value]) => (
              <div key={key} className="flex justify-between items-start">
                <span className="text-xs text-muted-foreground capitalize">
                  {key.replace(/([A-Z])/g, ' $1')}:
                </span>
                <span className="text-xs text-right flex-1 ml-2">
                  {Array.isArray(value) ? value.join(', ') : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Centrality Metrics */}
        <div>
          <h4 className="text-sm font-medium mb-3 text-muted-foreground">Centrality Metrics</h4>
          <div className="space-y-3">
            {Object.entries(data.centrality).map(([metric, value]) => (
              <div key={metric}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs capitalize">
                    {metric.replace(/([A-Z])/g, ' $1')}
                  </span>
                  <span className="text-xs text-primary font-medium">
                    {(Number(value) * 100).toFixed(1)}%
                  </span>
                </div>
                <Progress 
                  value={Number(value) * 100} 
                  className="h-1.5"
                />
              </div>
            ))}
          </div>
        </div>

        <Separator />

        {/* Connection Info */}
        <div>
          <h4 className="text-sm font-medium mb-2 text-muted-foreground">Connections</h4>
          <div className="flex items-center justify-between">
            <span className="text-xs">Related Nodes:</span>
            <Badge variant="secondary" className="text-xs">
              {data.connections}
            </Badge>
          </div>
        </div>

        {/* Timestamps */}
        <div>
          <h4 className="text-sm font-medium mb-2 text-muted-foreground">Timeline</h4>
          <div className="space-y-1">
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">Created:</span>
              <span className="text-xs">{formatDate(data.timestamps.created)}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">Updated:</span>
              <span className="text-xs">{formatDate(data.timestamps.updated)}</span>
            </div>
          </div>
        </div>

        <Separator />

        {/* Action Buttons */}
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" className="h-8">
            <Pin className="h-3 w-3 mr-1" />
            Pin
          </Button>
          <Button variant="outline" size="sm" className="h-8">
            <Eye className="h-3 w-3 mr-1" />
            Focus
          </Button>
          <Button variant="outline" size="sm" className="h-8">
            <Copy className="h-3 w-3 mr-1" />
            Copy ID
          </Button>
          <Button variant="outline" size="sm" className="h-8">
            <Download className="h-3 w-3 mr-1" />
            Export
          </Button>
        </div>

        <Button 
          variant="secondary" 
          className="w-full h-8" 
          size="sm"
          onClick={() => onShowNeighbors?.(data.id)}
          disabled={!onShowNeighbors}
        >
          <ExternalLink className="h-3 w-3 mr-2" />
          Show Neighbors
        </Button>

      </CardContent>
    </Card>
  );
};