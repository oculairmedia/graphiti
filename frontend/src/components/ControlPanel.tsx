import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Database, Settings2, Palette, Zap, RotateCcw, Paintbrush, Layers, Eye } from 'lucide-react';
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

interface ControlPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
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
  onToggleCollapse 
}) => {
  const { config, updateConfig } = useGraphConfig();
  
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
      <div className="flex-1 overflow-hidden flex flex-col">
        <Tabs defaultValue="query" className="flex-1 flex flex-col">
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

          <div className="flex-1 overflow-y-auto custom-scrollbar px-4 pb-4">
            
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
                        <SelectItem value="entire_graph">Entire Graph</SelectItem>
                        <SelectItem value="high-degree">High Degree Nodes</SelectItem>
                        <SelectItem value="agent-networks">Agent Networks</SelectItem>
                        <SelectItem value="communities">Communities</SelectItem>
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

                  <div className="space-y-2">
                    <Button className="w-full h-8 bg-primary hover:bg-primary/90">
                      <Database className="h-3 w-3 mr-2" />
                      Visualize
                    </Button>
                    <Button variant="destructive" className="w-full h-8">
                      Load Entire Graph (GPU)
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
                    <div key={type.id} className="flex items-center justify-between space-x-3 p-3 rounded-lg border border-border/30">
                      <div className="flex items-center space-x-3 flex-1">
                        <Checkbox
                          checked={config.nodeTypeVisibility[type.id as keyof typeof config.nodeTypeVisibility]}
                          onCheckedChange={(checked) => 
                            handleNodeTypeVisibilityChange(type.id, !!checked)
                          }
                        />
                        <div className="flex items-center space-x-2 flex-1">
                          <div 
                            className="w-4 h-4 rounded-full border border-border/30"
                            style={{ backgroundColor: config.nodeTypeColors[type.id as keyof typeof config.nodeTypeColors] }}
                          />
                          <span className="text-sm font-medium">{type.name}</span>
                        </div>
                      </div>
                      <div className="flex items-center space-x-2">
                        <Badge variant="outline" className="text-xs">
                          {type.count.toLocaleString()}
                        </Badge>
                        <Input
                          type="color"
                          value={config.nodeTypeColors[type.id as keyof typeof config.nodeTypeColors]}
                          onChange={(e) => handleNodeTypeColorChange(type.id, e.target.value)}
                          className="w-8 h-8 p-0 border-0 bg-transparent cursor-pointer"
                        />
                      </div>
                    </div>
                  ))}
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

                        <div className="flex items-center justify-between">
                          <Label className="text-xs text-muted-foreground">Label Color</Label>
                          <Input
                            type="color"
                            value={config.labelColor}
                            onChange={(e) => updateConfig({ labelColor: e.target.value })}
                            className="w-8 h-8 p-0 border-0 bg-transparent cursor-pointer"
                          />
                        </div>
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

                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Link Color</Label>
                    <Input
                      type="color"
                      value={config.linkColor}
                      onChange={(e) => updateConfig({ linkColor: e.target.value })}
                      className="w-8 h-8 p-0 border-0 bg-transparent cursor-pointer"
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Background</Label>
                    <Input
                      type="color"
                      value={config.backgroundColor}
                      onChange={(e) => updateConfig({ backgroundColor: e.target.value })}
                      className="w-8 h-8 p-0 border-0 bg-transparent cursor-pointer"
                    />
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground">Color Scheme</Label>
                    <Select value={config.colorScheme} onValueChange={(value) => updateConfig({ colorScheme: value })}>
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="by-type">By Node Type</SelectItem>
                        <SelectItem value="by-centrality">By Centrality</SelectItem>
                        <SelectItem value="by-pagerank">By PageRank</SelectItem>
                        <SelectItem value="by-degree">By Degree</SelectItem>
                        <SelectItem value="by-community">By Community</SelectItem>
                        <SelectItem value="custom">Custom Colors</SelectItem>
                      </SelectContent>
                    </Select>
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