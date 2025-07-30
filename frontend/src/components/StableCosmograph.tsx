import React, { memo, forwardRef } from 'react';
import { Cosmograph, CosmographRef } from '@cosmograph/react';
import type { GraphNode } from '../api/types';
import type { GraphLink } from '../types/graph';
import { useStableConfig } from '../contexts/GraphConfigProvider';
import { hexToRgba } from '../utils/colorCache';

interface StableCosmographProps {
  nodes: GraphNode[];
  links: GraphLink[];
  width: number;
  height: number;
  // Dynamic props that trigger updates
  nodeColor?: (node: GraphNode) => string;
  nodeSize?: (node: GraphNode) => number;
  nodeLabel?: (node: GraphNode) => string | undefined;
  linkColor?: (link: GraphLink) => string;
  linkWidth?: (link: GraphLink) => number;
  // Event handlers
  onZoom?: () => void;
  onNodeMouseOver?: (node: GraphNode | undefined) => void;
  onNodeMouseOut?: () => void;
  onNodeClick?: (node: GraphNode | undefined) => void;
  // Other dynamic props
  selectedNodes?: GraphNode[];
  focusedNodeIndex?: number;
  disableSimulation?: boolean | null;
  showLabels?: boolean;
  showHoveredNodeLabel?: boolean;
  renderLinks?: boolean;
}

// Memoized Cosmograph wrapper that only re-renders when necessary
const StableCosmograph = memo(forwardRef<CosmographRef, StableCosmographProps>((props, ref) => {
  const { config: stableConfig } = useStableConfig();
  
  const {
    nodes,
    links,
    width,
    height,
    nodeColor,
    nodeSize,
    nodeLabel,
    linkColor,
    linkWidth,
    onZoom,
    onNodeMouseOver,
    onNodeMouseOut,
    onNodeClick,
    selectedNodes,
    focusedNodeIndex,
    disableSimulation,
    showLabels,
    showHoveredNodeLabel,
    renderLinks,
  } = props;
  
  // Convert stable config colors to number arrays for Cosmograph
  const backgroundColor = hexToRgba(stableConfig.backgroundColor) || [0, 0, 0, 1];
  const linkColorValue = hexToRgba(stableConfig.linkColor) || [229, 231, 235, 1];
  const hoveredPointRingColor = hexToRgba(stableConfig.hoveredPointRingColor) || [255, 215, 0, 1];
  const focusedPointRingColor = hexToRgba(stableConfig.focusedPointRingColor) || [255, 107, 107, 1];
  const labelColor = hexToRgba(stableConfig.labelColor) || [255, 255, 255, 1];
  const hoveredLabelColor = hexToRgba(stableConfig.hoveredLabelColor) || [255, 255, 255, 1];
  
  return (
    <Cosmograph
      ref={ref}
      nodes={nodes}
      links={links}
      width={width}
      height={height}
      
      // Physics (stable)
      simulationGravity={stableConfig.gravity}
      simulationRepulsion={stableConfig.repulsion}
      simulationFriction={stableConfig.friction}
      simulationLinkSpring={stableConfig.linkSpring}
      simulationLinkDistance={stableConfig.linkDistance}
      simulationRepulsionTheta={stableConfig.simulationRepulsionTheta}
      simulationCluster={stableConfig.simulationCluster}
      simulationClusterStrength={stableConfig.simulationClusterStrength}
      simulationImpulse={stableConfig.simulationImpulse}
      simulationDecay={stableConfig.simulationDecay}
      disableSimulation={disableSimulation}
      spaceSize={stableConfig.spaceSize}
      randomSeed={stableConfig.randomSeed}
      
      // Quadtree (stable)
      useQuadtree={stableConfig.useQuadtree}
      quadtreeLevels={stableConfig.quadtreeLevels}
      
      // Node appearance (dynamic callbacks)
      nodeColor={nodeColor}
      nodeSize={nodeSize}
      nodeLabel={nodeLabel}
      nodeLabelAccessor={nodeLabel}
      
      // Link appearance (stable + dynamic)
      linkColor={linkColor || (() => linkColorValue)}
      linkWidth={linkWidth || (() => stableConfig.linkWidth)}
      linkOpacity={stableConfig.linkOpacity}
      linkGreyoutOpacity={stableConfig.linkGreyoutOpacity}
      scaleLinksOnZoom={stableConfig.scaleLinksOnZoom}
      linkVisibilityDistance={stableConfig.linkVisibilityDistance}
      linkVisibilityMinTransparency={stableConfig.linkVisibilityMinTransparency}
      linkArrows={stableConfig.linkArrows}
      linkArrowsSizeScale={stableConfig.linkArrowsSizeScale}
      curvedLinks={stableConfig.curvedLinks}
      curvedLinkSegments={stableConfig.curvedLinkSegments}
      curvedLinkWeight={stableConfig.curvedLinkWeight}
      curvedLinkControlPointDistance={stableConfig.curvedLinkControlPointDistance}
      renderLinks={renderLinks}
      
      // Labels (stable + dynamic toggles)
      showLabels={showLabels}
      showHoveredNodeLabel={showHoveredNodeLabel}
      labelColor={labelColor}
      hoveredLabelColor={hoveredLabelColor}
      labelSize={stableConfig.labelSize}
      
      // Background (stable)
      backgroundColor={backgroundColor}
      
      // Hover and focus (stable + dynamic)
      hoveredPointCursor={stableConfig.hoveredPointCursor}
      renderHoveredPointRing={stableConfig.renderHoveredPointRing}
      hoveredPointRingColor={hoveredPointRingColor}
      focusedPointRingColor={focusedPointRingColor}
      focusedNodeIndex={focusedNodeIndex}
      selectedNodes={selectedNodes}
      
      // Events
      onZoom={onZoom}
      onNodeMouseOver={onNodeMouseOver}
      onNodeMouseOut={onNodeMouseOut}
      onNodeClick={onNodeClick}
      
      // Fit view (stable)
      fitViewDuration={stableConfig.fitViewDuration}
      fitViewPadding={stableConfig.fitViewPadding}
    />
  );
}), (prevProps, nextProps) => {
  // Custom comparison function for memo
  // Only re-render if important props change
  return (
    prevProps.nodes === nextProps.nodes &&
    prevProps.links === nextProps.links &&
    prevProps.width === nextProps.width &&
    prevProps.height === nextProps.height &&
    prevProps.selectedNodes === nextProps.selectedNodes &&
    prevProps.focusedNodeIndex === nextProps.focusedNodeIndex &&
    prevProps.disableSimulation === nextProps.disableSimulation &&
    prevProps.showLabels === nextProps.showLabels &&
    prevProps.showHoveredNodeLabel === nextProps.showHoveredNodeLabel &&
    prevProps.renderLinks === nextProps.renderLinks &&
    // Check if callbacks are the same reference
    prevProps.nodeColor === nextProps.nodeColor &&
    prevProps.nodeSize === nextProps.nodeSize &&
    prevProps.nodeLabel === nextProps.nodeLabel &&
    prevProps.linkColor === nextProps.linkColor &&
    prevProps.linkWidth === nextProps.linkWidth
  );
});

StableCosmograph.displayName = 'StableCosmograph';

export default StableCosmograph;