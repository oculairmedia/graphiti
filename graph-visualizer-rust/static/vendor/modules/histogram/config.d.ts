import type { HistogramConfigInterface, HistogramEvents } from '@cosmograph/ui';
import { FilterType } from '../cosmograph/types';
export type CosmographHistogramConfigInterface<OutDatum, InDatum = OutDatum> = {
    /** `accessor`: Data key to access numeric values for the `CosmographHistogram`. Default: `n => n['value']` */
    accessor?: (d: InDatum) => number;
    /** `customExtent`: Minimum and maximum extent for the `CosmographHistogram` visualisation. Can be used if you doesn't want histogram range to be automatically calculated from data extent`. Default: `undefined` */
    customExtent?: [number, number];
    /** `data`: The histogram will be constructed from a user-defined data array using an accessor function. Default: `undefined` */
    data?: InDatum[];
    /** `filterFunction`: The function is used to narrow down the selection of nodes that will be passed to the Cosmograph Crossfilter. Default: `undefined` */
    filterFunction?: (selection: [number, number], data: InDatum[], crossfilteredData: OutDatum[]) => OutDatum[];
    /** `filterType` Defines which types of Cosmograph Crossfilter to use.
     * Can only be set once during initialization. Default: `nodes` */
    filterType?: FilterType | string;
    /**  `onSelection`: Callback for the range selection. Provides current selection of `CosmographHistogram`. */
    onSelection?: Exclude<HistogramEvents['onBrush'], undefined>;
    /** `highlightCrossfiltered`: Whether to highlight cross-filtered data from Cosmograph or not. Default: `true`  */
    highlightCrossfiltered?: boolean;
} & Omit<HistogramEvents, 'onBrush'>;
export declare const defaultCosmographHistogramConfig: CosmographHistogramConfigInterface<unknown>;
export type CosmographHistogramInputConfig<OutDatum, InDatum = OutDatum> = CosmographHistogramConfigInterface<OutDatum, InDatum> & Omit<HistogramConfigInterface, 'events'>;
