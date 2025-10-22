import { Graph, CosmosInputNode, CosmosInputLink } from '@cosmograph/cosmos';
import { type CosmographConfigInterface, type CosmographInputConfig } from './config';
import type { CosmographData } from './types';
import { Filter } from './crossfilter';
export declare class Cosmograph<N extends CosmosInputNode, L extends CosmosInputLink> {
    private _data;
    private _previousData;
    private _cosmographConfig;
    private _cosmosConfig;
    private _containerNode;
    private _labelsDivElement;
    private _watermarkDivElement;
    private _canvasElement;
    private _hoveredCssLabel;
    private _hoveredNode;
    private _cssLabelsRenderer;
    private _selectedNodesSet;
    private _nodesForTopLabels;
    private _nodesForForcedLabels;
    private _trackedNodeToLabel;
    private _isLabelsDestroyed;
    private _svgParser;
    private _nodesCrossfilter;
    private _linksCrossfilter;
    /** Filters nodes based on a links crossfilter result  */
    private _nodesFilter;
    /** Filters links based on a nodes crossfilter result  */
    private _linksFilter;
    /** Filters node based on selected nodes */
    private _selectedNodesFilter;
    private _disableSimulation;
    private _cosmos?;
    /**
    * @deprecated Direct use of the cosmos can lead to unexpected results,
    * so we do not recommend using it. Will be removed in version 2.0.0
    * */
    cosmos?: Graph<N, L>;
    constructor(containerNode: HTMLDivElement, config?: CosmographInputConfig<N, L>);
    get data(): CosmographData<N, L>;
    /**
     * Progress value indicates how far the simulation goes from 0 to 1,
     * where 0 represents the start of the simulation and 1 represents the end.
     */
    get progress(): number | undefined;
    /**
     * A value that gives information about the running simulation status.
     */
    get isSimulationRunning(): boolean | undefined;
    /**
     * The maximum point size.
     * This value is the maximum size of the `gl.POINTS` primitive that WebGL can render on the user's hardware.
     */
    get maxPointSize(): number | undefined;
    /**
     * Sets the data for the graph.
     * @param nodes - Nodes to be added to the graph.
     * @param links - Links to be added to the graph.
     * @param runSimulation When set to `false`, the simulation won't be started automatically (`true` by default).
     */
    setData(nodes: N[], links: L[], runSimulation?: boolean): void;
    /**
     * Sets the config for the graph.
     * @param config - Config to be applied to the graph.
     */
    setConfig(config?: CosmographInputConfig<N, L>): void;
    /**
     * Creates a filter for the nodes, adds the filter to the nodes crossfilter and returns this filter.
     */
    addNodesFilter(): Filter<N>;
    /**
     * Creates a filter for the links, adds the filter to the links crossfilter and returns this filter.
     */
    addLinksFilter(): Filter<L>;
    /**
     * Selects nodes inside a rectangular area.
     * @param selection Array of two corners of the rectangle `[[left, top], [right, bottom]]`.
     * The `left` and `right` coordinates should be relative to the width of the canvas. The
     * `top` and `bottom` coordinates should be relative to the height of the canvas.
     */
    selectNodesInRange(selection: [[number, number], [number, number]] | null): void;
    /**
     * Selects nodes.
     * @param nodes Array of nodes to be selected.
     */
    selectNodes(nodes: N[]): void;
    /**
     * Selects a node and, optionally, select its connected nodes.
     * @param node Selected node.
     * @param selectAdjacentNodes Optional parameter determining whether to also select the connected nodes.
     */
    selectNode(node: N, selectAdjacentNodes?: boolean): void;
    /**
     * Unselects all nodes.
     */
    unselectNodes(): void;
    /**
     * Get nodes that are currently selected.
     * @returns Array of selected nodes.
     */
    getSelectedNodes(): N[] | null | undefined;
    /**
     * Center the view and zoom in to a node.
     * @param node Node to be zoomed in.
     */
    zoomToNode(node: N): void;
    /**
     * Zoom the view in or out to the specified zoom level.
     * @param value Zoom level
     * @param duration Duration of the zoom in/out transition.
     */
    setZoomLevel(value: number, duration?: number): void;
    /**
     * Get zoom level.
     * @returns Zoom level value of the view.
     */
    getZoomLevel(): number | undefined;
    /**
     * Get current X and Y coordinates of the nodes.
     * @returns Object where keys are the ids of the nodes and values are corresponding `{ x: number; y: number }` objects.
     */
    getNodePositions(): {
        [key: string]: {
            x: number;
            y: number;
        };
    } | undefined;
    /**
     * Get current X and Y coordinates of the nodes.
     * @returns A Map object where keys are the ids of the nodes and values are their corresponding X and Y coordinates in the [number, number] format.
     */
    getNodePositionsMap(): Map<string, [number, number]> | undefined;
    /**
     * Get current X and Y coordinates of the nodes.
     * @returns Array of `[x: number, y: number]` arrays.
     */
    getNodePositionsArray(): [number, number][] | undefined;
    /**
     * Center and zoom in/out the view to fit all nodes in the scene.
     * @param duration Duration of the center and zoom in/out animation in milliseconds (`250` by default).
     */
    fitView(duration?: number): void;
    /**
     * Center and zoom in/out the view to fit nodes by their ids in the scene.
     * @param duration Duration of the center and zoom in/out animation in milliseconds (`250` by default).
     */
    fitViewByNodeIds(ids: string[], duration?: number): void;
    /**
     * Set focus on a node. A ring will be drawn around the focused node.
     * If no node is focused, the ring will be cleared.
     * @param node Node to be focused.
     */
    focusNode(node?: N): void;
    /**
     * Get nodes that are adjacent to a specific node by its id.
     * @param id Id of the node.
     * @returns Array of adjacent nodes.
     */
    getAdjacentNodes(id: string): N[] | undefined;
    /**
     * Converts the X and Y node coordinates from the space coordinate system to the screen coordinate system.
     * @param spacePosition Array of x and y coordinates in the space coordinate system.
     * @returns Array of x and y coordinates in the screen coordinate system.
     */
    spaceToScreenPosition(spacePosition: [number, number]): [number, number] | undefined;
    /**
     * Converts the node radius value from the space coordinate system to the screen coordinate system.
     * @param spaceRadius Radius of Node in the space coordinate system.
     * @returns Radius of Node in the screen coordinate system.
     */
    spaceToScreenRadius(spaceRadius: number): number | undefined;
    /**
     * Get node radius by its index.
     * @param index Index of the node.
     * @returns Radius of the node.
     */
    getNodeRadiusByIndex(index: number): number | undefined;
    /**
     * Get node radius by its id.
     * @param id Id of the node.
     * @returns Radius of the node.
     */
    getNodeRadiusById(id: string): number | undefined;
    /**
     * For the nodes that are currently visible on the screen, get a sample of node ids with their coordinates.
     * The resulting number of nodes will depend on the `nodeSamplingDistance` configuration property,
     * and the sampled nodes will be evenly distributed.
     * @returns A Map object where keys are the ids of the nodes and values are their corresponding X and Y coordinates in the [number, number] format.
     */
    getSampledNodePositionsMap(): Map<string, [number, number]> | undefined;
    /**
     * Starts the simulation.
     * @param alpha Value between 0 and 1. The higher the value,
     * the more initial energy the simulation will get.
     */
    start(alpha?: number): void;
    /**
     * Pause the simulation.
     */
    pause(): void;
    /**
     * Restarts the simulation.
     */
    restart(): void;
    /**
     * Render only one frame of the simulation (stops the simulation if it was running).
     */
    step(): void;
    /**
     * Destroy the graph and clean up the context.
     */
    remove(): void;
    /**
     * Create new Cosmos instance.
     */
    create(): void;
    /**
     * Returns an array of nodes with their degree values in the order they were sent to Cosmograph.
     */
    getNodeDegrees(): number[] | undefined;
    private _createCosmosConfig;
    private _updateLabels;
    private _updateSelectedNodesSet;
    private _renderLabels;
    private _renderLabelForHovered;
    /** Apply crossfiltered nodes result to links crossfilter */
    private _applyLinksFilter;
    /** Apply crossfiltered links result to nodes crossfilter */
    private _applyNodesFilter;
    private _checkBrightness;
    private _isDataDifferent;
    private _onClick;
    private _onLabelClick;
    private _onHoveredNodeClick;
    private _onNodeMouseOver;
    private _onNodeMouseOut;
    private _onMouseMove;
    private _onZoomStart;
    private _onZoom;
    private _onZoomEnd;
    private _onStart;
    private _onTick;
    private _onEnd;
    private _onPause;
    private _onRestart;
}
export type { CosmographData, CosmographConfigInterface, CosmographInputConfig, Filter };
