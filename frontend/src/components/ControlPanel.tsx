import React, { useState, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Database, Settings2, Palette, Zap, RotateCcw, Paintbrush, Layers, Eye, RefreshCw, Cpu, Play, Pause, Square, Shuffle, ZoomIn } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Checkbox } from '@/components/ui/checkbox';
import { useGraphConfig } from '@/contexts/GraphConfigContext';
import { useQuery } from '@tanstack/react-query';
import { graphClient } from '@/api/graphClient';
import { ColorPicker } from '@/components/ui/ColorPicker';
import type { GraphData, GraphNode } from '@/types/graph';

interface ControlPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onLayoutChange?: (layout: string) => void;
}

// Compute node types from real graph data dynamically
const computeNodeTypes = (graphData?: GraphData): Array<{ id: string; name: string; count: number }> => {
  if (!graphData?.nodes) {
    // Return empty array if no data available - no hardcoded types
    return [];
  }

  // Count actual node types from graph data
  const typeCount: Record<string, number> = {};
  graphData.nodes.forEach((node: GraphNode) => {
    const type = node.node_type || 'Unknown';
    typeCount[type] = (typeCount[type] || 0) + 1;
  });

  // Convert to expected format using only the actual types from the data
  return Object.entries(typeCount)
    .map(([type, count]) => ({
      id: type,
      name: type,
      count
    }))
    .sort((a, b) => b.count - a.count); // Sort by count descending
};

// Convert hex color to HSL for CSS custom properties
const hexToHsl = (hex: string): string => {
  // Remove # if present
  hex = hex.replace('#', '');
  
  // Parse hex values
  const r = parseInt(hex.substr(0, 2), 16) / 255;
  const g = parseInt(hex.substr(2, 2), 16) / 255;
  const b = parseInt(hex.substr(4, 2), 16) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }

  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
};

