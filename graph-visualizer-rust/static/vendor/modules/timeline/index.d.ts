import { CosmosInputNode, CosmosInputLink } from '@cosmograph/cosmos';
import { Timeline } from '@cosmograph/ui';
import { Cosmograph } from '../cosmograph';
import { CosmographTimelineInputConfig, CosmographTimelineConfigInterface } from './config';
export declare class CosmographTimeline<Datum> {
    private _cosmograph;
    private _config;
    private _filter;
    timeline: Timeline;
    constructor(cosmograph: Cosmograph<CosmosInputNode, CosmosInputLink>, targetElement: HTMLElement, config?: CosmographTimelineInputConfig<Datum>);
    /**
     * Sets the configuration for the timeline.
     * @param config Configuration to be applied to the timeline.
     */
    setConfig(config?: CosmographTimelineInputConfig<Datum>): void;
    /**  `getCurrentSelection`: Returns current brush selection in data units (`Date` or `number`). */
    getCurrentSelection(): [Date, Date] | [number, number] | undefined;
    /**  `getCurrentSelectionInPixels`: Returns current brush selection in pixels. */
    getCurrentSelectionInPixels(): [number, number] | undefined;
    /**  `getBarWidth`: Returns computed bar width in pixels */
    getBarWidth(): number;
    /**  `getIsAnimationRunning`: Returns a boolean value indicating if the animation is running. */
    getIsAnimationRunning(): boolean;
    /**  `setSelection`: Set the selected range on a `Timeline`. Takes a selection range as a parameter, which can be a range of dates or a range of numbers if `TimelineData` is numeric. */
    setSelection(selectionRange?: [Date, Date] | [number, number]): void;
    /**  `setSelectionInPixels`: Set the selected range on a `Timeline` in pixels. Takes an array containing two numeric values representing selection range in pixels. */
    setSelectionInPixels(coordinates?: [number, number]): void;
    /**  `playAnimation`: If some interval is selected on `Timeline`, starts animation for it. The selected interval is moved forward by each timeline bar according to the speed passed in the `animationSpeed` of the `Timeline` `config`. */
    playAnimation: () => void;
    /**  `pauseAnimation`: Pauses animation of selected timeline interval. */
    pauseAnimation: () => void;
    /**  `stopAnimation`: Same as `pauseAnimation()`, but resets selection and returns `undefined` value for the `onBrush` callback. */
    stopAnimation: () => void;
    private _updateData;
    private _updateDimension;
    private _applyFilter;
    private _onBrush;
    private _onBarHover;
    private _onAnimationPlay;
    private _onAnimationPause;
    /**  `getConfig`: Returns current `Timeline` configuration */
    getConfig(): CosmographTimelineConfigInterface<Datum>;
    remove(): void;
    private _createTimelineConfig;
}
export type { CosmographTimelineConfigInterface, CosmographTimelineInputConfig };
