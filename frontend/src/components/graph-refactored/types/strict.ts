/**
 * Strict TypeScript type definitions for graph components
 * All types are fully defined with no implicit any
 */

import { ReactNode, RefObject, CSSProperties } from 'react';

// ============================================================================
// Core Graph Types
// ============================================================================

export interface StrictGraphNode {
  readonly id: string;
  readonly label: string;
  readonly node_type: NodeType;
  readonly created_at: string;
  readonly updated_at: string;
  readonly properties: Record<string, unknown>;
  readonly summary: string;
  readonly name: string;
  // Optional positioning
  readonly x?: number;
  readonly y?: number;
  readonly z?: number;
  // Optional visual properties
  readonly color?: string;
  readonly size?: number;
  readonly opacity?: number;
}

export enum NodeType {
  Entity = 'Entity',
  Episodic = 'Episodic',
  Relation = 'Relation',
  Unknown = 'Unknown'
}

export interface StrictGraphLink {
  readonly source: string;
  readonly target: string;
  readonly from: string;
  readonly to: string;
  readonly weight: number;
  readonly edge_type: EdgeType;
  // Optional visual properties
  readonly color?: string;
  readonly width?: number;
  readonly opacity?: number;
}

export enum EdgeType {
  RelatedTo = 'RELATED_TO',
  Contains = 'CONTAINS',
  References = 'REFERENCES',
  DependsOn = 'DEPENDS_ON',
  Unknown = 'UNKNOWN'
}

// ============================================================================
// Component Props Types
// ============================================================================

export interface StrictGraphRendererProps {
  readonly nodes: ReadonlyArray<StrictGraphNode>;
  readonly links: ReadonlyArray<StrictGraphLink>;
  readonly nodeColor?: string | ((node: StrictGraphNode) => string);
  readonly nodeSize?: number | ((node: StrictGraphNode) => number);
  readonly nodeLabel?: (node: StrictGraphNode) => string;
  readonly linkColor?: string | ((link: StrictGraphLink) => string);
  readonly linkWidth?: number | ((link: StrictGraphLink) => number);
  readonly onNodeClick?: (node: StrictGraphNode | null) => void;
  readonly onNodeHover?: (node: StrictGraphNode | null) => void;
  readonly onNodeDoubleClick?: (node: StrictGraphNode | null) => void;
  readonly onZoom?: (zoomLevel: number) => void;
  readonly showFPSMonitor?: boolean;
  readonly simulationGravity?: number;
  readonly simulationRepulsion?: number;
  readonly simulationFriction?: number;
  readonly pixelRatio?: number;
  readonly initialZoomLevel?: number;
  readonly fitViewOnInit?: boolean;
}

export interface StrictGraphRendererRef {
  zoomIn(): void;
  zoomOut(): void;
  fitView(): void;
  getZoomLevel(): number;
  selectNode(nodeId: string): void;
  highlightNodes(nodeIds: ReadonlyArray<string>): void;
  clearHighlights(): void;
  pauseSimulation(): void;
  resumeSimulation(): void;
  restartSimulation(): void;
}

// ============================================================================
// Event Types
// ============================================================================

export interface StrictGraphEvent<T = unknown> {
  readonly type: GraphEventType;
  readonly target: EventTarget | null;
  readonly data: T;
  readonly timestamp: number;
  readonly propagationStopped: boolean;
}

export enum GraphEventType {
  NodeClick = 'node:click',
  NodeDoubleClick = 'node:dblclick',
  NodeHover = 'node:hover',
  NodeDragStart = 'node:dragstart',
  NodeDrag = 'node:drag',
  NodeDragEnd = 'node:dragend',
  LinkClick = 'link:click',
  LinkHover = 'link:hover',
  CanvasClick = 'canvas:click',
  CanvasDoubleClick = 'canvas:dblclick',
  CanvasDragStart = 'canvas:dragstart',
  CanvasDrag = 'canvas:drag',
  CanvasDragEnd = 'canvas:dragend',
  Zoom = 'zoom',
  Pan = 'pan'
}

// ============================================================================
// Delta Update Types
// ============================================================================

export interface StrictDeltaUpdate<T = unknown> {
  readonly id: string;
  readonly timestamp: number;
  readonly type: DeltaOperationType;
  readonly entityType: DeltaEntityType;
  readonly data: T;
  readonly metadata?: Record<string, unknown>;
}

export enum DeltaOperationType {
  Add = 'add',
  Update = 'update',
  Remove = 'remove'
}

export enum DeltaEntityType {
  Node = 'node',
  Link = 'link'
}

// ============================================================================
// State Management Types
// ============================================================================

export interface StrictGraphState {
  readonly nodes: ReadonlyArray<StrictGraphNode>;
  readonly links: ReadonlyArray<StrictGraphLink>;
  readonly selectedNodeIds: ReadonlySet<string>;
  readonly hoveredNodeId: string | null;
  readonly isLoading: boolean;
  readonly error: Error | null;
  readonly stats: GraphStats;
}

export interface GraphStats {
  readonly totalNodes: number;
  readonly totalLinks: number;
  readonly nodesByType: Readonly<Record<NodeType, number>>;
  readonly linksByType: Readonly<Record<EdgeType, number>>;
  readonly density: number;
  readonly averageDegree: number;
}

// ============================================================================
// Hook Return Types
// ============================================================================

