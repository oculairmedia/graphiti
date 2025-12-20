/**
 * GraphCanvasRenderer Component
 * Pure presentational component that renders Cosmograph with all visual configuration
 * Extracted from GraphCanvasV2 to separate rendering concerns
 * 
 * IMPORTANT: This component contains the EXACT Cosmograph JSX from GraphCanvasV2
 * to ensure zero regressions. All props are preserved exactly as they were.
 */

import React, { useMemo } from 'react';
import { Cosmograph } from '@cosmograph/react';

// PERFORMANCE FIX: Module-level constants to avoid array recreation on each render
const DEFAULT_COLOR_PALETTE = [
  '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
  '#1abc9c', '#34495e', '#e67e22', '#95a5a6', '#d35400'
] as const;

const DEFAULT_LINK_DIST_VARIATION_RANGE = [1, 1.2] as const;

interface CosmographData {
  nodes: any[];
  links: any[];
}

interface VisualizationConfig {
  pointSizeRange: [number, number];
  linkWidthRange: [number, number];
  nodeColorConfig: {
    colorBy: string;
    strategy: string;
    colorMap: Record<string, string>;
    colorFn?: (value: number | string) => string;
  };
  linkWidthByFn?: (edgeType: any, linkIndex: number) => number;
  linkColorByFn?: (edgeType: any, linkIndex: number) => string;
}

interface EventHandlers {
  handleClick: (nodeIndex: number | undefined) => void;
  handleMouseOver: (pointIndex: number | null) => void;
  handleMouseOut: () => void;
}

interface GraphCanvasRendererProps {
  cosmographRef: React.RefObject<any>;
  cosmographData: CosmographData;
  config: any; // GraphConfig type
  visualConfig: VisualizationConfig;
  eventHandlers: EventHandlers;
  // PERFORMANCE FIX: Changed from Map to boolean to prevent re-renders on every glow change
  hasGlowingNodes: boolean;
  onReady: () => void;
}

/**
 * Pure rendering component for Cosmograph
 * All logic and state management happens in parent component
 */
