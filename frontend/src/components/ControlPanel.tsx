import React, { useState, useCallback, memo } from 'react';
import { ChevronLeft, ChevronRight, Database, Settings2, Palette, Zap, Paintbrush, Layers, Search, BarChart } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useGraphConfig } from '@/contexts/GraphConfigProvider';
import type { GraphData, GraphNode } from '@/types/graph';
import { useConfigPersistence } from '@/hooks/usePersistedConfig';
import { GraphitiSearch } from './GraphitiSearch';
import type { NodeResult } from '../api/types';

// Import tab components
import { QueryControlsTab } from './ControlPanel/QueryControlsTab';
import { NodeStylingTab } from './ControlPanel/NodeStylingTab';
import { PhysicsControlsTab } from './ControlPanel/PhysicsControlsTab';
import { RenderControlsTab } from './ControlPanel/RenderControlsTab';
import { SettingsTab } from './ControlPanel/SettingsTab';
import { CentralityControlsTab } from './ControlPanel/CentralityControlsTab';

interface GraphCanvasHandle {
  clearSelection: () => void;
  selectNode: (node: GraphNode) => void;
  selectNodes: (nodes: GraphNode[]) => void;
  focusOnNodes: (nodeIds: string[], duration?: number, padding?: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: (duration?: number, padding?: number) => void;
}

interface ControlPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  onLayoutChange?: (layout: string) => void;
  graphCanvasRef?: React.RefObject<GraphCanvasHandle>;
  nodes?: GraphNode[];
  onNodeSelect?: (node: GraphNode) => void;
}

