import { HistogramConfig, type HistogramConfigInterface, type HistogramEvents } from './config';
export declare class Histogram {
    private _config;
    private _svg;
    private _containerNode;
    private _noDataDiv;
    private _resizeObserver;
    private _axisGroup;
    private _barsGroup;
    private _highlightedBarsGroup;
    private _brushGroup;
    private _firstRender;
    private _formatter;
    private _height;
    private _width;
    private _histogramWidth;
    private _histogramHeight;
    private _barWidth;
    private _maxCount;
    private _extent;
    private _barsData;
    private _highlightedBarsData;
    private _histogramData?;
    private _highlightedData?;
    private _bandIntervals;
    private _calculatedStep;
    private _currentSelection;
    private _currentSelectionInPixels;
    private _yScale;
    private _xScale;
    private _axis;
    private _brushInstance;
    constructor(containerNode: HTMLElement, config?: HistogramConfigInterface);
    private get _barPadding();
    /**  `getCurrentSelection`: Returns current brush selection. */
    get getCurrentSelection(): number[] | undefined;
    /**  `getCurrentSelectionInPixels`: Returns current brush selection in pixels. */
    get getCurrentSelectionInPixels(): number[];
    /**  `getBarWidth`: Returns computed bar width in pixels */
    getBarWidth(): number;
    /**  `getConfig`: Returns current `Histogram` configuration */
    getConfig(): HistogramConfig;
    /**  `setConfig`: Function for setting config of `Histogram`. */
    setConfig(config?: HistogramConfigInterface): void;
    /**  `setHistogramData`: Function for setting data of `Histogram`. */
    setHistogramData(data: number[] | undefined, customExtent?: [number, number]): void;
    /**  `setHighlightedData`: Function for setting highlighted data of `Histogram`. */
    setHighlightedData(data: number[] | undefined): void;
    /**  `setSelection`: Set the selected range on a `Histogram`. Takes a numeric selection range in the X axis u nits as a parameter. */
    setSelection(selection?: [number, number], renderOnly?: boolean): void;
    /**  `resize`: Resizes `Histogram` according to the parent node attributes. */
    resize(): void;
    /**  `render`: Renders `Histogram`. */
    render(): void;
    destroy(): void;
    private _updateAxis;
    private _updateBrush;
    private _updateBars;
    private _updateScales;
    private _disableBrush;
    private _updateHistogramData;
    private _updateHistogramHighlightedData;
    private _mapSelection;
    private _brushCurrentSelection;
    private _generateSequence;
    private _getClosestRange;
}
export { HistogramConfig };
export type { HistogramConfigInterface, HistogramEvents };
