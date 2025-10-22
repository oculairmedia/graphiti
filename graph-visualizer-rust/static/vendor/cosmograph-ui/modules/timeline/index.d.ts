import 'd3-transition';
import { TimelineConfig, type TimelineEvents, type TimelineConfigInterface } from './config';
import type { TimelineData } from './types';
export declare class Timeline {
    private _animationInterval;
    private _isAnimationRunning;
    private _svgParser;
    private _svg;
    private _animationControlDiv;
    private _noDataDiv;
    private _playButtonSvg;
    private _pauseButtonSvg;
    private _containerNode;
    private _resizeObserver;
    private _axisGroup;
    private _barsGroup;
    private _brushGroup;
    private _height;
    private _width;
    private _timelineWidth;
    private _timelineHeight;
    private _config;
    private _barWidth;
    private _maxCount;
    private _barsData;
    private _timeData;
    private _dateExtent;
    private _bandIntervals;
    private _currentSelection;
    private _currentSelectionInPixels;
    private _isNumericTimeline;
    private _firstRender;
    private _yScale;
    private _timeScale;
    private _numScale;
    private _activeAxisScale;
    private _timeAxis;
    private _numAxis;
    private _brushInstance;
    constructor(containerNode: HTMLElement, config?: TimelineConfigInterface);
    private get _barPadding();
    /**  `getCurrentSelection`: Returns current brush selection in data units (`Date` or `number`). */
    getCurrentSelection(): [Date, Date] | [number, number] | undefined;
    /**  `getCurrentSelectionInPixels`: Returns current brush selection in pixels. */
    getCurrentSelectionInPixels(): [number, number] | undefined;
    /**  `getBarWidth`: Returns computed bar width in pixels */
    getBarWidth(): number;
    /**  `getConfig`: Returns current `Timeline` configuration */
    getConfig(): TimelineConfig;
    /**  `getIsAnimationRunning`: Returns a boolean value indicating if the animation is running. */
    getIsAnimationRunning(): boolean;
    /**  `setConfig`: Function for setting config of `Timeline`. */
    setConfig(config?: TimelineConfigInterface): void;
    /**  `setTimeData`: Function for setting data of `Timeline`. */
    setTimeData(timeData: TimelineData): void;
    private _getBarsData;
    private _updateTimelineData;
    /**  `setSelection`: Set the selected range on a `Timeline`. Takes a selection range as a parameter, which can be a range of dates or a range of numbers if `TimelineData` is numeric. */
    setSelection(selectionRange?: [Date, Date] | [number, number], renderOnly?: boolean): void;
    /**  `setSelectionInPixels`: Set the selected range on a `Timeline` in pixels. Takes an array containing two numeric values representing selection range in pixels. */
    setSelectionInPixels(coordinates?: [number, number]): void;
    /**  `resize`: Resizes `Timeline` according to the parent node attributes. */
    resize(): void;
    /**  `render`: Renders `Timeline`. */
    render(): void;
    private _updateAxis;
    private _updateBrush;
    private _updateBars;
    private _updateScales;
    private _disableBrush;
    private _initAnimationControls;
    private _toggleAnimation;
    private _disableAnimation;
    /**  `playAnimation`: If some interval is selected on `Timeline`, starts animation for it. The selected interval is moved forward by each timeline bar according to the speed passed in the `animationSpeed` of the `Timeline` `config`. */
    playAnimation: () => void;
    /**  `pauseAnimation`: Pauses animation of selected timeline interval. */
    pauseAnimation: () => void;
    /**  `stopAnimation`: Same as `pauseAnimation()`, but resets selection and returns `undefined` value for the `onBrush` callback. */
    stopAnimation: () => void;
    private _animateSelection;
    private _checkLastTickPosition;
    destroy: () => void;
}
export { TimelineConfig };
export type { TimelineData, TimelineConfigInterface, TimelineEvents };
