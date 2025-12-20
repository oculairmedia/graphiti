import React from 'react';
import { 
  Download, Upload, Camera, Play, Pause, Settings, 
  BarChart3, Maximize2, Minimize2, Activity, Filter, 
  Clock, RefreshCw, ZoomIn, ZoomOut, Crosshair 
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { GraphSearch } from './GraphSearch';
import { GraphNode } from '../types/graph';
import { WebSocketStatus } from './WebSocketStatus';

// GRAPH-93: Zustand stores for global state
import { useUIStore, useGraphStore, useSelectionStore } from '../stores';

interface GraphNavBarProps {
  // Graph data (still needs to be passed - not global)
  nodes?: GraphNode[];
  links?: any[];
  
  // Callbacks that need parent context
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  onFitView?: () => void;
  onRefresh?: () => void;
  onDownload?: () => void;
  onUpload?: () => void;
  onScreenshot?: () => void;
  
  // Optional overrides (for flexibility)
  isRefreshing?: boolean;
}

export const GraphNavBar: React.FC<GraphNavBarProps> = ({
  nodes = [],
  links = [],
  onZoomIn,
  onZoomOut,
  onFitView,
  onRefresh,
  onDownload,
  onUpload,
  onScreenshot,
  isRefreshing = false,
}) => {
  // GRAPH-93: Read UI state from Zustand store
  const {
    isFullscreen,
    toggleFullscreen,
    showFilterPanel,
    toggleFilterPanel,
    showStatsPanel,
    toggleStatsPanel,
    showMonitoringPanel,
    toggleMonitoringPanel,
    isTimelineVisible,
    toggleTimeline,
  } = useUIStore();
  
  // GRAPH-93: Read graph state from Zustand store
  const {
    isSimulationRunning,
    toggleSimulation,
    liveStats,
  } = useGraphStore();
  
  // GRAPH-93: Read selection state from Zustand store
  const {
    selectNode,
    setHighlightedNodes,
    clearAll: clearSelection,
  } = useSelectionStore();
  
  // Use live stats if available, otherwise use passed nodes/links
  const nodeCount = liveStats?.nodeCount ?? nodes.length;
  const edgeCount = liveStats?.edgeCount ?? links.length;
  
  const handleNodeSelect = (node: GraphNode) => {
    selectNode(node);
  };
  
  const handleHighlightNodes = (highlightNodes: GraphNode[]) => {
    setHighlightedNodes(highlightNodes.map(n => n.id));
  };
  
  const handleSelectNodes = (selectedNodes: GraphNode[]) => {
    // For now, select the first node - multi-select can be added later
    if (selectedNodes.length > 0) {
      selectNode(selectedNodes[0]);
    }
  };

  return (
    <div className="absolute top-0 left-0 right-0 h-12 glass-panel border-b border-border/20 flex items-center justify-between px-4 z-50">
      {/* Left section - Logo and stats */}
      <div className="flex items-center space-x-3">
        <div className="text-lg font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
          Graphiti
        </div>
        <Badge variant="secondary" className="text-xs">
          {nodeCount.toLocaleString()} nodes · {edgeCount.toLocaleString()} edges
        </Badge>
        {liveStats && (
          <Badge variant="outline" className="text-xs text-muted-foreground">
            Updated {new Date(liveStats.lastUpdated).toLocaleTimeString()}
          </Badge>
        )}
      </div>

      {/* Center section - Search */}
      <div className="flex-1 max-w-xl mx-4">
        <GraphSearch 
          onNodeSelect={handleNodeSelect}
          onHighlightNodes={handleHighlightNodes}
          onSelectNodes={handleSelectNodes}
          onClearSelection={clearSelection}
          onFilterClick={toggleFilterPanel}
          nodes={nodes}
          className="w-full"
        />
      </div>

      {/* Right section - Controls */}
      <div className="flex items-center space-x-1">
        {/* Zoom controls */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onZoomIn}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Zoom In"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onZoomOut}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Zoom Out"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onFitView}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Fit View"
        >
          <Crosshair className="h-4 w-4" />
        </Button>
        
        <div className="w-px h-6 bg-border/30 mx-1" />
        
        {/* Simulation control */}
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleSimulation}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title={isSimulationRunning ? "Pause Simulation" : "Play Simulation"}
        >
          {isSimulationRunning ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>
        
        {/* Refresh */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Refresh Data"
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        </Button>
        
        <div className="w-px h-6 bg-border/30 mx-1" />
        
        {/* Panel toggles */}
        <Button
          variant={showFilterPanel ? "secondary" : "ghost"}
          size="sm"
          onClick={toggleFilterPanel}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Filter Panel"
        >
          <Filter className="h-4 w-4" />
        </Button>
        <Button
          variant={showStatsPanel ? "secondary" : "ghost"}
          size="sm"
          onClick={toggleStatsPanel}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Statistics"
        >
          <BarChart3 className="h-4 w-4" />
        </Button>
        <Button
          variant={showMonitoringPanel ? "secondary" : "ghost"}
          size="sm"
          onClick={toggleMonitoringPanel}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="System Monitoring"
        >
          <Activity className="h-4 w-4" />
        </Button>
        <Button
          variant={isTimelineVisible ? "secondary" : "ghost"}
          size="sm"
          onClick={toggleTimeline}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Timeline"
        >
          <Clock className="h-4 w-4" />
        </Button>
        
        <div className="w-px h-6 bg-border/30 mx-1" />
        
        {/* Actions */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onScreenshot}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Take Screenshot"
        >
          <Camera className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onDownload}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title="Download Graph"
        >
          <Download className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleFullscreen}
          className="h-8 w-8 p-0 hover:bg-primary/10"
          title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </Button>
        
        <div className="w-px h-6 bg-border/30 mx-1" />
        
        {/* WebSocket Status */}
        <WebSocketStatus />
      </div>
    </div>
  );
};

export default GraphNavBar;
