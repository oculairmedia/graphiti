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

interface ControlPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({ 
  collapsed, 
  onToggleCollapse 
}) => {
  const [queryType, setQueryType] = useState('entire');
  const [nodeLimit, setNodeLimit] = useState('1000');
  
  // Basic rendering controls
  const [linkWidth, setLinkWidth] = useState([1.5]);
  const [linkOpacity, setLinkOpacity] = useState([80]);
  const [linkColor, setLinkColor] = useState('#4a5568');
  const [backgroundColor, setBackgroundColor] = useState('#1a202c');
  
  // Physics controls
  const [gravity, setGravity] = useState([0.3]);
  const [repulsion, setRepulsion] = useState([1.2]);
  const [centerForce, setCenterForce] = useState([0.1]);
  const [friction, setFriction] = useState([0.85]);
  const [linkSpring, setLinkSpring] = useState([1.0]);
  const [linkDistance, setLinkDistance] = useState([30]);
  const [mouseRepulsion, setMouseRepulsion] = useState([20]);
  const [simulationDecay, setSimulationDecay] = useState([3000]);
  
  // Node sizing and scaling
  const [sizeMapping, setSizeMapping] = useState('degree');
  const [minNodeSize, setMinNodeSize] = useState([3]);
  const [maxNodeSize, setMaxNodeSize] = useState([12]);
  const [sizeMultiplier, setSizeMultiplier] = useState([1.0]);
  const [nodeOpacity, setNodeOpacity] = useState([90]);
  const [borderWidth, setBorderWidth] = useState([0]);
  
  // Color scheme and node type colors
  const [colorScheme, setColorScheme] = useState('by-type');
  const [nodeTypeColors, setNodeTypeColors] = useState({
    Entity: '#4ECDC4',
    Episodic: '#B794F6', 
    Agent: '#F6AD55',
    Community: '#90CDF4'
  });
  const [nodeTypeVisibility, setNodeTypeVisibility] = useState({
    Entity: true,
    Episodic: true,
    Agent: true,
    Community: true
  });
  
  // Label controls
  const [showLabels, setShowLabels] = useState(true);
  const [labelSize, setLabelSize] = useState([12]);
  const [labelOpacity, setLabelOpacity] = useState([80]);
  const [labelColor, setLabelColor] = useState('#ffffff');

  // Node type definitions
  const nodeTypes = [
    { id: 'Entity', name: 'Entity', count: 2847 },
    { id: 'Episodic', name: 'Episodic', count: 1024 },
    { id: 'Agent', name: 'Agent', count: 892 },
    { id: 'Community', name: 'Community', count: 156 }
  ];

  const handleNodeTypeColorChange = (type: string, color: string) => {
    setNodeTypeColors(prev => ({ ...prev, [type]: color }));
  };

  const handleNodeTypeVisibilityChange = (type: string, visible: boolean) => {
    setNodeTypeVisibility(prev => ({ ...prev, [type]: visible }));
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
                    <Select value={queryType} onValueChange={setQueryType}>
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="entire">Entire Graph</SelectItem>
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
                      value={nodeLimit}
                      onChange={(e) => setNodeLimit(e.target.value)}
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
                          checked={nodeTypeVisibility[type.id as keyof typeof nodeTypeVisibility]}
                          onCheckedChange={(checked) => 
                            handleNodeTypeVisibilityChange(type.id, !!checked)
                          }
                        />
                        <div className="flex items-center space-x-2 flex-1">
                          <div 
                            className="w-4 h-4 rounded-full border border-border/30"
                            style={{ backgroundColor: nodeTypeColors[type.id as keyof typeof nodeTypeColors] }}
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
                          value={nodeTypeColors[type.id as keyof typeof nodeTypeColors]}
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
                    <Select value={sizeMapping} onValueChange={setSizeMapping}>
                      <SelectTrigger className="h-8 bg-secondary/30">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="glass">
                        <SelectItem value="uniform">Uniform Size</SelectItem>
                        <SelectItem value="degree">Degree Centrality</SelectItem>
                        <SelectItem value="betweenness">Betweenness Centrality</SelectItem>
                        <SelectItem value="pagerank">PageRank Score</SelectItem>
                        <SelectItem value="eigenvector">Eigenvector Centrality</SelectItem>
                        <SelectItem value="connections">Connection Count</SelectItem>
                        <SelectItem value="custom">Custom Property</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <Label className="text-xs text-muted-foreground">Min Size</Label>
                        <Badge variant="outline" className="text-xs">{minNodeSize[0]}px</Badge>
                      </div>
                      <Slider
                        value={minNodeSize}
                        onValueChange={setMinNodeSize}
                        max={10}
                        min={1}
                        step={1}
                        className="w-full"
                      />
                    </div>
                    <div>
                      <div className="flex justify-between items-center mb-2">
                        <Label className="text-xs text-muted-foreground">Max Size</Label>
                        <Badge variant="outline" className="text-xs">{maxNodeSize[0]}px</Badge>
                      </div>
                      <Slider
                        value={maxNodeSize}
                        onValueChange={setMaxNodeSize}
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
                      <Badge variant="outline" className="text-xs">{sizeMultiplier[0]}x</Badge>
                    </div>
                    <Slider
                      value={sizeMultiplier}
                      onValueChange={setSizeMultiplier}
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
                      <Badge variant="outline" className="text-xs">{nodeOpacity[0]}%</Badge>
                    </div>
                    <Slider
                      value={nodeOpacity}
                      onValueChange={setNodeOpacity}
                      max={100}
                      min={10}
                      step={5}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Border Width</Label>
                      <Badge variant="outline" className="text-xs">{borderWidth[0]}px</Badge>
                    </div>
                    <Slider
                      value={borderWidth}
                      onValueChange={setBorderWidth}
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
                        checked={showLabels}
                        onCheckedChange={(checked) => setShowLabels(!!checked)}
                      />
                    </div>
                    
                    {showLabels && (
                      <>
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <Label className="text-xs text-muted-foreground">Label Size</Label>
                            <Badge variant="outline" className="text-xs">{labelSize[0]}px</Badge>
                          </div>
                          <Slider
                            value={labelSize}
                            onValueChange={setLabelSize}
                            max={24}
                            min={8}
                            step={1}
                            className="w-full"
                          />
                        </div>

                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <Label className="text-xs text-muted-foreground">Label Opacity</Label>
                            <Badge variant="outline" className="text-xs">{labelOpacity[0]}%</Badge>
                          </div>
                          <Slider
                            value={labelOpacity}
                            onValueChange={setLabelOpacity}
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
                            value={labelColor}
                            onChange={(e) => setLabelColor(e.target.value)}
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
                      <Badge variant="outline" className="text-xs">{gravity[0]}</Badge>
                    </div>
                    <Slider
                      value={gravity}
                      onValueChange={setGravity}
                      max={1}
                      min={0}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Repulsion Force</Label>
                      <Badge variant="outline" className="text-xs">{repulsion[0]}</Badge>
                    </div>
                    <Slider
                      value={repulsion}
                      onValueChange={setRepulsion}
                      max={2}
                      min={0}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Center Force</Label>
                      <Badge variant="outline" className="text-xs">{centerForce[0]}</Badge>
                    </div>
                    <Slider
                      value={centerForce}
                      onValueChange={setCenterForce}
                      max={0.5}
                      min={0}
                      step={0.01}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Friction/Drag</Label>
                      <Badge variant="outline" className="text-xs">{friction[0]}</Badge>
                    </div>
                    <Slider
                      value={friction}
                      onValueChange={setFriction}
                      max={0.99}
                      min={0.5}
                      step={0.01}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Link Spring</Label>
                      <Badge variant="outline" className="text-xs">{linkSpring[0]}</Badge>
                    </div>
                    <Slider
                      value={linkSpring}
                      onValueChange={setLinkSpring}
                      max={2}
                      min={0}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Link Distance</Label>
                      <Badge variant="outline" className="text-xs">{linkDistance[0]}px</Badge>
                    </div>
                    <Slider
                      value={linkDistance}
                      onValueChange={setLinkDistance}
                      max={100}
                      min={5}
                      step={5}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Mouse Repulsion</Label>
                      <Badge variant="outline" className="text-xs">{mouseRepulsion[0]}px</Badge>
                    </div>
                    <Slider
                      value={mouseRepulsion}
                      onValueChange={setMouseRepulsion}
                      max={40}
                      min={1}
                      step={1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Simulation Decay</Label>
                      <Badge variant="outline" className="text-xs">{simulationDecay[0]}ms</Badge>
                    </div>
                    <Slider
                      value={simulationDecay}
                      onValueChange={setSimulationDecay}
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
                      <Badge variant="outline" className="text-xs">{linkWidth[0]}</Badge>
                    </div>
                    <Slider
                      value={linkWidth}
                      onValueChange={setLinkWidth}
                      max={5}
                      min={0.1}
                      step={0.1}
                      className="w-full"
                    />
                  </div>

                  <div>
                    <div className="flex justify-between items-center mb-2">
                      <Label className="text-xs text-muted-foreground">Link Opacity</Label>
                      <Badge variant="outline" className="text-xs">{linkOpacity[0]}%</Badge>
                    </div>
                    <Slider
                      value={linkOpacity}
                      onValueChange={setLinkOpacity}
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
                      value={linkColor}
                      onChange={(e) => setLinkColor(e.target.value)}
                      className="w-8 h-8 p-0 border-0 bg-transparent cursor-pointer"
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">Background</Label>
                    <Input
                      type="color"
                      value={backgroundColor}
                      onChange={(e) => setBackgroundColor(e.target.value)}
                      className="w-8 h-8 p-0 border-0 bg-transparent cursor-pointer"
                    />
                  </div>

                  <div>
                    <Label className="text-xs text-muted-foreground">Color Scheme</Label>
                    <Select value={colorScheme} onValueChange={setColorScheme}>
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
            </TabsContent>

          </div>
        </Tabs>
      </div>
    </div>
  );
};