import { CosmosInputLink, CosmosInputNode } from '@cosmograph/cosmos';
import { Cosmograph } from '../cosmograph';
import { CosmographHistogramInputConfig, CosmographHistogramConfigInterface } from './config';
export declare class CosmographHistogram<OutDatum, InDatum = OutDatum> {
    private _cosmograph;
    private _histogram;
    private _config;
    private _filter;
    constructor(cosmograph: Cosmograph<CosmosInputNode, CosmosInputLink>, targetElement: HTMLElement, config?: CosmographHistogramInputConfig<OutDatum, InDatum>);
    /**
     * Sets the config for the histogram.
     * @param config Configuration to be applied to the histogram.
     */
    setConfig(config?: CosmographHistogramInputConfig<OutDatum, InDatum>): void;
    /**  `getCurrentSelection`: Returns current brush selection. */
    getCurrentSelection(): number[] | undefined;
    /**  `getCurrentSelectionInPixels`: Returns current brush selection in pixels. */
    getCurrentSelectionInPixels(): number[];
    /**  `getBarWidth`: Returns computed bar width in pixels */
    getBarWidth(): number;
    /**  `setSelection`: Set the selected range on a `Histogram`. Takes a numeric selection range in the X axis units as a parameter. */
    setSelection(selection?: [number, number]): void;
    /**
     * Returns current histogram configuration.
     */
    getConfig(): CosmographHistogramConfigInterface<OutDatum, InDatum>;
    /**
     * Destroy the histogram instance.
     */
    remove(): void;
    private _createHistogramConfig;
    private _updateDimension;
    private _applyFilter;
    private _updateData;
    private _updateDynamicData;
    private _onBrush;
    private _onBarHover;
}
export type { CosmographHistogramConfigInterface, CosmographHistogramInputConfig };
