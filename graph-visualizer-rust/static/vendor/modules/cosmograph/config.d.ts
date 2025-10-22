import { CosmosInputLink, CosmosInputNode, GraphConfigInterface, GraphSimulationSettings, GraphEvents } from '@cosmograph/cosmos';
export type CosmographConfigInterface<N extends CosmosInputNode, L extends CosmosInputLink> = {
    /**
     * Do not run the simulation, just render the graph.
     * Cosmos uses the x and y values of the nodes’ data to determine their position in the graph.
     * If x and y values are not specified, the position of the nodes will be assigned randomly.
     * If the value is set to null and the data does not have any links,
     * Cosmograph will automatically set this value to `true`.
     * Default value: `null`
     */
    disableSimulation?: boolean | null;
    /**
     * Show labels for the nodes that are currently visible on the screen,
     * and automatically update to reflect the current zoom level.
     * Default: `true`
     */
    showDynamicLabels?: boolean;
    /**
     * Show labels for the top nodes.
     * Default: `false`
     */
    showTopLabels?: boolean;
    /**
     * Sets the maximum number of top nodes to show labels for.
     * Default: `100`
     */
    showTopLabelsLimit?: number;
    /**
     * Specify the key that is used to determine the top nodes.
     * By default, the top nodes are determined by the node degree.
     * Default: `undefined`
     */
    showTopLabelsValueKey?: keyof N;
    /**
     * An array of nodes to show labels for.
     * Default: `undefined`
     */
    showLabelsFor?: N[];
    /**
     * Whether to show a hovered node label.
     * Default: `false`
     */
    showHoveredNodeLabel?: boolean;
    /**
     * Function that  generate custom text for each label.
     * Default: `n => n.id`
     * @param node Node object
     * @returns String that will be used as the label text for that node
     */
    nodeLabelAccessor?: (node: N) => string;
    /**
     * Specifies the CSS class to use for the labels.
     * Default: `undefined`
     */
    nodeLabelClassName?: string | ((node: N) => string);
    /**
     * Specifies the CSS color to use for the labels.
     * Default: `undefined`
     */
    nodeLabelColor?: string | ((node: N) => string);
    /**
     * Specifies the CSS class to use for the hovered node label.
     * Default: `undefined`
     */
    hoveredNodeLabelClassName?: string | ((node: N) => string);
    /**
     * Specifies the CSS color to use for the hovered node label.
     * Default: `undefined`
     */
    hoveredNodeLabelColor?: string | ((node: N) => string);
    /**
     * Callback function that will be called when the data was updated
     * Default: `undefined`
     */
    onSetData?: (nodes: N[], links: L[]) => void;
    /**
     * Callback function that will be called when the nodes was filtered by Node Crossfilter.
     * Default: `undefined`
     */
    onNodesFiltered?: (filteredNodes: N[] | undefined) => void;
    /**
     * Callback function that will be called when the links was filtered by Link Crossfilter.
     * Default: `undefined`
     */
    onLinksFiltered?: (filteredLinks: L[] | undefined) => void;
    /**
     * Callback function that will be called when clicked on a label.
     * The Node data for this label will be passed as the first argument,
     * and the corresponding mouse event as the second argument
     * Default: `undefined`
     */
    onLabelClick?: (node: N, event: MouseEvent) => void;
} & GraphEvents<N> & {
    /**
     * Decay coefficient. Use bigger values if you want the simulation to "cool down" slower.
     * Default value: `1000`
     */
    simulationDecay?: GraphSimulationSettings<N>['decay'];
    /**
     * Gravity force coefficient.
     * Default value: `0`
     */
    simulationGravity?: GraphSimulationSettings<N>['gravity'];
    /**
     * Centering to center mass force coefficient.
     * Default value: `0`
     */
    simulationCenter?: GraphSimulationSettings<N>['center'];
    /**
     * Repulsion force coefficient.
     * Default value: `0.1`
     */
    simulationRepulsion?: GraphSimulationSettings<N>['repulsion'];
    /**
     * Decreases / increases the detalization of the Many-Body force calculations.
     * When `useQuadtree` is set to `true`, this property corresponds to the Barnes–Hut approximation criterion.
     * Default value: `1.7`
     */
    simulationRepulsionTheta?: GraphSimulationSettings<N>['repulsionTheta'];
    /**
     * Barnes–Hut approximation depth.
     * Can only be used when `useQuadtree` is set `true`.
     * Default value: `12`
     */
    simulationRepulsionQuadtreeLevels?: GraphSimulationSettings<N>['repulsionQuadtreeLevels'];
    /**
     * Link spring force coefficient.
     * Default value: `1`
     */
    simulationLinkSpring?: GraphSimulationSettings<N>['linkSpring'];
    /**
     * Minimum link distance.
     * Default value: `2`
     */
    simulationLinkDistance?: GraphSimulationSettings<N>['linkDistance'];
    /**
     * Range of random link distance values.
     * Default value: `[1, 1.2]`
     */
    simulationLinkDistRandomVariationRange?: GraphSimulationSettings<N>['linkDistRandomVariationRange'];
    /**
     * Repulsion coefficient from mouse position.
     * The repulsion force is activated by pressing the right mouse button.
     * Default value: `2`
     */
    simulationRepulsionFromMouse?: GraphSimulationSettings<N>['repulsionFromMouse'];
    /**
     * Friction coefficient.
     * Default value: `0.85`
     */
    simulationFriction?: GraphSimulationSettings<N>['friction'];
    /**
     * Callback function that will be called when the simulation starts.
     * Default value: `undefined`
     */
    onSimulationStart?: GraphSimulationSettings<N>['onStart'];
    /**
     * Callback function that will be called on every tick of the simulation.
     * The value of the first argument `alpha` will decrease over time as the simulation
     * "cools down". If there's a node under the cursor, its datum will be passed as the second argument,
     * index as the third argument and position as the fourth argument:
     * (alpha: number, node: Node | undefined, index: number | undefined, nodePosition: [number, number] | undefined) => void. Default value: undefined
     * Default value: `undefined`
     */
    onSimulationTick?: GraphSimulationSettings<N>['onTick'];
    /**
     * Callback function that will be called when the simulation stops.
     * Default value: `undefined`
     */
    onSimulationEnd?: GraphSimulationSettings<N>['onEnd'];
    /**
     * Callback function that will be called when the simulation is paused.
     * Default value: `undefined`
     */
    onSimulationPause?: GraphSimulationSettings<N>['onPause'];
    /**
     * Callback function that will be called when the simulation is restarted.
     * Default value: `undefined`
     */
    onSimulationRestart?: GraphSimulationSettings<N>['onRestart'];
};
export declare const defaultCosmographConfig: CosmographConfigInterface<CosmosInputNode, CosmosInputLink>;
export type CosmographInputConfig<N extends CosmosInputNode, L extends CosmosInputLink> = CosmographConfigInterface<N, L> & Omit<GraphConfigInterface<N, L>, 'events' | 'simulation' | 'disableSimulation'>;