// Compute node types from nodes array dynamically
const computeNodeTypes = (nodes: GraphNode[]): Array<{ id: string; name: string; count: number }> => {
  if (!nodes || nodes.length === 0) {
    // Return empty array if no nodes available
    return [];
  }

  // Count actual node types from nodes
  const typeCount: Record<string, number> = {};
  nodes.forEach((node: GraphNode) => {
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

export const ControlPanel: React.FC<ControlPanelProps> = React.memo(({ 
  collapsed, 
  onToggleCollapse,
  onLayoutChange,
  graphCanvasRef,
  nodes = [],
  onNodeSelect
}) => {
  const { config, updateConfig, updateNodeTypeConfigurations, applyLayout, cosmographRef } = useGraphConfig();
  const { resetAllConfig, exportConfig, importConfig, getStorageInfo } = useConfigPersistence();
  
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  // Compute real node types from nodes prop with memoization
  const nodeTypes = React.useMemo(() => computeNodeTypes(nodes), [nodes]);
  
  // Node type configurations are now updated in GraphViz.tsx to avoid duplicate calls

  const handleResetToDefaults = useCallback(() => {
    updateConfig({
      // Reset to Cosmograph v2.0 defaults
      repulsion: 0.1,
      simulationRepulsionTheta: 1.7,
      simulationCluster: 0.1,
      simulationClusterStrength: undefined,
      simulationImpulse: undefined,
      linkSpring: 1.0,
      linkDistance: 2,
      linkDistRandomVariationRange: [1, 1.2],
      gravity: 0.0,
      centerForce: 0.0,
      friction: 0.85,
      simulationDecay: 1000,
      mouseRepulsion: 2.0,
      spaceSize: 4096,
      randomSeed: undefined,
      disableSimulation: null
    });
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
      // Trigger a refresh through window reload or other mechanism
      // Since we're not using React Query here, we'll rely on the parent component
      window.location.reload();
    } catch (error) {
      // In production, you might want to show a user-friendly error message
      // toast.error('Failed to refresh graph data. Please try again.');
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleQuickQuery = async (queryType: string, limit: number): Promise<void> => {
    try {
      updateConfig({ queryType, nodeLimit: limit });
      setTimeout(() => {
        handleRefreshGraph().catch(error => {
          // Refresh error handled silently
        });
      }, 100);
    } catch (error) {
      // Query error handled silently to not interrupt UI flow
    }
  };
  
  // Stable callback for search node selection to prevent re-renders
  const handleSearchNodeSelect = useCallback((node: NodeResult) => {
    // Try multiple matching strategies
    let graphNode = nodes.find(n => n.id === node.uuid);
    
    if (!graphNode) {
      // Try matching against uuid field if it exists
      graphNode = nodes.find(n => (n as any).uuid === node.uuid);
    }
    
    if (!graphNode) {
      // Try converting index to string and matching
      const nodeIndex = nodes.findIndex(n => n.id === String(node.uuid));
      if (nodeIndex >= 0) {
        graphNode = nodes[nodeIndex];
      }
    }
    
    if (graphNode) {
      onNodeSelect?.(graphNode);
    } else {
      // Single concise warning when node not found
      console.warn('[Search] Node not found:', node.uuid);
    }
  }, [nodes, onNodeSelect]);

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
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Search">
            <Search className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Query">
            <Database className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Node Styling">
            <Paintbrush className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Physics">
            <Zap className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Centrality">
            <BarChart className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Rendering">
            <Layers className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" className="p-2 hover:bg-primary/10" title="Settings">
            <Settings2 className="h-4 w-4" />
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
        <Tabs defaultValue="search" className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid grid-cols-7 m-4 mb-2 glass">
            <TabsTrigger value="search" className="text-xs">
              <Search className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="query" className="text-xs">
              <Database className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="styling" className="text-xs">
              <Paintbrush className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="physics" className="text-xs">
              <Zap className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="centrality" className="text-xs">
              <BarChart className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="render" className="text-xs">
              <Layers className="h-3 w-3" />
            </TabsTrigger>
            <TabsTrigger value="settings" className="text-xs">
              <Settings2 className="h-3 w-3" />
            </TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-y-auto custom-scrollbar px-4 pb-4 min-h-0">
            
            {/* Search Tab */}
            <TabsContent value="search" className="mt-0 h-full">
              {graphCanvasRef && onNodeSelect && (
                <GraphitiSearch
                  graphCanvasRef={graphCanvasRef}
                  className="h-full"
                  onNodeSelect={handleSearchNodeSelect}
                />
              )}
            </TabsContent>
            
            {/* Query Controls Tab */}
            <TabsContent value="query" className="mt-0">
              <QueryControlsTab
                config={config}
                isRefreshing={isRefreshing}
                onQueryTypeChange={(value) => updateConfig({ queryType: value })}
                onNodeLimitChange={(value) => updateConfig({ nodeLimit: value })}
                onSearchTermChange={(value) => updateConfig({ searchTerm: value })}
                onRefreshGraph={handleRefreshGraph}
                onQuickQuery={handleQuickQuery}
              />
            </TabsContent>

            {/* Node Styling Tab */}
            <TabsContent value="styling" className="mt-0">
              <NodeStylingTab
                config={config}
                nodeTypes={nodeTypes}
                onNodeTypeColorChange={handleNodeTypeColorChange}
                onNodeTypeVisibilityChange={handleNodeTypeVisibilityChange}
                onConfigUpdate={updateConfig}
              />
            </TabsContent>

            {/* Physics Tab */}
            <TabsContent value="physics" className="mt-0">
              <PhysicsControlsTab
                config={config}
                onConfigUpdate={updateConfig}
                onResetToDefaults={handleResetToDefaults}
              />
            </TabsContent>

            {/* Centrality Tab */}
            <TabsContent value="centrality" className="mt-0">
              <CentralityControlsTab
                onCentralityUpdate={() => {
                  // Trigger a refresh of the graph data
                  // This will be handled by the parent component
                  console.log('Centrality updated, refresh graph data');
                }}
              />
            </TabsContent>

            {/* Render Controls Tab */}
            <TabsContent value="render" className="mt-0">
              <RenderControlsTab
                config={config}
                onConfigUpdate={updateConfig}
              />
            </TabsContent>

            {/* Settings Tab */}
            <TabsContent value="settings" className="mt-0">
              <SettingsTab
                config={config}
                onConfigUpdate={updateConfig}
                graphStats={nodes && nodes.length > 0 ? {
                  nodeCount: nodes.length,
                  edgeCount: 0  // Edge count would need to be passed separately if needed
                } : undefined}
              />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
});

ControlPanel.displayName = 'ControlPanel';