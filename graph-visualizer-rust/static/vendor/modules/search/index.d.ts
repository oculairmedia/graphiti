import { CosmosInputNode, CosmosInputLink } from '@cosmograph/cosmos';
import { Search, type SearchConfigInterface } from '@cosmograph/ui';
import { CosmographSearchInputConfig, CosmographSearchConfigInterface } from './config';
import { Cosmograph } from '../cosmograph';
export declare class CosmographSearch<N extends CosmosInputNode, L extends CosmosInputLink> {
    private _cosmograph;
    private _config;
    private _data;
    private _filter;
    private _defaultAccessors;
    search: Search<N>;
    constructor(cosmograph: Cosmograph<N, L>, targetElement: HTMLElement, config?: SearchConfigInterface<N>);
    /**  `setConfig`: Sets config for the `Search` instance. */
    setConfig(config?: CosmographSearchInputConfig<N>): void;
    private _updateData;
    /**  `getConfig`: Returns current `Search` configuration. */
    getConfig(): CosmographSearchConfigInterface<N>;
    /**  `remove`: Destroys current `Search` instance. */
    remove(): void;
    /**  `setListState`: Manages the state of the `Search` suggestions/accessors dropdown list. */
    setListState(state: boolean): void;
    /**  `clearInput`: Clears the text input of `Search` instance. */
    clearInput(): void;
    private _createDefaultAccessorOptions;
    private _onSelectResult;
    private _createSearchConfig;
    private _onSelect;
    private _onSearch;
    private _onEnter;
    private _onAccessorSelect;
}
export type { SearchConfigInterface as CosmographSearchConfigInterface, CosmographSearchInputConfig };
