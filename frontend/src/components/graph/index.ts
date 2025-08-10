/**
 * Refactored graph components following modern React architecture
 * with proper separation of concerns
 */

// Core components
export { GraphContainer } from './GraphContainer';
export type { GraphContainerProps } from './GraphContainer';

export { GraphCanvasRenderer } from './GraphCanvasRenderer';
export type { GraphViewportProps, GraphViewportHandle, ViewportInfo } from './GraphCanvasRenderer';

// Utility components
export { ErrorBoundary } from './ErrorBoundary';
export { GraphLoadingState } from './GraphLoadingState';

// Re-export hooks for convenience
export { useGraphData, createGraphDelta } from '../../hooks/graph/useGraphData';
export type { GraphDataState, GraphDataActions, GraphDelta, GraphLink } from '../../hooks/graph/useGraphData';

export { useWebSocketManager } from '../../hooks/graph/useWebSocketManager';
export type { WebSocketState, WebSocketActions, WebSocketMessage } from '../../hooks/graph/useWebSocketManager';

export { useGraphRenderer } from '../../hooks/graph/useGraphRenderer';
export type { GraphRendererState, GraphRendererActions, RenderConfig, RenderStats } from '../../hooks/graph/useGraphRenderer';