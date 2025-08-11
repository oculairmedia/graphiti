import React, { useState, useMemo, useOptimistic, useTransition } from 'react';
import { X, Filter, Calendar, TrendingUp, Tag, Link2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useGraphConfig } from '../contexts/GraphConfigProvider';
import type { GraphData } from '../types/graph';

interface FilterPanelProps {
  isOpen: boolean;
  onClose: () => void;
  data?: GraphData;
}

export const FilterPanel: React.FC<FilterPanelProps> = ({ 
  isOpen, 
  onClose,
  data
}) => {
  const { config, updateConfig } = useGraphConfig();
  
  // React 19 performance features
  const [isPending, startTransition] = useTransition();
  
  // Optimistic state for immediate UI feedback
  const [optimisticConfig, setOptimisticConfig] = useOptimistic(
    config,
    (state, newConfig: typeof config) => ({ ...state, ...newConfig })
  );
  
  // Compute real node type statistics from actual data
  const nodeTypeStats = useMemo(() => {
    if (!data?.nodes) return [];
    
    const typeCount: Record<string, number> = {};
    data.nodes.forEach(node => {
      const type = node.node_type || 'Unknown';
      typeCount[type] = (typeCount[type] || 0) + 1;
    });

    return Object.entries(typeCount).map(([type, count]) => ({
      id: type,
      label: type,
      color: {
        'Entity': 'bg-node-entity',
        'Episodic': 'bg-node-episodic',
        'Agent': 'bg-node-agent',
        'Community': 'bg-node-community'
      }[type] || 'bg-primary',
      count
    }));
  }, [data?.nodes]);
  
  // Local state for temporary filter values before applying
  const [tempFilters, setTempFilters] = useState({
    selectedTypes: config.filteredNodeTypes,
    degreeRange: [config.minDegree, config.maxDegree],
    pagerankRange: [config.minPagerank, config.maxPagerank],
    betweennessRange: [config.minBetweenness, config.maxBetweenness],
    eigenvectorRange: [config.minEigenvector, config.maxEigenvector],
    minConnections: config.minConnections.toString(),
    maxConnections: config.maxConnections.toString(),
    dateRange: { start: config.startDate, end: config.endDate }
  });
  
  // Sync tempFilters with config changes when modal opens
  React.useEffect(() => {
    if (isOpen) {
      setTempFilters({
        selectedTypes: config.filteredNodeTypes,
        degreeRange: [config.minDegree, config.maxDegree],
        pagerankRange: [config.minPagerank, config.maxPagerank],
        betweennessRange: [config.minBetweenness, config.maxBetweenness],
        eigenvectorRange: [config.minEigenvector, config.maxEigenvector],
        minConnections: config.minConnections.toString(),
        maxConnections: config.maxConnections.toString(),
        dateRange: { start: config.startDate, end: config.endDate }
      });
    }
  }, [isOpen, config.filteredNodeTypes, config.minDegree, config.maxDegree, 
      config.minPagerank, config.maxPagerank, config.minBetweenness, config.maxBetweenness,
      config.minEigenvector, config.maxEigenvector, config.minConnections, 
      config.maxConnections, config.startDate, config.endDate]);

  const handleTypeToggle = (typeId: string) => {
    setTempFilters(prev => ({
      ...prev,
      selectedTypes: prev.selectedTypes.includes(typeId)
        ? prev.selectedTypes.filter(id => id !== typeId)
        : [...prev.selectedTypes, typeId]
    }));
  };

  const clearAllFilters = () => {
    const allTypes = nodeTypeStats.map(type => type.id);
    setTempFilters({
      selectedTypes: allTypes,
      degreeRange: [0, 100],
      pagerankRange: [0, 100],
      betweennessRange: [0, 100],
      eigenvectorRange: [0, 100],
      minConnections: '0',
      maxConnections: '1000',
      dateRange: { start: '', end: '' }
    });
  };
  
  const applyFilters = () => {
    const newConfig = {
      filteredNodeTypes: tempFilters.selectedTypes,
      minDegree: tempFilters.degreeRange[0],
      maxDegree: tempFilters.degreeRange[1],
      minPagerank: tempFilters.pagerankRange[0],
      maxPagerank: tempFilters.pagerankRange[1],
      minBetweenness: tempFilters.betweennessRange[0],
      maxBetweenness: tempFilters.betweennessRange[1],
      minEigenvector: tempFilters.eigenvectorRange[0],
      maxEigenvector: tempFilters.eigenvectorRange[1],
      minConnections: parseInt(tempFilters.minConnections) || 0,
      maxConnections: parseInt(tempFilters.maxConnections) || 1000,
      startDate: tempFilters.dateRange.start,
      endDate: tempFilters.dateRange.end
    };
    
    // Apply optimistic update immediately for instant feedback
    setOptimisticConfig(newConfig);
    
    // Then apply the actual update in a transition
    startTransition(() => {
      updateConfig(newConfig);
    });
    
    onClose();
  };
  
  const handleDatePreset = (days: number) => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - days);
    
    setTempFilters(prev => ({
      ...prev,
      dateRange: {
        start: start.toISOString().split('T')[0],
        end: end.toISOString().split('T')[0]
      }
    }));
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card className="glass-panel w-full max-w-2xl max-h-[80vh] overflow-hidden animate-scale-in">
        <CardHeader className="pb-3 border-b border-border/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Filter className="h-5 w-5 text-primary" />
              <CardTitle className="text-lg">Advanced Filters</CardTitle>
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

        <CardContent className="p-0">
          <Tabs defaultValue="basic" className="w-full">
            <TabsList className="grid w-full grid-cols-4 glass">
              <TabsTrigger value="basic" className="flex items-center space-x-1">
                <Tag className="h-3 w-3" />
                <span>Basic</span>
              </TabsTrigger>
              <TabsTrigger value="metrics" className="flex items-center space-x-1">
                <TrendingUp className="h-3 w-3" />
                <span>Metrics</span>
              </TabsTrigger>
              <TabsTrigger value="temporal" className="flex items-center space-x-1">
                <Calendar className="h-3 w-3" />
                <span>Time</span>
              </TabsTrigger>
              <TabsTrigger value="links" className="flex items-center space-x-1">
                <Link2 className="h-3 w-3" />
                <span>Links</span>
              </TabsTrigger>
            </TabsList>

            <div className="p-6 max-h-[60vh] overflow-y-auto custom-scrollbar">
              
              <TabsContent value="basic" className="mt-0 space-y-6">
                <div>
                  <h3 className="text-sm font-medium mb-4">Node Types</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {nodeTypeStats.map((type) => (
                      <div 
                        key={type.id}
                        className="flex items-center justify-between p-3 rounded-lg border border-border/30 hover:border-primary/30 transition-colors"
                      >
                        <div className="flex items-center space-x-3">
                          <Checkbox
                            checked={tempFilters.selectedTypes.includes(type.id)}
                            onCheckedChange={() => handleTypeToggle(type.id)}
                          />
                          <div className={`w-3 h-3 rounded-full ${type.color}`} />
                          <span className="text-sm">{type.label}</span>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {type.count.toLocaleString()}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-4">Properties</h3>
                  <Select>
                    <SelectTrigger className="bg-secondary/30">
                      <SelectValue placeholder="Select properties to filter by" />
                    </SelectTrigger>
                    <SelectContent className="glass">
                      <SelectItem value="author">Author</SelectItem>
                      <SelectItem value="field">Field of Study</SelectItem>
                      <SelectItem value="institution">Institution</SelectItem>
                      <SelectItem value="keywords">Keywords</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>

              <TabsContent value="metrics" className="mt-0 space-y-6">
                <div>
                  <div className="flex justify-between items-center mb-3">
                    <Label className="text-sm font-medium">Degree Centrality</Label>
                    <Badge variant="outline" className="text-xs">
                      {tempFilters.degreeRange[0]}% - {tempFilters.degreeRange[1]}%
                    </Badge>
                  </div>
                  <Slider
                    value={tempFilters.degreeRange}
                    onValueChange={(value) => setTempFilters(prev => ({ ...prev, degreeRange: value }))}
                    max={100}
                    min={0}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div>
                  <div className="flex justify-between items-center mb-3">
                    <Label className="text-sm font-medium">PageRank Score</Label>
                    <Badge variant="outline" className="text-xs">
                      {tempFilters.pagerankRange[0]}% - {tempFilters.pagerankRange[1]}%
                    </Badge>
                  </div>
                  <Slider
                    value={tempFilters.pagerankRange}
                    onValueChange={(value) => setTempFilters(prev => ({ ...prev, pagerankRange: value }))}
                    max={100}
                    min={0}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div>
                  <div className="flex justify-between items-center mb-3">
                    <Label className="text-sm font-medium">Betweenness Centrality</Label>
                    <Badge variant="outline" className="text-xs">
                      {tempFilters.betweennessRange[0]}% - {tempFilters.betweennessRange[1]}%
                    </Badge>
                  </div>
                  <Slider
                    value={tempFilters.betweennessRange}
                    onValueChange={(value) => setTempFilters(prev => ({ ...prev, betweennessRange: value }))}
                    max={100}
                    min={0}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div>
                  <div className="flex justify-between items-center mb-3">
                    <Label className="text-sm font-medium">Eigenvector Centrality</Label>
                    <Badge variant="outline" className="text-xs">
                      {tempFilters.eigenvectorRange[0]}% - {tempFilters.eigenvectorRange[1]}%
                    </Badge>
                  </div>
                  <Slider
                    value={tempFilters.eigenvectorRange}
                    onValueChange={(value) => setTempFilters(prev => ({ ...prev, eigenvectorRange: value }))}
                    max={100}
                    min={0}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">Connection Count</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs text-muted-foreground">Minimum</Label>
                      <Input
                        type="number"
                        value={tempFilters.minConnections}
                        onChange={(e) => setTempFilters(prev => ({ ...prev, minConnections: e.target.value }))}
                        placeholder="0"
                        className="bg-secondary/30"
                      />
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">Maximum</Label>
                      <Input
                        type="number"
                        value={tempFilters.maxConnections}
                        onChange={(e) => setTempFilters(prev => ({ ...prev, maxConnections: e.target.value }))}
                        placeholder="1000"
                        className="bg-secondary/30"
                      />
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="temporal" className="mt-0 space-y-6">
                <div>
                  <h3 className="text-sm font-medium mb-3">Date Range</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs text-muted-foreground">Start Date</Label>
                      <Input
                        type="date"
                        value={tempFilters.dateRange.start}
                        onChange={(e) => setTempFilters(prev => ({ 
                          ...prev, 
                          dateRange: { ...prev.dateRange, start: e.target.value }
                        }))}
                        className="bg-secondary/30"
                      />
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">End Date</Label>
                      <Input
                        type="date"
                        value={tempFilters.dateRange.end}
                        onChange={(e) => setTempFilters(prev => ({ 
                          ...prev, 
                          dateRange: { ...prev.dateRange, end: e.target.value }
                        }))}
                        className="bg-secondary/30"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">Quick Presets</h3>
                  <div className="grid grid-cols-2 gap-2">
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8"
                      onClick={() => handleDatePreset(1)}
                    >
                      Last 24h
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8"
                      onClick={() => handleDatePreset(7)}
                    >
                      Last 7 days
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8"
                      onClick={() => handleDatePreset(30)}
                    >
                      Last 30 days
                    </Button>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      className="h-8"
                      onClick={() => handleDatePreset(90)}
                    >
                      Last 90 days
                    </Button>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="links" className="mt-0 space-y-6">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-medium">Link Strength</h3>
                    <Switch
                      checked={config.linkStrengthEnabled}
                      onCheckedChange={(checked) => updateConfig({ linkStrengthEnabled: checked })}
                      className="data-[state=checked]:bg-green-500"
                    />
                  </div>
                  
                  {config.linkStrengthEnabled && (
                    <div className="space-y-4">
                      {/* Entity-Entity Strength */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs">Entity-Entity Links</Label>
                          <span className="text-xs text-muted-foreground">
                            {config.entityEntityStrength.toFixed(1)}x
                          </span>
                        </div>
                        <Slider
                          value={[config.entityEntityStrength]}
                          onValueChange={(value) => updateConfig({ entityEntityStrength: value[0] })}
                          min={0.1}
                          max={3.0}
                          step={0.1}
                          className="w-full"
                        />
                        <p className="text-xs text-muted-foreground">
                          Stronger connections between entities (tighter clustering)
                        </p>
                      </div>

                      {/* Episodic Strength */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs">Episodic/Temporal Links</Label>
                          <span className="text-xs text-muted-foreground">
                            {config.episodicStrength.toFixed(1)}x
                          </span>
                        </div>
                        <Slider
                          value={[config.episodicStrength]}
                          onValueChange={(value) => updateConfig({ episodicStrength: value[0] })}
                          min={0.1}
                          max={3.0}
                          step={0.1}
                          className="w-full"
                        />
                        <p className="text-xs text-muted-foreground">
                          Weaker connections for temporal relationships
                        </p>
                      </div>

                      {/* Default Strength */}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs">Other Links</Label>
                          <span className="text-xs text-muted-foreground">
                            {config.defaultLinkStrength.toFixed(1)}x
                          </span>
                        </div>
                        <Slider
                          value={[config.defaultLinkStrength]}
                          onValueChange={(value) => updateConfig({ defaultLinkStrength: value[0] })}
                          min={0.1}
                          max={3.0}
                          step={0.1}
                          className="w-full"
                        />
                        <p className="text-xs text-muted-foreground">
                          Default strength for unspecified link types
                        </p>
                      </div>

                      {/* Reset button */}
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={() => {
                          updateConfig({
                            entityEntityStrength: 1.5,
                            episodicStrength: 0.5,
                            defaultLinkStrength: 1.0,
                          });
                        }}
                      >
                        Reset to Defaults
                      </Button>
                    </div>
                  )}
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">Link Display</h3>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Label className="text-xs">Show Links</Label>
                      <Switch
                        checked={config.renderLinks}
                        onCheckedChange={(checked) => updateConfig({ renderLinks: checked })}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label className="text-xs">Link Arrows</Label>
                      <Switch
                        checked={config.linkArrows}
                        onCheckedChange={(checked) => updateConfig({ linkArrows: checked })}
                      />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label className="text-xs">Curved Links</Label>
                      <Switch
                        checked={config.curvedLinks}
                        onCheckedChange={(checked) => updateConfig({ curvedLinks: checked })}
                      />
                    </div>
                  </div>
                </div>
              </TabsContent>

            </div>
          </Tabs>
        </CardContent>

        <div className="p-4 border-t border-border/20 flex items-center justify-between bg-secondary/20">
          <div className="flex items-center space-x-2">
            <Badge variant="secondary" className="text-xs">
              {tempFilters.selectedTypes.length} types selected
            </Badge>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={clearAllFilters}
              className="text-xs hover:bg-primary/10"
            >
              Clear All
            </Button>
          </div>
          <div className="flex items-center space-x-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button 
              className="bg-primary hover:bg-primary/90"
              onClick={applyFilters}
            >
              Apply Filters
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};
// Force rebuild Mon Aug 11 06:48:47 PM EDT 2025
