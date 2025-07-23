import React, { useEffect, useRef, forwardRef, useState } from 'react';
import { Cosmograph, CosmographProvider } from '@cosmograph/react';
import { useQuery } from '@tanstack/react-query';
import { graphClient } from '../api/graphClient';
import { GraphNode, GraphEdge } from '../api/types';

interface GraphCanvasProps {
  onNodeClick: (node: any) => void;
  onNodeSelect: (nodeId: string) => void;
  selectedNodes: string[];
  className?: string;
}

export const GraphCanvas = forwardRef<HTMLDivElement, GraphCanvasProps>(
  ({ onNodeClick, onNodeSelect, selectedNodes, className }, ref) => {
    const cosmographRef = useRef<any>(null);
    const [isReady, setIsReady] = useState(false);

    // Fetch graph data from Rust server
    const { data, isLoading, error } = useQuery({
      queryKey: ['graphData'],
      queryFn: () => graphClient.getGraphData({ 
        query_type: 'entire_graph',
        limit: 5000 
      }),
      refetchInterval: 30000, // Refresh every 30 seconds
    });

    // Transform data for Cosmograph format
    const transformedData = React.useMemo(() => {
      if (!data) return { nodes: [], links: [] };
      
      return {
        nodes: data.nodes.map(node => ({
          id: node.id,
          ...node,
        })),
        links: data.edges.map(edge => ({
          source: edge.from,
          target: edge.to,
          ...edge,
        })),
      };
    }, [data]);

    // Handle Cosmograph events
    const handleClick = (node?: GraphNode) => {
      if (node) {
        onNodeClick(node);
        onNodeSelect(node.id);
      }
    };

    if (isLoading) {
      return (
        <div className={`flex items-center justify-center h-full ${className}`}>
          <div className="text-muted-foreground">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mb-4"></div>
            <p>Loading graph data...</p>
          </div>
        </div>
      );
    }

    if (error) {
      return (
        <div className={`flex items-center justify-center h-full ${className}`}>
          <div className="text-destructive">
            <p>Error loading graph: {(error as Error).message}</p>
            <p className="text-sm text-muted-foreground mt-2">
              Make sure the Rust server is running at localhost:3000
            </p>
          </div>
        </div>
      );
    }

    return (
      <div 
        ref={(node) => {
          if (typeof ref === 'function') {
            ref(node);
          } else if (ref) {
            ref.current = node;
          }
        }}
        className={`relative overflow-hidden ${className}`}
      >
        <CosmographProvider
          nodes={transformedData.nodes}
          links={transformedData.links}
        >
          <Cosmograph
            ref={cosmographRef}
            // Appearance
            backgroundColor="#0a0a0a"
            nodeColor={(node: GraphNode) => node.color || '#b3b3b3'}
            nodeSize={(node: GraphNode) => node.size || 5}
            nodeLabelAccessor={(node: GraphNode) => node.label || node.id}
            linkColor="#666666"
            linkWidth={1}
            linkArrows={true}
            linkArrowsSizeScale={0.5}
            
            // Labels
            showDynamicLabels={true}
            showHoveredNodeLabel={true}
            hoveredNodeLabelColor="#ffffff"
            
            // Physics
            simulationFriction={0.85}
            simulationLinkSpring={1.0}
            simulationLinkDistance={2}
            simulationRepulsion={0.1}
            simulationGravity={0.05}
            simulationCenter={0.1}
            
            // Interaction
            onClick={handleClick}
            renderHoveredNodeRing={true}
            hoveredNodeRingColor="#22d3ee"
            focusedNodeRingColor="#fbbf24"
            nodeGreyoutOpacity={0.1}
            
            // Performance
            pixelRatio={window.devicePixelRatio || 2}
            showFPSMonitor={false}
            
            // Selection
            showLabelsFor={selectedNodes.map(id => ({ id }))}
          />
        </CosmographProvider>
        
        {/* Performance Overlay */}
        {data && (
          <div className="absolute top-4 left-4 glass text-xs text-muted-foreground p-2 rounded">
            <div>Nodes: {data.stats.total_nodes.toLocaleString()}</div>
            <div>Edges: {data.stats.total_edges.toLocaleString()}</div>
            <div>Density: {data.stats.density.toFixed(4)}</div>
          </div>
        )}
      </div>
    );
  }
);

GraphCanvas.displayName = 'GraphCanvas';