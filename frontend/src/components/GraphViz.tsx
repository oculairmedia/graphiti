import React, { useState, useRef, useEffect } from 'react';
import { Search, Settings, BarChart3, Download, Upload, Maximize2, ZoomIn, ZoomOut, Camera, Filter, Layout, Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { ControlPanel } from './ControlPanel';
import { SearchBar } from './SearchBar';
import { GraphCanvas } from './GraphCanvas';
import { NodeDetailsPanel } from './NodeDetailsPanel';
import { LayoutPanel } from './LayoutPanel';
import { FilterPanel } from './FilterPanel';
import { StatsPanel } from './StatsPanel';
import { QuickActions } from './QuickActions';

interface GraphVizProps {
  className?: string;
}

export const GraphViz: React.FC<GraphVizProps> = ({ className }) => {
  const [leftPanelCollapsed, setLeftPanelCollapsed] = useState(false);
  const [rightPanelCollapsed, setRightPanelCollapsed] = useState(false);
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [showStatsPanel, setShowStatsPanel] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);

  const graphCanvasRef = useRef<HTMLDivElement>(null);

  // Mock data for demonstration
  const mockNodeData = {
    id: 'node_123',
    name: 'Neural Network Research',
    type: 'Entity',
    summary: 'Comprehensive research on neural network architectures and their applications in modern AI systems.',
    properties: {
      field: 'Artificial Intelligence',
      author: 'Dr. Sarah Chen',
      citations: 342,
      year: 2024
    },
    centrality: {
      degree: 0.85,
      betweenness: 0.72,
      pagerank: 0.91,
      eigenvector: 0.78
    },
    timestamps: {
      created: '2024-01-15T10:30:00Z',
      updated: '2024-01-20T14:45:00Z'
    },
    connections: 23
  };

  const handleNodeSelect = (nodeId: string) => {
    if (selectedNodes.includes(nodeId)) {
      setSelectedNodes(selectedNodes.filter(id => id !== nodeId));
    } else {
      setSelectedNodes([...selectedNodes, nodeId]);
    }
  };

  const handleNodeClick = (node: any) => {
    setSelectedNode(node);
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  return (
    <div className={`h-screen w-full flex flex-col bg-background overflow-hidden ${className}`}>
      {/* Top Navigation Bar */}
      <div className="h-16 glass-panel border-b border-border/20 flex items-center justify-between px-6 z-50">
        <div className="flex items-center space-x-4">
          <div className="text-xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
            Graphiti
          </div>
          <Badge variant="secondary" className="text-xs">
            Knowledge Graph
          </Badge>
        </div>

        <div className="flex-1 max-w-2xl mx-8">
          <SearchBar 
            value={searchQuery}
            onChange={setSearchQuery}
            onFilterClick={() => setShowFilterPanel(true)}
          />
        </div>

        <div className="flex items-center space-x-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowStatsPanel(true)}
            className="hover:bg-primary/10"
          >
            <BarChart3 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={toggleFullscreen}
            className="hover:bg-primary/10"
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="hover:bg-primary/10"
          >
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Control Panel */}
        <div className={`${leftPanelCollapsed ? 'w-12' : 'w-80'} transition-all duration-300 flex-shrink-0`}>
          <ControlPanel 
            collapsed={leftPanelCollapsed}
            onToggleCollapse={() => setLeftPanelCollapsed(!leftPanelCollapsed)}
          />
        </div>

        {/* Main Graph Viewport */}
        <div className="flex-1 relative">
          <GraphCanvas 
            ref={graphCanvasRef}
            onNodeClick={handleNodeClick}
            onNodeSelect={handleNodeSelect}
            selectedNodes={selectedNodes}
            className="h-full w-full"
          />
          
          {/* Node Details Panel Overlay */}
          {selectedNode && (
            <div className="absolute top-4 right-4 w-96 animate-slide-in-right">
              <NodeDetailsPanel 
                node={selectedNode}
                onClose={() => setSelectedNode(null)}
              />
            </div>
          )}

          {/* Quick Actions Toolbar */}
          <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2">
            <QuickActions 
              selectedCount={selectedNodes.length}
              onClearSelection={() => setSelectedNodes([])}
              onFitToScreen={() => {}}
              onZoomIn={() => {}}
              onZoomOut={() => {}}
              onScreenshot={() => {}}
            />
          </div>
        </div>

        {/* Right Layout Panel */}
        <div className={`${rightPanelCollapsed ? 'w-12' : 'w-80'} transition-all duration-300 flex-shrink-0`}>
          <LayoutPanel 
            collapsed={rightPanelCollapsed}
            onToggleCollapse={() => setRightPanelCollapsed(!rightPanelCollapsed)}
          />
        </div>
      </div>

      {/* Modal Panels */}
      {showFilterPanel && (
        <FilterPanel 
          isOpen={showFilterPanel}
          onClose={() => setShowFilterPanel(false)}
        />
      )}

      {showStatsPanel && (
        <StatsPanel 
          isOpen={showStatsPanel}
          onClose={() => setShowStatsPanel(false)}
        />
      )}
    </div>
  );
};

export default GraphViz;