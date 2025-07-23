import crossfilter from 'crossfilter2';
type OnFilterCallback = () => void;
type OnDataAddedCallback = () => void;
type OnDataRemovedCallback = () => void;
export declare class Filter<Record> {
    private _crossfilter;
    private _dimension;
    private _selfRemove;
    private _syncUp;
    onFiltered: OnFilterCallback | undefined;
    onDataAdded: OnDataAddedCallback | undefined;
    onDataRemoved: OnDataRemovedCallback | undefined;
    constructor(crossfilter: crossfilter.Crossfilter<Record>, selfRemove: () => void, syncUp?: () => void);
    setAccessor(selector: crossfilter.OrderedValueSelector<Record, string | string[] | number | number[]>): void;
    applyFilter(filterValue: (d: unknown) => boolean): void;
    clear(): void;
    getAllValues(): crossfilter.NaturallyOrderedValue[] | undefined;
    getFilteredValues(): crossfilter.NaturallyOrderedValue[] | undefined;
    getFilteredRecords(): Record[];
    isActive(): boolean;
    dispose(): void;
    remove(): void;
}
export declare class Crossfilter<Record> {
    private _crossfilter;
    private _records;
    private _filters;
    private _syncUpFunction;
    onFiltered: OnFilterCallback | undefined;
    onDataAdded: OnDataAddedCallback | undefined;
    onDataRemoved: OnDataRemovedCallback | undefined;
    constructor(syncUpFunction: () => void);
    addRecords(records: Record[]): void;
    getFilteredRecords(ignoreFilter?: Filter<Record>): Record[];
    addFilter(runSyncOnApply?: boolean): Filter<Record>;
    clearFilters(): void;
    isAnyFiltersActive(exceptFilter?: Filter<Record>): boolean;
    getAllRecords(): Record[] | undefined;
}
export {};
