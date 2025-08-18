import React from 'react';
import { Download, Upload, Camera, Play, Pause, Settings, BarChart3, Maximize2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { GraphSearch } from './GraphSearch';
import { GraphNode } from '../api/types';
import { WebSocketStatus } from './WebSocketStatus';

interface GraphNavBarProps {
  totalNodes: number;
  visibleNodes: number;
  isVirtualized: boolean;
  isSimulationRunning: boolean;
  selectedNodes: GraphNode[];
  allNodes: GraphNode[];
  onNodeSelect: (node: GraphNode) => void;
  onHighlightNodes: (nodes: GraphNode[]) => void;
  onSelectNodes: (nodes: GraphNode[]) => void;
  onClearSelection: () => void;
  onFilterClick: () => void;
  onDownload: () => void;
  onUpload: () => void;
  onScreenshot: () => void;
  onToggleSimulation: () => void;
  onSettingsClick: () => void;
  onStatsClick: () => void;
  onFullscreenClick: () => void;
}

export const GraphNavBar: React.FC<GraphNavBarProps> = ({
  totalNodes,
  visibleNodes,
  isVirtualized,
  isSimulationRunning,
  selectedNodes,
  allNodes,
  onNodeSelect,
  onHighlightNodes,
  onSelectNodes,
  onClearSelection,
  onFilterClick,
  onDownload,
  onUpload,
  onScreenshot,
  onToggleSimulation,
  onSettingsClick,
  onStatsClick,
  onFullscreenClick,
}) => {
  return (
    <div className="h-16 glass-panel border-b border-border/20 flex items-center justify-between px-6 z-50">
      <div className="flex items-center space-x-4">
        <div className="text-xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
          Graphiti
        </div>
        <Badge variant="secondary" className="text-xs">
          Knowledge Graph
        </Badge>
        {isVirtualized && (
          <Badge variant="outline" className="text-xs border-warning text-warning">
            Virtualized ({visibleNodes.toLocaleString()}/{totalNodes.toLocaleString()})
          </Badge>
        )}
      </div>

      <div className="flex-1 max-w-2xl mx-8">
        <GraphSearch 
          onNodeSelect={onNodeSelect}
          onHighlightNodes={onHighlightNodes}
          onSelectNodes={onSelectNodes}
          onClearSelection={onClearSelection}
          onFilterClick={onFilterClick}
          nodes={allNodes}
          className="w-full"
        />
      </div>

      <div className="flex items-center space-x-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onDownload}
          className="hover:bg-primary/10"
          title="Download Graph"
        >
          <Download className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onUpload}
          disabled
          className="hover:bg-primary/10"
          title="Upload Graph"
        >
          <Upload className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onScreenshot}
          className="hover:bg-primary/10"
          title="Take Screenshot"
        >
          <Camera className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleSimulation}
          className="hover:bg-primary/10"
          title={isSimulationRunning ? "Pause Simulation" : "Play Simulation"}
        >
          {isSimulationRunning ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onSettingsClick}
          className="hover:bg-primary/10"
          title="Settings"
        >
          <Settings className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onStatsClick}
          className="hover:bg-primary/10"
          title="Statistics"
        >
          <BarChart3 className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onFullscreenClick}
          className="hover:bg-primary/10"
          title="Fullscreen"
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
        <div className="ml-4 pl-4 border-l border-border/20">
          <WebSocketStatus />
        </div>
      </div>
    </div>
  );
};