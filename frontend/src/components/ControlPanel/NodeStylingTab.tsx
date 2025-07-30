import React from 'react';
import { Palette, Layers } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { ColorPicker } from '@/components/ui/ColorPicker';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { useColorUtils } from '@/hooks/useColorUtils';
import { generateNodeTypeColor } from '@/contexts/GraphConfigContext';

interface NodeType {
  id: string;
  name: string;
  count: number;
}

interface NodeStylingTabProps {
  config: {
    nodeTypeColors: Record<string, string>;
    nodeTypeVisibility: Record<string, boolean>;
    colorScheme: string;
    gradientHighColor: string;
    gradientLowColor: string;
    sizeMapping: string;
    minNodeSize: number;
    maxNodeSize: number;
    sizeMultiplier: number;
  };
  nodeTypes: NodeType[];
  onNodeTypeColorChange: (type: string, color: string) => void;
  onNodeTypeVisibilityChange: (type: string, visible: boolean) => void;
  onConfigUpdate: (updates: Record<string, unknown>) => void;
}

export const NodeStylingTab: React.FC<NodeStylingTabProps> = ({
  config,
  nodeTypes,
  onNodeTypeColorChange,
  onNodeTypeVisibilityChange,
  onConfigUpdate,
}) => {
  const { hexToHsl } = useColorUtils();

  return (
    <div className="space-y-4">
      {/* Node Type Colors & Visibility */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Palette className="h-4 w-4 text-primary" />
            <span>Node Types</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {nodeTypes.map((type, index) => {
            const actualColor = config.nodeTypeColors[type.id] || generateNodeTypeColor(type.id, index);
            
            return (
              <div key={type.id} className="space-y-2 p-3 rounded-lg border border-border/30">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <Checkbox
                      checked={config.nodeTypeVisibility[type.id] !== false}
                      onCheckedChange={(checked) => 
                        onNodeTypeVisibilityChange(type.id, !!checked)
                      }
                    />
                    <div className="flex items-center space-x-2">
                      <div 
                        className="w-4 h-4 rounded-full border border-border/30 control-color-indicator"
                        style={{
                          '--indicator-color': hexToHsl(actualColor)
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
                  color={actualColor}
                  onChange={(color) => onNodeTypeColorChange(type.id, color)}
                  className="w-full"
                />
              </div>
            );
          })}
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
            <Select value={config.colorScheme} onValueChange={(value) => onConfigUpdate({ colorScheme: value })}>
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
                    onChange={(color) => onConfigUpdate({ gradientHighColor: color })}
                    label="High Value Color"
                    className="w-full"
                    swatches={['#FF6B6B', '#FF4757', '#FF3838', '#FF6348', '#FF9F43', '#F39C12', '#E74C3C', '#C0392B']}
                  />
                  <ColorPicker
                    color={config.gradientLowColor}
                    onChange={(color) => onConfigUpdate({ gradientLowColor: color })}
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
            <Select value={config.sizeMapping} onValueChange={(value) => onConfigUpdate({ sizeMapping: value })}>
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
                onValueChange={([value]) => onConfigUpdate({ minNodeSize: value })}
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
                onValueChange={([value]) => onConfigUpdate({ maxNodeSize: value })}
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
              onValueChange={([value]) => onConfigUpdate({ sizeMultiplier: value })}
              max={3}
              min={0.1}
              step={0.1}
              className="w-full"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
};