export interface StrictUseGraphDataReturn {
  readonly data: StrictGraphState | null;
  readonly isLoading: boolean;
  readonly error: Error | null;
  readonly refresh: () => Promise<void>;
  readonly updateNode: (nodeId: string, updates: Partial<StrictGraphNode>) => void;
  readonly updateLink: (source: string, target: string, updates: Partial<StrictGraphLink>) => void;
  readonly addNode: (node: StrictGraphNode) => void;
  readonly addLink: (link: StrictGraphLink) => void;
  readonly removeNode: (nodeId: string) => void;
  readonly removeLink: (source: string, target: string) => void;
  readonly clearCache: () => void;
}

export interface StrictUseGraphDeltaReturn {
  readonly isConnected: boolean;
  readonly connect: () => void;
  readonly disconnect: () => void;
  readonly subscribe: (callback: (delta: StrictDeltaUpdate) => void) => () => void;
  readonly send: (message: unknown) => void;
  readonly stats: DeltaConnectionStats;
}

export interface DeltaConnectionStats {
  readonly messagesReceived: number;
  readonly messagesSent: number;
  readonly lastMessageTime: number | null;
  readonly connectionTime: number | null;
  readonly reconnectAttempts: number;
}

// ============================================================================
// Performance Types
// ============================================================================

export interface StrictPerformanceMetrics {
  readonly renderTime: number;
  readonly updateTime: number;
  readonly fps: number;
  readonly memoryUsage: MemoryUsage;
  readonly nodeRenderCount: number;
  readonly linkRenderCount: number;
}

export interface MemoryUsage {
  readonly used: number;
  readonly total: number;
  readonly percent: number;
}

// ============================================================================
// Configuration Types
// ============================================================================

export interface StrictGraphConfig {
  readonly rendering: RenderingConfig;
  readonly simulation: SimulationConfig;
  readonly interaction: InteractionConfig;
  readonly performance: PerformanceConfig;
}

export interface RenderingConfig {
  readonly pixelRatio: number;
  readonly antialias: boolean;
  readonly alpha: boolean;
  readonly premultipliedAlpha: boolean;
  readonly preserveDrawingBuffer: boolean;
  readonly powerPreference: 'default' | 'high-performance' | 'low-power';
}

export interface SimulationConfig {
  readonly enabled: boolean;
  readonly gravity: number;
  readonly repulsion: number;
  readonly friction: number;
  readonly linkStrength: number;
  readonly linkDistance: number;
  readonly theta: number;
  readonly alpha: number;
  readonly alphaDecay: number;
  readonly alphaMin: number;
  readonly velocityDecay: number;
}

export interface InteractionConfig {
  readonly enableZoom: boolean;
  readonly enablePan: boolean;
  readonly enableDrag: boolean;
  readonly enableHover: boolean;
  readonly enableSelection: boolean;
  readonly multiSelectKey: 'ctrl' | 'shift' | 'alt';
  readonly clickDelay: number;
  readonly doubleClickDelay: number;
  readonly dragThreshold: number;
}

export interface PerformanceConfig {
  readonly targetFPS: number;
  readonly adaptiveQuality: boolean;
  readonly virtualRendering: boolean;
  readonly objectPooling: boolean;
  readonly batchUpdates: boolean;
  readonly maxNodes: number;
  readonly maxLinks: number;
}

// ============================================================================
// Utility Types
// ============================================================================

export type DeepReadonly<T> = {
  readonly [P in keyof T]: T[P] extends object ? DeepReadonly<T[P]> : T[P];
};

export type Nullable<T> = T | null;
export type Optional<T> = T | undefined;
export type Maybe<T> = T | null | undefined;

export type AsyncResult<T> = Promise<{ success: true; data: T } | { success: false; error: Error }>;

export type EventHandler<T = void> = (event: StrictGraphEvent<T>) => void;
export type NodePredicate = (node: StrictGraphNode) => boolean;
export type LinkPredicate = (link: StrictGraphLink) => boolean;

export type NodeColorFunction = (node: StrictGraphNode) => string;
export type NodeSizeFunction = (node: StrictGraphNode) => number;
export type LinkColorFunction = (link: StrictGraphLink) => string;
export type LinkWidthFunction = (link: StrictGraphLink) => number;

// ============================================================================
// Type Guards
// ============================================================================

export function isStrictGraphNode(value: unknown): value is StrictGraphNode {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    'label' in value &&
    'node_type' in value &&
    typeof (value as any).id === 'string'
  );
}

export function isStrictGraphLink(value: unknown): value is StrictGraphLink {
  return (
    typeof value === 'object' &&
    value !== null &&
    'source' in value &&
    'target' in value &&
    'weight' in value &&
    typeof (value as any).source === 'string' &&
    typeof (value as any).target === 'string'
  );
}

export function isDeltaUpdate(value: unknown): value is StrictDeltaUpdate {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    'type' in value &&
    'entityType' in value &&
    'timestamp' in value
  );
}

// ============================================================================
// Assertion Functions
// ============================================================================

export function assertNever(value: never): never {
  throw new Error(`Unexpected value: ${value}`);
}

export function assertDefined<T>(
  value: T | null | undefined,
  message?: string
): asserts value is T {
  if (value === null || value === undefined) {
    throw new Error(message || 'Value is null or undefined');
  }
}

export function assertType<T>(
  value: unknown,
  guard: (value: unknown) => value is T,
  message?: string
): asserts value is T {
  if (!guard(value)) {
    throw new Error(message || 'Type assertion failed');
  }
}