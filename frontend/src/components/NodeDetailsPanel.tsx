import React from 'react';
import { X, Pin, Eye, EyeOff, Copy, Download, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';

interface NodeDetailsPanelProps {
  node: any;
  onClose: () => void;
}

export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose 
}) => {
  const getNodeTypeColor = (type: string) => {
    const colors = {
      Entity: 'bg-node-entity',
      Episodic: 'bg-node-episodic', 
      Agent: 'bg-node-agent',
      Community: 'bg-node-community'
    };
    return colors[type as keyof typeof colors] || 'bg-primary';
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

  // Mock data for demonstration
  const mockData = {
    id: 'node_12345',
    name: 'Neural Network Research',
    type: 'Entity',
    summary: 'Comprehensive research on neural network architectures and their applications in modern AI systems. This work explores deep learning methodologies and their practical implementations.',
    properties: {
      field: 'Artificial Intelligence',
      author: 'Dr. Sarah Chen',
      citations: 342,
      year: 2024,
      institution: 'MIT AI Lab',
      keywords: ['Neural Networks', 'Deep Learning', 'AI']
    },
    centrality: {
      degree: 0.85,
      betweenness: 0.72,
      pagerank: 0.91,
      eigenvector: 0.78
    },
    timestamps: {
      created: '2024-01-15T10:30:00Z',
      updated: '2024-01-20T14:45:00Z'
    },
    connections: 23
  };

  const data = { ...mockData, ...node };

  return (
    <Card className="glass-panel w-96 max-h-[80vh] overflow-hidden animate-fade-in">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 pr-2">
            <CardTitle className="text-lg leading-tight mb-2">
              {data.name}
            </CardTitle>
            <div className="flex items-center space-x-2 mb-2">
              <Badge 
                className={`${getNodeTypeColor(data.type)} text-black text-xs`}
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

      <CardContent className="overflow-y-auto custom-scrollbar space-y-4">
        
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

        <Button variant="secondary" className="w-full h-8" size="sm">
          <ExternalLink className="h-3 w-3 mr-2" />
          Show Neighbors
        </Button>

      </CardContent>
    </Card>
  );
};