import React from 'react';
import { useGraphDataQuery } from '../hooks/useGraphDataQuery';
import { GraphViewport } from './GraphViewport';

/**
 * Standalone GraphViewport that fetches its own data
 * This is what the test expects
 */
const GraphViewportStandalone: React.FC = () => {
  const { 
    transformedData,
    isLoading,
    error
  } = useGraphDataQuery();

  const [selectedNode, setSelectedNode] = React.useState(null);
  const [selectedNodes, setSelectedNodes] = React.useState<string[]>([]);
  const [hoveredNode, setHoveredNode] = React.useState(null);

  if (isLoading) {
    return <div>Loading...</div>;
  }

  if (error) {
    return <div>Error: {error.message}</div>;
  }

  return (
    <GraphViewport
      nodes={transformedData?.nodes || []}
      links={transformedData?.links || []}
      selectedNodes={selectedNodes}
      highlightedNodes={[]}
      hoveredNode={hoveredNode}
      hoveredConnectedNodes={[]}
      selectedNode={selectedNode}
      onNodeClick={setSelectedNode}
      onNodeSelect={(nodeId) => setSelectedNodes([nodeId])}
      onNodeHover={setHoveredNode}
      onClearSelection={() => setSelectedNodes([])}
      onShowNeighbors={() => {}}
      onZoomIn={() => {}}
      onZoomOut={() => {}}
      onFitView={() => {}}
      onScreenshot={() => {}}
    />
  );
};

export default GraphViewportStandalone;