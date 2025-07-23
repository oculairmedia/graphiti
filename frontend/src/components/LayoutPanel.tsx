import React, { useState } from 'react';
import { ChevronRight, ChevronLeft, Layout, Network, Circle, GitBranch, Clock, Layers } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';

interface LayoutPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export const LayoutPanel: React.FC<LayoutPanelProps> = ({ 
  collapsed, 
  onToggleCollapse 
}) => {
  const [selectedLayout, setSelectedLayout] = useState('force-directed');
  const [hierarchyDirection, setHierarchyDirection] = useState('top-down');
  const [radialCenter, setRadialCenter] = useState('');
  const [circularOrdering, setCircularOrdering] = useState('degree');
  const [clusterBy, setClusterBy] = useState('type');

  const layouts = [
    {
      id: 'force-directed',
      name: 'Force-Directed',
      icon: Network,
      description: 'Physics-based layout with natural clustering'
    },
    {
      id: 'hierarchical',
      name: 'Hierarchical',
      icon: GitBranch,
      description: 'Tree-like structure with clear levels'
    },
    {
      id: 'radial',
      name: 'Radial',
      icon: Circle,
      description: 'Nodes arranged in concentric circles'
    },
    {
      id: 'circular',
      name: 'Circular',
      icon: Circle,
      description: 'Nodes arranged in a perfect circle'
    },
    {
      id: 'temporal',
      name: 'Temporal',
      icon: Clock,
      description: 'Timeline-based arrangement'
    },
    {
      id: 'cluster',
      name: 'Cluster',
      icon: Layers,
      description: 'Grouped by communities or types'
    }
  ];

  if (collapsed) {
    return (
      <div className="h-full w-12 glass-panel border-l border-border/20 flex flex-col items-center py-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleCollapse}
          className="mb-4 hover:bg-primary/10"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="flex flex-col space-y-3">
          {layouts.slice(0, 4).map((layout) => (
            <Button 
              key={layout.id}
              variant="ghost" 
              size="sm" 
              className="p-2 hover:bg-primary/10"
              title={layout.name}
            >
              <layout.icon className="h-4 w-4" />
            </Button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-80 glass-panel border-l border-border/20 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-border/20 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Graph Layouts</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleCollapse}
          className="hover:bg-primary/10"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
        
        {/* Layout Selection */}
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground">Choose Layout</h3>
          <div className="grid gap-2">
            {layouts.map((layout) => (
              <Card 
                key={layout.id}
                className={`cursor-pointer transition-all hover:scale-[1.02] ${
                  selectedLayout === layout.id 
                    ? 'ring-2 ring-primary bg-primary/5' 
                    : 'glass border-border/30 hover:border-primary/30'
                }`}
                onClick={() => setSelectedLayout(layout.id)}
              >
                <CardContent className="p-3">
                  <div className="flex items-center space-x-3">
                    <layout.icon className="h-4 w-4 text-primary" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-medium">{layout.name}</h4>
                        {selectedLayout === layout.id && (
                          <Badge variant="secondary" className="text-xs">
                            Active
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">
                        {layout.description}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>

        {/* Layout-Specific Options */}
        {selectedLayout === 'hierarchical' && (
          <Card className="glass border-border/30">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Hierarchical Options</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label className="text-xs text-muted-foreground">Direction</Label>
                <Select value={hierarchyDirection} onValueChange={setHierarchyDirection}>
                  <SelectTrigger className="h-8 bg-secondary/30">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="glass">
                    <SelectItem value="top-down">Top to Bottom</SelectItem>
                    <SelectItem value="bottom-up">Bottom to Top</SelectItem>
                    <SelectItem value="left-right">Left to Right</SelectItem>
                    <SelectItem value="right-left">Right to Left</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        )}

        {selectedLayout === 'radial' && (
          <Card className="glass border-border/30">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Radial Options</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label className="text-xs text-muted-foreground">Center Node ID</Label>
                <Input
                  value={radialCenter}
                  onChange={(e) => setRadialCenter(e.target.value)}
                  placeholder="Enter node ID or leave empty for auto"
                  className="h-8 bg-secondary/30"
                />
              </div>
            </CardContent>
          </Card>
        )}

        {selectedLayout === 'circular' && (
          <Card className="glass border-border/30">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Circular Options</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label className="text-xs text-muted-foreground">Node Ordering</Label>
                <Select value={circularOrdering} onValueChange={setCircularOrdering}>
                  <SelectTrigger className="h-8 bg-secondary/30">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="glass">
                    <SelectItem value="degree">By Degree</SelectItem>
                    <SelectItem value="centrality">By Centrality</SelectItem>
                    <SelectItem value="type">By Type</SelectItem>
                    <SelectItem value="alphabetical">Alphabetical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        )}

        {selectedLayout === 'cluster' && (
          <Card className="glass border-border/30">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Cluster Options</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <Label className="text-xs text-muted-foreground">Cluster By</Label>
                <Select value={clusterBy} onValueChange={setClusterBy}>
                  <SelectTrigger className="h-8 bg-secondary/30">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="glass">
                    <SelectItem value="type">Node Type</SelectItem>
                    <SelectItem value="community">Community</SelectItem>
                    <SelectItem value="centrality">Centrality Range</SelectItem>
                    <SelectItem value="temporal">Time Period</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Apply Button */}
        <Card className="glass border-border/30">
          <CardContent className="p-3">
            <Button 
              className="w-full bg-primary hover:bg-primary/90"
              size="sm"
            >
              <Layout className="h-3 w-3 mr-2" />
              Apply Layout
            </Button>
          </CardContent>
        </Card>

        {/* Layout Presets */}
        <Card className="glass border-border/30">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Quick Presets</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Button variant="outline" size="sm" className="w-full h-8 justify-start">
              Exploration Mode
            </Button>
            <Button variant="outline" size="sm" className="w-full h-8 justify-start">
              Analysis Mode
            </Button>
            <Button variant="outline" size="sm" className="w-full h-8 justify-start">
              Presentation Mode
            </Button>
          </CardContent>
        </Card>

      </div>
    </div>
  );
};