export const ControlPanel: React.FC<ControlPanelProps> = React.memo(({ 
  collapsed, 
  onToggleCollapse,
  onLayoutChange
}) => {
  const { config, updateConfig, updateNodeTypeConfigurations, applyLayout, cosmographRef } = useGraphConfig();
  
  // Get current graph data for layout operations
  const { data: graphData } = useQuery({
    queryKey: ['graphData', config.queryType, config.nodeLimit],
    queryFn: () => graphClient.getGraphData({
      query_type: config.queryType,
      limit: config.nodeLimit
    }),
    staleTime: 30000,
    refetchOnWindowFocus: false
  });
  const queryClient = useQueryClient();
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  // Compute real node types from graph data with memoization
  const nodeTypes = React.useMemo(() => computeNodeTypes(graphData), [graphData]);
  
  // Update node type configurations when graph data changes
  React.useEffect(() => {
    if (nodeTypes.length > 0) {
      const nodeTypeIds = nodeTypes.map(type => type.id);
      updateNodeTypeConfigurations(nodeTypeIds);
    }
  }, [nodeTypes, updateNodeTypeConfigurations]);

  // Simulation control functions
  const handleSimulationStart = useCallback(() => {
    if (cosmographRef?.current && typeof cosmographRef.current.start === 'function') {
      cosmographRef.current.start(1.0); // Full alpha for strong initial impulse
      console.log('Simulation started');
    }
  }, [cosmographRef]);

  const handleSimulationPause = useCallback(() => {
    if (cosmographRef?.current && typeof cosmographRef.current.pause === 'function') {
      cosmographRef.current.pause();
      console.log('Simulation paused');
    }
  }, [cosmographRef]);

  const handleSimulationRestart = useCallback(() => {
    if (cosmographRef?.current && typeof cosmographRef.current.restart === 'function') {
      cosmographRef.current.restart();
      console.log('Simulation restarted');
    }
  }, [cosmographRef]);

  const handleResetToDefaults = useCallback(() => {
    updateConfig({
      // Reset to Cosmograph v2.0 defaults
      repulsion: 0.1,
      simulationRepulsionTheta: 1.7,
      linkSpring: 1.0,
      linkDistance: 2,
      gravity: 0.0,
      centerForce: 0.0,
      friction: 0.85,
      simulationDecay: 1000,
      mouseRepulsion: 2.0,
      spaceSize: 4096,
      randomSeed: undefined,
      disableSimulation: null
    });
    console.log('Reset simulation to defaults');
  }, [updateConfig]);

  const handleNodeTypeColorChange = (type: string, color: string) => {
    updateConfig({ 
      nodeTypeColors: { 
        ...config.nodeTypeColors, 
        [type]: color 
      } 
    });
  };

  const handleNodeTypeVisibilityChange = (type: string, visible: boolean) => {
    updateConfig({ 
      nodeTypeVisibility: { 
        ...config.nodeTypeVisibility, 
        [type]: visible 
      } 
    });
  };

  const handleRefreshGraph = async (): Promise<void> => {
    setIsRefreshing(true);
    try {
      // Invalidate the graph data query to force a refresh
      await queryClient.invalidateQueries({ 
        queryKey: ['graphData', config.queryType, config.nodeLimit] 
      });
    } catch (error) {
      console.error('Error refreshing graph:', error);
      // In production, you might want to show a user-friendly error message
      // toast.error('Failed to refresh graph data. Please try again.');
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleQuickQuery = async (queryType: string, limit: number): Promise<void> => {
    try {
      updateConfig({ queryType, nodeLimit: limit });
      // Small delay to let config update, then refresh
      setTimeout(() => {
        handleRefreshGraph().catch(error => {
          console.error('Error in handleQuickQuery refresh:', error);
        });
      }, 100);
    } catch (error) {
      console.error('Error in handleQuickQuery:', error);
    }
  };

  if (collapsed) {
    return (
      <div className="h-full w-12 glass-panel border-r border-border/20 flex flex-col items-center py-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleCollapse}
          className="mb-4 hover:bg-primary/10"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
        <div className="flex flex-col space-y-3">
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Query">
            <Database className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Rendering">
            <Settings2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Node Styling">
            <Paintbrush className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Physics">
            <Zap className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-80 glass-panel border-r border-border/20 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-border/20 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Graph Controls</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleCollapse}
          className="hover:bg-primary/10"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
      </div>

      {/* Scrollable Content with Tabs */}
      <div className="flex-1 flex flex-col min-h-0">
        <Tabs defaultValue="query" className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid grid-cols-4 m-4 mb-2 glass">
            <TabsTrigger value="query" className="text-xs">
              <Database className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="styling" className="text-xs">
              <Paintbrush className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="physics" className="text-xs">
              <Zap className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="render" className="text-xs">
              <Settings2 className="h-3 w-3" />
            </TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto custom-scrollbar px-4 pb-4 min-h-0">
            
            {/* Query Controls Tab */}
            <TabsContent value="query" className="mt-0 space-y-4">
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
                    <Select value={config.queryType} onValueChange={(value) => updateConfig({ queryType: value })}>
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
                      onChange={(e) => updateConfig({ nodeLimit: parseInt(e.target.value) || 1000 })}
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
                      onClick={handleRefreshGraph}
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
                        onClick={() => handleQuickQuery('high_degree', 200)}
                      >
                        ⚡ Top 200
                      </Button>
                      <Button 
                        variant="outline" 
                        className="h-8 text-xs"
                        onClick={() => handleQuickQuery('agents', 500)}
                      >
                        🤖 Agents
                      </Button>
                    </div>
                    
                    <Button 
                      variant="destructive" 
                      className="w-full h-8"
                      onClick={() => handleQuickQuery('entire_graph', 50000)}
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
                      onClick={() => handleQuickQuery('high_degree', 1000)}
                    >
                      📊 High Centrality
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={() => handleQuickQuery('agents', 300)}
                    >
                      🤖 AI Agents
                    </Button>
                  </div>
                  
                  <div className="grid grid-cols-1 gap-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={() => handleQuickQuery('entire_graph', 10000)}
                    >
                      🌐 Medium Graph (10K)
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={() => handleQuickQuery('entire_graph', 5000)}
                    >
                      ⚡ Fast Load (5K)
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Node Styling Tab */}
            <TabsContent value="styling" className="mt-0 space-y-4">
              {/* Node Type Colors & Visibility */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Palette className="h-4 w-4 text-primary" />
                    <span>Node Types</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {nodeTypes.map((type) => (
                    <div key={type.id} className="space-y-2 p-3 rounded-lg border border-border/30">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <Checkbox
                            checked={config.nodeTypeVisibility[type.id as keyof typeof config.nodeTypeVisibility]}
                            onCheckedChange={(checked) => 
                              handleNodeTypeVisibilityChange(type.id, !!checked)
                            }
                          />
                          <div className="flex items-center space-x-2">
                            <div 
                              className="w-4 h-4 rounded-full border border-border/30 control-color-indicator"
                              style={{
                                '--indicator-color': hexToHsl(config.nodeTypeColors[type.id as keyof typeof config.nodeTypeColors] || '#9CA3AF')
                              } as React.CSSProperties}
                            />
                            <span className="text-sm font-medium">{type.name}</span>
                          </div>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {type.count.toLocaleString()}
                        </Badge>
                      </div>
                      <ColorPicker
                        color={config.nodeTypeColors[type.id as keyof typeof config.nodeTypeColors]}
                        onChange={(color) => handleNodeTypeColorChange(type.id, color)}
                        className="w-full"
                      />
                    </div>
                  ))}
                </CardContent>
              </Card>

              {/* Node Color Scheme */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Palette className="h-4 w-4 text-primary" />
                    <span>Color Scheme</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">Node Color Scheme</Label>
                    <Select value={config.colorScheme} onValueChange={(value) => updateConfig({ colorScheme: value })}>
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="by-type">🏷️ By Node Type</SelectItem>
                        <SelectItem value="by-centrality">📊 By Centrality</SelectItem>
                        <SelectItem value="by-pagerank">🔗 By PageRank</SelectItem>
                        <SelectItem value="by-degree">🌐 By Degree</SelectItem>
                        <SelectItem value="by-community">👥 By Community</SelectItem>
                        <SelectItem value="custom">🎨 Custom Colors</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {config.colorScheme === 'by-type' && (
                    <div className="p-3 rounded-lg bg-secondary/20 border border-border/30">
                      <p className="text-xs text-muted-foreground">
                        Using individual type colors set above. Modify colors in the Node Types section.
                      </p>
                    </div>
                  )}

                  {config.colorScheme !== 'by-type' && (
                    <div className="space-y-3">
                      <div className="p-3 rounded-lg bg-secondary/20 border border-border/30">
                        <p className="text-xs text-muted-foreground mb-2">
                          {config.colorScheme === 'by-centrality' && 'Colors nodes by centrality metrics - red (high) to blue (low)'}
                          {config.colorScheme === 'by-pagerank' && 'Colors nodes by PageRank score - warmer colors for higher scores'}
                          {config.colorScheme === 'by-degree' && 'Colors nodes by connection count - size correlates with color intensity'}
                          {config.colorScheme === 'by-community' && 'Colors nodes by detected community groups'}
                          {config.colorScheme === 'custom' && 'Uses custom color mapping based on node properties'}
                        </p>
                      </div>

                      {(config.colorScheme === 'by-centrality' || config.colorScheme === 'by-pagerank' || config.colorScheme === 'by-degree') && (
                        <div className="grid grid-cols-2 gap-3">
                          <ColorPicker
                            color={config.gradientHighColor}
                            onChange={(color) => updateConfig({ gradientHighColor: color })}
                            label="High Value Color"
                            className="w-full"
                            swatches={['#FF6B6B', '#FF4757', '#FF3838', '#FF6348', '#FF9F43', '#F39C12', '#E74C3C', '#C0392B']}
                          />
                          <ColorPicker
                            color={config.gradientLowColor}
                            onChange={(color) => updateConfig({ gradientLowColor: color })}
                            label="Low Value Color"
                            className="w-full"
                            swatches={['#4ECDC4', '#00D2D3', '#17A2B8', '#3498DB', '#2980B9', '#5DADE2', '#AED6F1', '#EBF5FB']}
                          />
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Size Mapping */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Layers className="h-4 w-4 text-primary" />
                    <span>Size Scaling</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">Size Mapped to</Label>
                    <Select value={config.sizeMapping} onValueChange={(value) => updateConfig({ sizeMapping: value })}>
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="uniform">Uniform Size</SelectItem>
                        <SelectItem value="degree">Degree Centrality</SelectItem>
                        <SelectItem value="betweenness">Betweenness Centrality</SelectItem>
                        <SelectItem value="pagerank">PageRank Score</SelectItem>
                        <SelectItem value="importance">Importance Centrality</SelectItem>
                        <SelectItem value="connections">Connection Count</SelectItem>
                        <SelectItem value="custom">Custom Property</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <Label className="text-xs text-muted-foreground">Min Size</Label>
                        <Badge variant="outline" className="text-xs">{config.minNodeSize}px</Badge>
                      </div>
                      <Slider
                        value={[config.minNodeSize]}
                        onValueChange={([value]) => updateConfig({ minNodeSize: value })}
                        max={10}
                        min={1}
                        step={1}
                        className="w-full"
                      />
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <Label className="text-xs text-muted-foreground">Max Size</Label>
                        <Badge variant="outline" className="text-xs">{config.maxNodeSize}px</Badge>
                      </div>
                      <Slider
                        value={[config.maxNodeSize]}
                        onValueChange={([value]) => updateConfig({ maxNodeSize: value })}
                        max={30}
                        min={5}
                        step={1}
                        className="w-full"
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Size Multiplier</Label>
                      <Badge variant="outline" className="text-xs">{config.sizeMultiplier.toFixed(1)}x</Badge>
                    </div>
                    <Slider
                      value={[config.sizeMultiplier]}
                      onValueChange={([value]) => updateConfig({ sizeMultiplier: value })}
                      max={3}
                      min={0.1}
                      step={0.1}
                      className="w-full"
                    />
                  </div>
                </CardContent>
              </Card>

            </TabsContent>

            {/* Physics Tab */}
            <TabsContent value="physics" className="mt-0 space-y-4">
              {/* Simulation Control */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Play className="h-4 w-4 text-primary" />
                    <span>Simulation Control</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">Simulation Mode</Label>
                    <Select 
                      value={config.disableSimulation === null ? 'auto' : config.disableSimulation ? 'disabled' : 'enabled'} 
                      onValueChange={(value) => {
                        const newValue = value === 'auto' ? null : value === 'enabled' ? false : true;
                        updateConfig({ disableSimulation: newValue });
                      }}
                    >
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="auto">🤖 Auto (detect links)</SelectItem>
                        <SelectItem value="enabled">▶️ Force Simulation On</SelectItem>
                        <SelectItem value="disabled">⏹️ Static Positioning</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div className="grid grid-cols-3 gap-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={handleSimulationStart}
                    >
                      <Play className="h-3 w-3 mr-1" />
                      Start
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={handleSimulationPause}
                    >
                      <Pause className="h-3 w-3 mr-1" />
                      Pause
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={handleSimulationRestart}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" />
                      Restart
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Force Configuration */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-primary" />
                    <span>Force Configuration</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Repulsion Force</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.repulsion]}
                        onValueChange={([value]) => updateConfig({ repulsion: value })}
                        max={10}
                        min={0}
                        step={0.01}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.repulsion.toFixed(2)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ repulsion: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Controls node repulsion strength</p>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Repulsion Theta</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.simulationRepulsionTheta]}
                        onValueChange={([value]) => updateConfig({ simulationRepulsionTheta: value })}
                        max={2}
                        min={0.3}
                        step={0.1}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.simulationRepulsionTheta.toFixed(2)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ simulationRepulsionTheta: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Barnes-Hut approximation level (higher = more accurate)</p>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Link Spring Force</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.linkSpring]}
                        onValueChange={([value]) => updateConfig({ linkSpring: value })}
                        max={5}
                        min={0}
                        step={0.01}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.linkSpring.toFixed(2)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ linkSpring: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Attraction strength between connected nodes</p>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Link Distance</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.linkDistance]}
                        onValueChange={([value]) => updateConfig({ linkDistance: value })}
                        max={20}
                        min={0.1}
                        step={0.1}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.linkDistance.toFixed(1)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ linkDistance: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Minimum distance between linked nodes</p>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Gravity Force</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.gravity]}
                        onValueChange={([value]) => updateConfig({ gravity: value })}
                        max={2}
                        min={0}
                        step={0.01}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.gravity.toFixed(2)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ gravity: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Attraction towards graph center</p>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Center Force</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.centerForce]}
                        onValueChange={([value]) => updateConfig({ centerForce: value })}
                        max={2}
                        min={0}
                        step={0.01}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.centerForce.toFixed(2)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ centerForce: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Centering force pulling nodes together</p>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Friction</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.friction]}
                        onValueChange={([value]) => updateConfig({ friction: value })}
                        max={1}
                        min={0}
                        step={0.01}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.friction.toFixed(2)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ friction: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Node movement damping (higher = slower)</p>
                  </div>
                </CardContent>
              </Card>

              {/* Advanced Settings */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Settings2 className="h-4 w-4 text-primary" />
                    <span>Advanced Settings</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Simulation Decay</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.simulationDecay]}
                        onValueChange={([value]) => updateConfig({ simulationDecay: value })}
                        max={10000}
                        min={100}
                        step={100}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.simulationDecay.toString()}
                        onChange={(e) => {
                          const value = parseInt(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ simulationDecay: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Simulation cooldown time</p>
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground mb-2 block">Mouse Repulsion</Label>
                    <div className="flex items-center space-x-2 mb-2">
                      <Slider
                        value={[config.mouseRepulsion]}
                        onValueChange={([value]) => updateConfig({ mouseRepulsion: value })}
                        max={20}
                        min={0}
                        step={0.1}
                        className="flex-1"
                      />
                      <Input
                        type="text"
                        value={config.mouseRepulsion.toFixed(1)}
                        onChange={(e) => {
                          const value = parseFloat(e.target.value);
                          if (!isNaN(value)) {
                            updateConfig({ mouseRepulsion: value });
                          }
                        }}
                        className="w-16 h-6 bg-secondary/30 text-xs text-center"
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Repulsion force from mouse cursor</p>
                  </div>


                  <div>
                    <Label className="text-xs text-muted-foreground">Random Seed</Label>
                    <Input
                      type="text"
                      value={config.randomSeed || ''}
                      onChange={(e) => {
                        const value = e.target.value;
                        const numValue = parseFloat(value);
                        updateConfig({ 
                          randomSeed: value === '' ? undefined : (!isNaN(numValue) ? numValue : value)
                        });
                      }}
                      className="h-8 bg-secondary/30 mt-1"
                      placeholder="Optional (number or string)"
                    />
                    <p className="text-xs text-muted-foreground mt-1">Controls layout randomness for reproducible results</p>
                  </div>

                  <Button variant="outline" className="w-full h-8" size="sm" onClick={handleResetToDefaults}>
                    <Shuffle className="h-3 w-3 mr-2" />
                    Reset to Defaults
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Rendering Tab */}
            <TabsContent value="render" className="mt-0 space-y-4">
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Settings2 className="h-4 w-4 text-primary" />
                    <span>Link & Background</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Link Width</Label>
                      <Badge variant="outline" className="text-xs">{config.linkWidth.toFixed(1)}</Badge>
                    </div>
                    <Slider
                      value={[config.linkWidth]}
                      onValueChange={([value]) => updateConfig({ linkWidth: value })}
                      max={5}
                      min={0.1}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground">Link Width Column</Label>
                    <Input
                      value={config.linkWidthBy}
                      onChange={(e) => updateConfig({ linkWidthBy: e.target.value })}
                      className="h-8 bg-secondary/30 mt-1"
                      placeholder="weight"
                    />
                    <p className="text-xs text-muted-foreground mt-1">Column name for link width values</p>
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Link Opacity</Label>
                      <Badge variant="outline" className="text-xs">{Math.round(config.linkOpacity * 100)}%</Badge>
                    </div>
                    <Slider
                      value={[config.linkOpacity * 100]}
                      onValueChange={([value]) => updateConfig({ linkOpacity: value / 100 })}
                      max={100}
                      min={0}
                      step={5}
                      className="w-full"
                    />
                  </div>

                  <ColorPicker
                    color={config.linkColor}
                    onChange={(color) => updateConfig({ linkColor: color })}
                    label="Link Color"
                    swatches={[
                      '#666666', '#ffffff', '#ff6b6b', '#4ecdc4', '#45b7d1',
                      '#96ceb4', '#ffeaa7', '#dda0dd', '#98d8c8', '#f7dc6f',
                      '#bb8fce', '#85c1e9', '#f8c471', '#82e0aa', '#adb5bd',
                      '#495057'
                    ]}
                  />

                  <ColorPicker
                    color={config.backgroundColor}
                    onChange={(color) => updateConfig({ backgroundColor: color })}
                    label="Background Color"
                    swatches={[
                      '#000000', '#0a0a0a', '#1a1a1a', '#2d3748', '#1a202c',
                      '#2a2a2a', '#0f172a', '#111827', '#1f2937', '#374151',
                      '#ffffff', '#f8f9fa', '#e9ecef', '#dee2e6'
                    ]}
                  />


                  {/* Link Color Schemes */}
                  <div>
                    <Label className="text-xs text-muted-foreground">Link Color Scheme</Label>
                    <Select 
                      value={config.linkColorScheme} 
                      onValueChange={(value) => updateConfig({ linkColorScheme: value })}
                    >
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="uniform">➖ Uniform Color</SelectItem>
                        <SelectItem value="by-weight">⚖️ By Edge Weight</SelectItem>
                        <SelectItem value="by-type">🔗 By Edge Type</SelectItem>
                        <SelectItem value="by-distance">📏 By Distance</SelectItem>
                        <SelectItem value="gradient">🌈 Node Color Gradient</SelectItem>
                        <SelectItem value="community">👥 By Community Bridge</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>

              {/* Hover & Focus Effects */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Eye className="h-4 w-4 text-primary" />
                    <span>Hover & Focus Effects</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Hover Cursor */}
                  <div>
                    <Label className="text-xs text-muted-foreground">Hover Cursor</Label>
                    <Select value={config.hoveredPointCursor} onValueChange={(value) => updateConfig({ hoveredPointCursor: value })}>
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="auto">↗️ Auto</SelectItem>
                        <SelectItem value="pointer">👆 Pointer</SelectItem>
                        <SelectItem value="crosshair">✛ Crosshair</SelectItem>
                        <SelectItem value="grab">✋ Grab</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Hover Ring Toggle */}
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Show Hover Ring</Label>
                    <Checkbox
                      checked={config.renderHoveredPointRing}
                      onCheckedChange={(checked) => updateConfig({ renderHoveredPointRing: checked })}
                    />
                  </div>

                  {/* Hover Ring Color */}
                  {config.renderHoveredPointRing && (
                    <div>
                      <Label className="text-xs text-muted-foreground">Hover Ring Color</Label>
                      <ColorPicker
                        color={config.hoveredPointRingColor}
                        onChange={(color) => updateConfig({ hoveredPointRingColor: color })}
                        swatches={[
                          '#22d3ee', '#06b6d4', '#0891b2', '#0e7490',
                          '#fbbf24', '#f59e0b', '#d97706', '#b45309',
                          '#ef4444', '#dc2626', '#b91c1c', '#991b1b',
                          '#10b981', '#059669', '#047857', '#065f46'
                        ]}
                      />
                    </div>
                  )}

                  {/* Focus Ring Color */}
                  <div>
                    <Label className="text-xs text-muted-foreground">Focus Ring Color</Label>
                    <ColorPicker
                      color={config.focusedPointRingColor}
                      onChange={(color) => updateConfig({ focusedPointRingColor: color })}
                      swatches={[
                        '#fbbf24', '#f59e0b', '#d97706', '#b45309',
                        '#22d3ee', '#06b6d4', '#0891b2', '#0e7490',
                        '#ef4444', '#dc2626', '#b91c1c', '#991b1b',
                        '#10b981', '#059669', '#047857', '#065f46'
                      ]}
                    />
                  </div>

                  {/* Render Links Toggle */}
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Show Links</Label>
                    <Checkbox
                      checked={config.renderLinks}
                      onCheckedChange={(checked) => updateConfig({ renderLinks: checked })}
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Fit View Configuration */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <ZoomIn className="h-4 w-4 text-primary" />
                    <span>Fit View Settings</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Animation Duration */}
                  <div>
                    <Label className="text-xs text-muted-foreground">Animation Duration (ms)</Label>
                    <div className="flex items-center space-x-2 mt-1">
                      <Slider
                        value={[config.fitViewDuration]}
                        onValueChange={([value]) => updateConfig({ fitViewDuration: value })}
                        min={0}
                        max={2000}
                        step={50}
                        className="flex-1"
                      />
                      <span className="text-xs text-muted-foreground w-12 text-right">
                        {config.fitViewDuration}
                      </span>
                    </div>
                  </div>

                  {/* Padding */}
                  <div>
                    <Label className="text-xs text-muted-foreground">Viewport Padding</Label>
                    <div className="flex items-center space-x-2 mt-1">
                      <Slider
                        value={[config.fitViewPadding * 100]}
                        onValueChange={([value]) => updateConfig({ fitViewPadding: value / 100 })}
                        min={0}
                        max={50}
                        step={1}
                        className="flex-1"
                      />
                      <span className="text-xs text-muted-foreground w-12 text-right">
                        {Math.round(config.fitViewPadding * 100)}%
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Link Visibility & Effects */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Eye className="h-4 w-4 text-primary" />
                    <span>Link Visibility</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Min Visibility Distance</Label>
                      <Badge variant="outline" className="text-xs">{config.linkVisibilityDistance[0]}px</Badge>
                    </div>
                    <Slider
                      value={[config.linkVisibilityDistance[0]]}
                      onValueChange={([value]) => updateConfig({ 
                        linkVisibilityDistance: [value, config.linkVisibilityDistance[1]] 
                      })}
                      max={200}
                      min={10}
                      step={10}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Max Visibility Distance</Label>
                      <Badge variant="outline" className="text-xs">{config.linkVisibilityDistance[1]}px</Badge>
                    </div>
                    <Slider
                      value={[config.linkVisibilityDistance[1]]}
                      onValueChange={([value]) => updateConfig({ 
                        linkVisibilityDistance: [config.linkVisibilityDistance[0], value] 
                      })}
                      max={500}
                      min={50}
                      step={10}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Min Transparency</Label>
                      <Badge variant="outline" className="text-xs">{Math.round(config.linkVisibilityMinTransparency * 100)}%</Badge>
                    </div>
                    <Slider
                      value={[config.linkVisibilityMinTransparency * 100]}
                      onValueChange={([value]) => updateConfig({ 
                        linkVisibilityMinTransparency: value / 100 
                      })}
                      max={100}
                      min={0}
                      step={5}
                      className="w-full"
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Show Link Arrows</Label>
                    <Checkbox 
                      checked={config.linkArrows}
                      onCheckedChange={(checked) => updateConfig({ linkArrows: !!checked })}
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Arrow Size Scale</Label>
                      <Badge variant="outline" className="text-xs">{config.linkArrowsSizeScale.toFixed(1)}x</Badge>
                    </div>
                    <Slider
                      value={[config.linkArrowsSizeScale]}
                      onValueChange={([value]) => updateConfig({ linkArrowsSizeScale: value })}
                      max={3}
                      min={0.1}
                      step={0.1}
                      className="w-full"
                    />
                  </div>
                </CardContent>
              </Card>

              {/* Curved Links */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-primary" />
                    <span>Curved Links</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Enable Curved Links</Label>
                    <Checkbox
                      checked={config.curvedLinks}
                      onCheckedChange={(checked) => updateConfig({ curvedLinks: !!checked })}
                    />
                  </div>

                  {config.curvedLinks && (
                    <>
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <Label className="text-xs text-muted-foreground">Curve Weight</Label>
                          <Badge variant="outline" className="text-xs">{config.curvedLinkWeight.toFixed(2)}</Badge>
                        </div>
                        <Slider
                          value={[config.curvedLinkWeight]}
                          onValueChange={([value]) => updateConfig({ curvedLinkWeight: value })}
                          max={1}
                          min={0}
                          step={0.05}
                          className="w-full"
                        />
                      </div>

                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <Label className="text-xs text-muted-foreground">Curve Segments</Label>
                          <Badge variant="outline" className="text-xs">{config.curvedLinkSegments}</Badge>
                        </div>
                        <Slider
                          value={[config.curvedLinkSegments]}
                          onValueChange={([value]) => updateConfig({ curvedLinkSegments: Math.round(value) })}
                          max={30}
                          min={5}
                          step={1}
                          className="w-full"
                        />
                      </div>

                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <Label className="text-xs text-muted-foreground">Control Point Distance</Label>
                          <Badge variant="outline" className="text-xs">{config.curvedLinkControlPointDistance.toFixed(2)}</Badge>
                        </div>
                        <Slider
                          value={[config.curvedLinkControlPointDistance]}
                          onValueChange={([value]) => updateConfig({ curvedLinkControlPointDistance: value })}
                          max={1}
                          min={0}
                          step={0.05}
                          className="w-full"
                        />
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Graph Layout Algorithms */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Layers className="h-4 w-4 text-primary" />
                    <span>Layout Algorithms</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">Force Layout Type</Label>
                    <Select value={config.layout} onValueChange={(value) => {
                      updateConfig({ layout: value });
                      onLayoutChange?.(value);
                    }}>
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="force-directed">🌊 Force-Directed</SelectItem>
                        <SelectItem value="hierarchical">🌳 Hierarchical</SelectItem>
                        <SelectItem value="circular">⭕ Circular</SelectItem>
                        <SelectItem value="radial">☀️ Radial</SelectItem>
                        <SelectItem value="cluster">📦 Cluster</SelectItem>
                        <SelectItem value="temporal">⏰ Temporal</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={() => {
                        console.log('Applying force-directed layout with data:', graphData?.nodes?.length, 'nodes');
                        if (graphData?.nodes && graphData?.edges) {
                          applyLayout('force-directed', {}, { nodes: graphData.nodes, edges: graphData.edges });
                        } else {
                          console.warn('No graph data available for layout');
                        }
                      }}
                    >
                      🌊 Spring
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={() => {
                        console.log('Applying circular layout with data:', graphData?.nodes?.length, 'nodes');
                        if (graphData?.nodes && graphData?.edges) {
                          applyLayout('circular', {}, { nodes: graphData.nodes, edges: graphData.edges });
                        } else {
                          console.warn('No graph data available for layout');
                        }
                      }}
                    >
                      ⭕ Circular
                    </Button>
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={() => {
                        console.log('Applying hierarchical layout with data:', graphData?.nodes?.length, 'nodes');
                        if (graphData?.nodes && graphData?.edges) {
                          applyLayout('hierarchical', {}, { nodes: graphData.nodes, edges: graphData.edges });
                        } else {
                          console.warn('No graph data available for layout');
                        }
                      }}
                    >
                      🌳 Tree
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8 text-xs"
                      onClick={() => {
                        console.log('Applying radial layout with data:', graphData?.nodes?.length, 'nodes');
                        if (graphData?.nodes && graphData?.edges) {
                          applyLayout('radial', {}, { nodes: graphData.nodes, edges: graphData.edges });
                        } else {
                          console.warn('No graph data available for layout');
                        }
                      }}
                    >
                      ☀️ Radial
                    </Button>
                  </div>

                  <Separator />

                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Enable Quadtree (Experimental)</Label>
                    <Checkbox 
                      checked={config.useQuadtree} 
                      onCheckedChange={(checked) => updateConfig({ useQuadtree: !!checked })}
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Quadtree Levels</Label>
                      <Badge variant="outline" className="text-xs">{config.quadtreeLevels}</Badge>
                    </div>
                    <Slider
                      value={[config.quadtreeLevels]}
                      onValueChange={([value]) => updateConfig({ quadtreeLevels: value })}
                      max={15}
                      min={5}
                      step={1}
                      className="w-full"
                    />
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

          </div>
        </Tabs>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Only re-render if collapsed state changes
  return prevProps.collapsed === nextProps.collapsed;
});