import type { AccessorOption, SearchData } from './types';
import { type SearchConfigInterface, type SearchEvents } from './config';
export declare class Search<T extends SearchData> {
    private _search;
    private _containerNode;
    private _config;
    constructor(containerNode: HTMLElement, config?: SearchConfigInterface<T>);
    setData(data: T[]): void;
    setConfig(config?: SearchConfigInterface<T>): void;
    setListState(state: boolean): void;
    clearInput(): void;
    /**  `getConfig`: Returns current `Search` configuration */
    getConfig(): SearchConfigInterface<T>;
    destroy(): void;
}
export type { SearchData, SearchConfigInterface, SearchEvents, AccessorOption as SearchAccessorOption };
