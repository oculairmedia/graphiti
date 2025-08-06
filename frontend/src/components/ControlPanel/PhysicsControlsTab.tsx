import React from 'react';
import { Zap, RotateCcw, Activity, Square } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { ControlSlider } from '@/components/ui/ControlSlider';
import { ControlGroup } from '@/components/ui/ControlGroup';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface PhysicsControlsTabProps {
  config: {
    repulsion: number;
    simulationRepulsionTheta: number;
    linkSpring: number;
    linkDistance: number;
    linkDistRandomVariationRange: [number, number];
    gravity: number;
    centerForce: number;
    friction: number;
    simulationDecay: number;
    simulationCluster: number;
    mouseRepulsion: number;
    disableSimulation: boolean | null;
    clusteringEnabled: boolean;
    pointClusterBy: string;
    pointClusterStrengthBy: string;
    clusteringMethod: 'nodeType' | 'centrality' | 'custom' | 'none';
    centralityMetric: 'degree' | 'pagerank' | 'betweenness' | 'eigenvector';
    clusterStrength: number;
  };
  onConfigUpdate: (updates: Record<string, unknown>) => void;
  onResetToDefaults: () => void;
}

export const PhysicsControlsTab: React.FC<PhysicsControlsTabProps> = ({
  config,
  onConfigUpdate,
  onResetToDefaults,
}) => {
  return (
    <div className="space-y-4">
      {/* Force Configuration */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Zap className="h-4 w-4 text-primary" />
            <span>Force Configuration</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ControlSlider
            label="Repulsion Force"
            value={config.repulsion}
            min={0}
            max={10}
            step={0.01}
            onChange={(value) => onConfigUpdate({ repulsion: value })}
            icon={<Zap className="h-3 w-3" />}
          />
          <p className="text-xs text-muted-foreground -mt-2">Controls node repulsion strength</p>

          <ControlSlider
            label="Repulsion Theta"
            value={config.simulationRepulsionTheta}
            min={0.3}
            max={2}
            step={0.1}
            onChange={(value) => onConfigUpdate({ simulationRepulsionTheta: value })}
          />
          <p className="text-xs text-muted-foreground -mt-2">Barnes-Hut approximation level (higher = more accurate)</p>

          <ControlSlider
            label="Link Spring Force"
            value={config.linkSpring}
            min={0}
            max={5}
            step={0.01}
            onChange={(value) => onConfigUpdate({ linkSpring: value })}
          />
          <p className="text-xs text-muted-foreground -mt-2">Attraction strength between connected nodes</p>

          <ControlSlider
            label="Link Distance"
            value={config.linkDistance}
            min={0.1}
            max={20}
            step={0.1}
            onChange={(value) => onConfigUpdate({ linkDistance: value })}
            formatValue={(v) => v.toFixed(1)}
          />
          <p className="text-xs text-muted-foreground -mt-2">Minimum distance between linked nodes</p>

          {/* Link Distance Random Variation */}
          <ControlGroup title="Link Distance Variation" variant="plain">
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <span className="text-xs text-muted-foreground w-8">Min:</span>
                <ControlSlider
                  label=""
                  value={config.linkDistRandomVariationRange[0]}
                  min={0.5}
                  max={2}
                  step={0.1}
                  onChange={(value) => onConfigUpdate({ 
                    linkDistRandomVariationRange: [value, config.linkDistRandomVariationRange[1]] 
                  })}
                  showInput={false}
                  formatValue={(v) => v.toFixed(1)}
                  className="flex-1"
                />
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-xs text-muted-foreground w-8">Max:</span>
                <ControlSlider
                  label=""
                  value={config.linkDistRandomVariationRange[1]}
                  min={0.5}
                  max={3}
                  step={0.1}
                  onChange={(value) => onConfigUpdate({ 
                    linkDistRandomVariationRange: [config.linkDistRandomVariationRange[0], value] 
                  })}
                  showInput={false}
                  formatValue={(v) => v.toFixed(1)}
                  className="flex-1"
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground mt-1">Random variation range for link distances</p>
          </ControlGroup>

          <ControlSlider
            label="Gravity Force"
            value={config.gravity}
            min={0}
            max={2}
            step={0.01}
            onChange={(value) => onConfigUpdate({ gravity: value })}
          />
          <p className="text-xs text-muted-foreground -mt-2">Attraction towards graph center</p>

          <ControlSlider
            label="Center Force"
            value={config.centerForce}
            min={0}
            max={5}
            step={0.01}
            onChange={(value) => onConfigUpdate({ centerForce: value })}
          />
          <p className="text-xs text-muted-foreground -mt-2">Centering force strength</p>
        </CardContent>
      </Card>

      {/* Simulation Control */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Activity className="h-4 w-4 text-primary" />
            <span>Simulation Control</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ControlSlider
            label="Friction"
            value={config.friction}
            min={0}
            max={1}
            step={0.01}
            onChange={(value) => onConfigUpdate({ friction: value })}
          />
          <p className="text-xs text-muted-foreground -mt-2">Speed damping (0 = no friction, 1 = high friction)</p>

          <ControlSlider
            label="Simulation Decay"
            value={config.simulationDecay}
            min={0}
            max={10000}
            step={100}
            onChange={(value) => onConfigUpdate({ simulationDecay: value })}
            formatValue={(v) => v.toString()}
          />
          <p className="text-xs text-muted-foreground -mt-2">Force decay rate over time</p>

          <div className="flex items-center space-x-2 p-3 rounded-lg bg-secondary/20 border border-border/30">
            <Checkbox
              checked={config.clusteringEnabled}
              onCheckedChange={(checked) => 
                onConfigUpdate({ clusteringEnabled: checked as boolean })
              }
            />
            <Label className="text-sm cursor-pointer">
              <Activity className="inline-block h-3 w-3 mr-1" />
              Enable Clustering
            </Label>
          </div>
          {config.clusteringEnabled && (
            <>
              <div className="space-y-2">
                <Label className="text-sm">Clustering Method</Label>
                <Select
                  value={config.clusteringMethod}
                  onValueChange={(value) => onConfigUpdate({ clusteringMethod: value })}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="nodeType">By Node Type</SelectItem>
                    <SelectItem value="centrality">By Centrality</SelectItem>
                    <SelectItem value="custom">Custom</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {config.clusteringMethod === 'centrality' && (
                <div className="space-y-2">
                  <Label className="text-sm">Centrality Metric</Label>
                  <Select
                    value={config.centralityMetric}
                    onValueChange={(value) => onConfigUpdate({ centralityMetric: value })}
                  >
                    <SelectTrigger className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="degree">Degree</SelectItem>
                      <SelectItem value="pagerank">PageRank</SelectItem>
                      <SelectItem value="betweenness">Betweenness</SelectItem>
                      <SelectItem value="eigenvector">Eigenvector</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              <ControlSlider
                label="Cluster Strength"
                value={config.clusterStrength}
                min={0}
                max={1}
                step={0.01}
                onChange={(value) => onConfigUpdate({ clusterStrength: value })}
                formatValue={(v) => (v * 100).toFixed(0) + '%'}
              />
              <p className="text-xs text-muted-foreground -mt-2">
                Strength of attraction to cluster centers
              </p>
            </>
          )}

          <ControlSlider
            label="Simulation Cluster Force"
            value={config.simulationCluster}
            min={0}
            max={5}
            step={0.01}
            onChange={(value) => onConfigUpdate({ simulationCluster: value })}
            disabled={!config.clusteringEnabled}
          />
          <p className="text-xs text-muted-foreground -mt-2">Overall clustering force in simulation</p>

          <ControlSlider
            label="Mouse Repulsion"
            value={config.mouseRepulsion}
            min={0}
            max={10}
            step={0.1}
            onChange={(value) => onConfigUpdate({ mouseRepulsion: value })}
            formatValue={(v) => v.toFixed(1)}
          />
          <p className="text-xs text-muted-foreground -mt-2">Node repulsion from mouse cursor</p>

          <div className="flex items-center space-x-2 p-3 rounded-lg bg-secondary/20 border border-border/30">
            <Checkbox
              checked={config.disableSimulation === true}
              onCheckedChange={(checked) => 
                onConfigUpdate({ disableSimulation: checked ? true : null })
              }
            />
            <Label className="text-sm cursor-pointer">
              <Square className="inline-block h-3 w-3 mr-1" />
              Disable Simulation
            </Label>
          </div>
          {config.disableSimulation && (
            <p className="text-xs text-muted-foreground">
              Physics simulation is disabled. Nodes will remain static.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Presets & Actions */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <RotateCcw className="h-4 w-4 text-primary" />
            <span>Presets & Actions</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button 
            className="w-full h-8" 
            variant="outline"
            onClick={onResetToDefaults}
          >
            <RotateCcw className="h-3 w-3 mr-2" />
            Reset to Defaults
          </Button>
          
          <div className="grid grid-cols-2 gap-2">
            <Button 
              variant="outline" 
              size="sm" 
              className="h-8 text-xs"
              onClick={() => onConfigUpdate({ 
                repulsion: 0.5, 
                linkSpring: 2.0,
                gravity: 0.1 
              })}
            >
              🎯 Tight Clustering
            </Button>
            <Button 
              variant="outline" 
              size="sm" 
              className="h-8 text-xs"
              onClick={() => onConfigUpdate({ 
                repulsion: 2.0, 
                linkSpring: 0.5,
                gravity: 0 
              })}
            >
              💫 Spread Layout
            </Button>
          </div>
          
          <Button 
            variant="outline" 
            size="sm" 
            className="w-full h-8 text-xs"
            onClick={() => onConfigUpdate({ 
              friction: 0.95,
              simulationDecay: 5000,
              disableSimulation: null
            })}
          >
            🌊 Smooth Animation
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};