// PERFORMANCE FIX: Memoize renderer to prevent unnecessary Cosmograph re-renders
export const GraphCanvasRenderer: React.FC<GraphCanvasRendererProps> = React.memo(({
  cosmographRef,
  cosmographData,
  config,
  visualConfig,
  eventHandlers,
  hasGlowingNodes,
  onReady
}) => {
  const { pointSizeRange, linkWidthRange, nodeColorConfig, linkWidthByFn, linkColorByFn } = visualConfig;
  const { handleClick, handleMouseOver, handleMouseOut } = eventHandlers;
  
  const CosmographAny = Cosmograph as any;
  
  // Safety check - ensure data arrays exist before rendering Cosmograph
  const safeNodes = cosmographData?.nodes || [];
  const safeLinks = cosmographData?.links || [];
  
  // PERFORMANCE FIX: Memoize label class name functions to avoid recreation on each render
  const pointLabelClassName = useMemo(() => () => 
    `background: ${config.labelBackgroundColor || 'rgba(0,0,0,0.7)'}; ` +
    `font-weight: ${config.labelFontWeight || 400}; ` +
    `padding: 4px 6px; border-radius: 3px;`,
    [config.labelBackgroundColor, config.labelFontWeight]
  );
  
  const hoveredPointLabelClassName = useMemo(() => () =>
    `background: ${config.hoveredLabelBackgroundColor || 'rgba(0,0,0,0.9)'}; ` +
    `font-weight: ${config.hoveredLabelFontWeight || 600}; ` +
    `font-size: ${config.hoveredLabelSize || 14}px; ` +
    `color: ${config.hoveredLabelColor || '#ffffff'}; ` +
    `padding: 5px 8px; border-radius: 4px;`,
    [config.hoveredLabelBackgroundColor, config.hoveredLabelFontWeight, config.hoveredLabelSize, config.hoveredLabelColor]
  );
  
  return (
    <CosmographAny
      ref={cosmographRef}
      // Use points/links instead of nodes/links
      // Safety: use empty arrays if data is undefined to prevent .length errors
      points={safeNodes}
      links={safeLinks}
      // Point configuration - tell Cosmograph how to interpret the data
      pointIdBy="id"
      pointIndexBy="index"
      pointLabelBy={config.labelBy || "label"}
      pointSizeBy="size"
      pointClusterBy={config.clusteringEnabled ? "cluster" : undefined}
      pointClusterStrengthBy={config.clusteringEnabled ? "clusterStrength" : undefined}
      // Label configuration - using Cosmograph's actual API
      showLabels={config.renderLabels || false}
      pointLabelFontSize={config.labelSize || 12}
      pointLabelColor={config.labelColor || "#ffffff"}
      showDynamicLabels={config.showDynamicLabels || false}
      showTopLabels={config.showTopLabels || false}
      showTopLabelsLimit={config.showTopLabelsLimit || 100}
      showHoveredPointLabel={config.showHoveredNodeLabel !== false}
      // Use className for background and font weight styling (memoized)
      pointLabelClassName={pointLabelClassName}
      hoveredPointLabelClassName={hoveredPointLabelClassName}
      // Link configuration - use indices for performance
      linkSourceBy="source"
      linkSourceIndexBy="sourceIndex"
      linkTargetBy="target"
      linkTargetIndexBy="targetIndex"
      // Use Direct strategy to allow linkColorByFn to return custom colors
      // This enables edge highlighting for selected/hovered links
      linkColorStrategy="direct"
      // Always use edge_type as the base field for linkColorBy
      linkColorBy="edge_type"
      // Use memoized link color function that handles both color and transparency
      linkColorByFn={linkColorByFn}
      linkWidthBy={
        // Only use columns that actually exist in the links data
        // For uniform width, we don't set this to allow linkWidthRange to work
        config.linkWidthScheme === 'uniform' ? undefined :
        // For by-weight, use the weight column if it exists
        config.linkWidthScheme === 'by-weight' && cosmographData.links[0]?.weight ? 'weight' : 
        // For other schemes, we need a dummy column for linkWidthByFn to work
        'edge_type'  // Use edge_type as a dummy column for function-based sizing
      }
      linkWidthByFn={
        // IMPORTANT: Don't provide linkWidthByFn for uniform width
        // This allows linkWidthRange to control the width directly
        config.linkWidthScheme === 'uniform' ? undefined : linkWidthByFn
      }
      linkWidthRange={linkWidthRange}
      // Link visual properties - increased visibility
      linkWidth={config.linkWidth || 2}
      linkOpacity={config.linkOpacity || 0.85}
      linkColor={config.linkColor || '#9CA3AF'}
      linkArrows={config.edgeArrows || false}
      curvedLinks={config.curvedLinks || false}
      curvedLinkSegments={config.curvedLinkSegments || 19}
      curvedLinkWeight={config.curvedLinkWeight || 0.8}
      curvedLinkControlPointDistance={config.curvedLinkControlPointDistance || 0.5}
      // Visual configuration
      backgroundColor={config.backgroundColor}
      pointSizeStrategy="auto"
      pointSizeRange={pointSizeRange}
      // Color configuration
      pointColorPalette={DEFAULT_COLOR_PALETTE}
      // Use strategy based on color scheme
      pointColorStrategy={nodeColorConfig.strategy}
      // Specify which column contains the color data
      pointColorBy={nodeColorConfig.colorBy}
      // Use map for type-based coloring
      pointColorByMap={nodeColorConfig.colorMap}
      // Use function for metric-based coloring
      pointColorByFn={nodeColorConfig.colorFn}
      // Interaction
      enableDrag={true}
      enableRightClickRepulsion={true}
      renderLinks={config.renderLinks !== false}
      // Point ring colors for hover and focus
      // PERFORMANCE FIX: Use boolean instead of checking Map.size to avoid re-renders
      focusedPointRingColor={hasGlowingNodes ? (config.nodeAccessHighlightColor || "#FFD700") : (config.focusedPointRingColor || "#0066cc")}
      // Layout and simulation - fitView configuration
      fitViewOnInit={false}  // Disable automatic fitView to prevent simulation interruption (like old implementation)
      // fitViewDelay={config.fitViewDelay || 500}  // Not needed when fitViewOnInit is false
      fitViewPadding={config.fitViewPadding !== undefined ? config.fitViewPadding : 0.2}  // Default: 0.2 (20% padding) - normalized value 0-1
      fitViewDuration={config.fitViewDuration || 1000}  // Default: 1000ms - animation duration
      simulationEnabled={!config.disableSimulation && config.simulationEnabled !== false}
      simulationGravity={config.gravity ?? config.simulationGravity ?? 0.1}
      simulationCenter={config.centerForce ?? config.simulationCenter ?? 0.0}
      simulationRepulsion={config.repulsion ?? config.simulationRepulsion ?? 0.5}
      simulationRepulsionTheta={config.simulationRepulsionTheta ?? 1.7}
      simulationLinkDistance={config.linkDistance ?? config.simulationLinkDistance ?? 2}
      simulationLinkSpring={config.linkSpring ?? config.simulationLinkSpring ?? 1}
      simulationLinkDistRandomVariationRange={config.linkDistRandomVariationRange ?? DEFAULT_LINK_DIST_VARIATION_RANGE}
      simulationFriction={config.friction ?? config.simulationFriction ?? 0.85}
      simulationDecay={config.simulationDecay ?? 1000}
      simulationCluster={config.simulationCluster ?? 0.1}
      simulationClusterStrength={config.clusterStrength ?? config.simulationClusterStrength}
      simulationRepulsionFromMouse={config.mouseRepulsion ?? 2.0}
      // Hover configuration - use Cosmograph's built-in hover system
      renderHoveredPointRing={true}
      hoveredPointRingColor="#ffffff"
      hoveredPointCursor="pointer"
      onPointMouseOver={handleMouseOver}
      onPointMouseOut={handleMouseOut}
      // Events
      onReady={onReady}
      onClick={handleClick}
    />
  );
}, (prevProps, nextProps) => {
  // Custom comparison to prevent unnecessary re-renders
  // Only re-render if these critical props change
  return (
    prevProps.cosmographData === nextProps.cosmographData &&
    prevProps.config === nextProps.config &&
    prevProps.visualConfig === nextProps.visualConfig &&
    prevProps.eventHandlers === nextProps.eventHandlers &&
    prevProps.hasGlowingNodes === nextProps.hasGlowingNodes
    // Note: cosmographRef and onReady are stable refs/callbacks
  );
});
