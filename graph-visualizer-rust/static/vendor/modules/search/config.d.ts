import { CosmosInputNode } from '@cosmograph/cosmos';
import type { SearchConfigInterface, SearchEvents } from '@cosmograph/ui';
export type CosmographSearchConfigInterface<N extends CosmosInputNode> = {
    /**
     * Callback function that will be called when the user selects an item from the suggestions list.
     * Provides selected node as argument.
     */
    onSelectResult?: (node?: N) => void;
} & Omit<SearchEvents<N>, 'onSelect'>;
export declare const defaultCosmographSearchConfig: CosmographSearchInputConfig<CosmosInputNode>;
export type CosmographSearchInputConfig<N extends CosmosInputNode> = CosmographSearchConfigInterface<N> & Omit<SearchConfigInterface<N>, 'events'>;
