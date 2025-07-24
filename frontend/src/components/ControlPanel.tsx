import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Database, Settings2, Palette, Zap, RotateCcw, Paintbrush, Layers, Eye, RefreshCw, Cpu } from 'lucide-react';
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

interface ControlPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onLayoutChange?: (layout: string) => void;
}

// Memoized node type definitions to prevent re-creation on every render
const NODE_TYPES = [
  { id: 'Entity', name: 'Entity', count: 2847 },
  { id: 'Episodic', name: 'Episodic', count: 1024 },
  { id: 'Agent', name: 'Agent', count: 892 },
  { id: 'Community', name: 'Community', count: 156 }
] as const;

export const ControlPanel: React.FC<ControlPanelProps> = React.memo(({ 
  collapsed, 
  onToggleCollapse,
  onLayoutChange
}) => {
  const { config, updateConfig, applyLayout } = useGraphConfig();
  
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
  
  const nodeTypes = NODE_TYPES;

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

  const handleRefreshGraph = async () => {
    setIsRefreshing(true);
    try {
      // Invalidate the graph data query to force a refresh
      await queryClient.invalidateQueries({ 
        queryKey: ['graphData', config.queryType, config.nodeLimit] 
      });
    } catch (error) {
      console.error('Error refreshing graph:', error);
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleQuickQuery = async (queryType: string, limit: number) => {
    updateConfig({ queryType, nodeLimit: limit });
    // Small delay to let config update, then refresh
    setTimeout(() => {
      handleRefreshGraph();
    }, 100);
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
                              className="w-4 h-4 rounded-full border border-border/30"
                              style={{ backgroundColor: config.nodeTypeColors[type.id as keyof typeof config.nodeTypeColors] }}
                            />
                            <span className="text-sm font-medium">{type.name}</span>
                          </div>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {type.count.toLocaleString()}
                        </Badge>
                      </div>
                      <ColorPicker
                        value={config.nodeTypeColors[type.id as keyof typeof config.nodeTypeColors]}
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
                            value={config.gradientHighColor}
                            onChange={(color) => updateConfig({ gradientHighColor: color })}
                            label="High Value Color"
                            className="w-full"
                            presets={['#FF6B6B', '#FF4757', '#FF3838', '#FF6348', '#FF9F43', '#F39C12', '#E74C3C', '#C0392B']}
                          />
                          <ColorPicker
                            value={config.gradientLowColor}
                            onChange={(color) => updateConfig({ gradientLowColor: color })}
                            label="Low Value Color"
                            className="w-full"
                            presets={['#4ECDC4', '#00D2D3', '#17A2B8', '#3498DB', '#2980B9', '#5DADE2', '#AED6F1', '#EBF5FB']}
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

              {/* Node Appearance */}
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Eye className="h-4 w-4 text-primary" />
                    <span>Appearance</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Node Opacity</Label>
                      <Badge variant="outline" className="text-xs">{config.nodeOpacity}%</Badge>
                    </div>
                    <Slider
                      value={[config.nodeOpacity]}
                      onValueChange={([value]) => updateConfig({ nodeOpacity: value })}
                      max={100}
                      min={10}
                      step={5}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Border Width</Label>
                      <Badge variant="outline" className="text-xs">{config.borderWidth}px</Badge>
                    </div>
                    <Slider
                      value={[config.borderWidth]}
                      onValueChange={([value]) => updateConfig({ borderWidth: value })}
                      max={5}
                      min={0}
                      step={0.5}
                      className="w-full"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs text-muted-foreground">Show Labels</Label>
                      <Checkbox
                        checked={config.showLabels}
                        onCheckedChange={(checked) => updateConfig({ showLabels: !!checked })}
                      />
                    </div>
                    
                    {config.showLabels && (
                      <>
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <Label className="text-xs text-muted-foreground">Label Size</Label>
                            <Badge variant="outline" className="text-xs">{config.labelSize}px</Badge>
                          </div>
                          <Slider
                            value={[config.labelSize]}
                            onValueChange={([value]) => updateConfig({ labelSize: value })}
                            max={24}
                            min={8}
                            step={1}
                            className="w-full"
                          />
                        </div>

                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <Label className="text-xs text-muted-foreground">Label Opacity</Label>
                            <Badge variant="outline" className="text-xs">{config.labelOpacity}%</Badge>
                          </div>
                          <Slider
                            value={[config.labelOpacity]}
                            onValueChange={([value]) => updateConfig({ labelOpacity: value })}
                            max={100}
                            min={0}
                            step={5}
                            className="w-full"
                          />
                        </div>

                        <ColorPicker
                          value={config.labelColor}
                          onChange={(color) => updateConfig({ labelColor: color })}
                          label="Label Color"
                        />
                      </>
                    )}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Physics Tab */}
            <TabsContent value="physics" className="mt-0 space-y-4">
              <Card className="glass border-border/30">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center space-x-2">
                    <Zap className="h-4 w-4 text-primary" />
                    <span>Force Simulation</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Gravity</Label>
                      <Badge variant="outline" className="text-xs">{config.gravity.toFixed(1)}</Badge>
                    </div>
                    <Slider
                      value={[config.gravity]}
                      onValueChange={([value]) => updateConfig({ gravity: value })}
                      max={1}
                      min={0}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Repulsion Force</Label>
                      <Badge variant="outline" className="text-xs">{config.repulsion.toFixed(1)}</Badge>
                    </div>
                    <Slider
                      value={[config.repulsion]}
                      onValueChange={([value]) => updateConfig({ repulsion: value })}
                      max={2}
                      min={0}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Center Force</Label>
                      <Badge variant="outline" className="text-xs">{config.centerForce.toFixed(2)}</Badge>
                    </div>
                    <Slider
                      value={[config.centerForce]}
                      onValueChange={([value]) => updateConfig({ centerForce: value })}
                      max={0.5}
                      min={0}
                      step={0.01}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Friction/Drag</Label>
                      <Badge variant="outline" className="text-xs">{config.friction.toFixed(2)}</Badge>
                    </div>
                    <Slider
                      value={[config.friction]}
                      onValueChange={([value]) => updateConfig({ friction: value })}
                      max={0.99}
                      min={0.5}
                      step={0.01}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Link Spring</Label>
                      <Badge variant="outline" className="text-xs">{config.linkSpring.toFixed(1)}</Badge>
                    </div>
                    <Slider
                      value={[config.linkSpring]}
                      onValueChange={([value]) => updateConfig({ linkSpring: value })}
                      max={2}
                      min={0}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Link Distance</Label>
                      <Badge variant="outline" className="text-xs">{config.linkDistance}px</Badge>
                    </div>
                    <Slider
                      value={[config.linkDistance]}
                      onValueChange={([value]) => updateConfig({ linkDistance: value })}
                      max={100}
                      min={5}
                      step={5}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Mouse Repulsion</Label>
                      <Badge variant="outline" className="text-xs">{config.mouseRepulsion}px</Badge>
                    </div>
                    <Slider
                      value={[config.mouseRepulsion]}
                      onValueChange={([value]) => updateConfig({ mouseRepulsion: value })}
                      max={40}
                      min={1}
                      step={1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Simulation Decay</Label>
                      <Badge variant="outline" className="text-xs">{config.simulationDecay}ms</Badge>
                    </div>
                    <Slider
                      value={[config.simulationDecay]}
                      onValueChange={([value]) => updateConfig({ simulationDecay: value })}
                      max={10000}
                      min={100}
                      step={100}
                      className="w-full"
                    />
                  </div>

                  <Button variant="outline" className="w-full h-8" size="sm">
                    <RotateCcw className="h-3 w-3 mr-2" />
                    Reset Physics
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
                    value={config.linkColor}
                    onChange={(color) => updateConfig({ linkColor: color })}
                    label="Link Color"
                    presets={[
                      '#666666', '#ffffff', '#ff6b6b', '#4ecdc4', '#45b7d1',
                      '#96ceb4', '#ffeaa7', '#dda0dd', '#98d8c8', '#f7dc6f',
                      '#bb8fce', '#85c1e9', '#f8c471', '#82e0aa', '#adb5bd',
                      '#495057'
                    ]}
                  />

                  <ColorPicker
                    value={config.backgroundColor}
                    onChange={(color) => updateConfig({ backgroundColor: color })}
                    label="Background Color"
                    presets={[
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