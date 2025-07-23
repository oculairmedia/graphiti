import { Config } from '../../utils';
import type { BarData, Padding } from './types';
export declare const DEFAULT_PADDING: Padding;
export declare class TimelineConfig extends Config implements TimelineConfigInterface {
    allowSelection: boolean;
    showAnimationControls: boolean;
    animationSpeed: number;
    padding: Padding;
    axisTickHeight: number;
    selectionRadius: number;
    selectionPadding: number;
    barCount: number;
    barRadius: number;
    barPadding: number;
    barTopMargin: number;
    minBarHeight: number;
    dataStep: undefined;
    tickStep: undefined;
    formatter: (date: number | Date) => string;
    events: TimelineEvents;
}
export interface TimelineConfigInterface {
    /** `padding`: Padding between the outer edges of the timeline. Affects only timeline container without animation button. Set in pixels. Default: `{ top: 0, bottom: 0, left: 0, right: 0 }` */
    padding?: Padding;
    /** `axisTickHeight`: Height of the ticks that appear along the timeline axis. Set in pixels. Default: `25` */
    axisTickHeight?: number;
    /** `selectionRadius`: Corners roundness of the data selection brush. Set in pixels. Default: `3` */
    selectionRadius?: number;
    /** `selectionPadding`: Padding of the data selection brush. Set in pixels. Default: `8` */
    selectionPadding?: number;
    /** `barCount`: Number of bars to be displayed in the timeline. Ignored if `dataStep` is set. Default: `100` */
    barCount?: number;
    /** `barRadius`: Corners roundness of each bar on the timeline. Set in pixels. Default: `1` */
    barRadius?: number;
    /** `barPadding`: Padding between each bar on the timeline. Set in percent of bar width from 0 (as 0% of the bar width) to 1 (as 100% of the bar width). Default: `0.1` */
    barPadding?: number;
    /** `barTopMargin`: Margin between the top edge of the timeline and the maximum height bar. Set in pixels. Default: `3` */
    barTopMargin?: number;
    /** `minBarHeight`: Height of bars with an empty data on the timeline. Set in pixels. Default: `1` */
    minBarHeight?: number;
    /** `allowSelection`: Determines whether or not the timeline allows users to select a range of dates using a selection brush control. Default: `true` */
    allowSelection?: boolean;
    /** `showAnimationControls`: If set to true, shows an animation control button that allows to play or pause animation of selected range of dates. Default: `false` */
    showAnimationControls?: boolean;
    /** `animationSpeed`: Rate of refresh for each selection brush movement. Set in ms. Default: `50` */
    animationSpeed?: number;
    /** `dataStep`: Generate bars of width of this value mapped in the X axis units. Overrides `barCount`. Set in ms for `Date[]` data. Default: `undefined` */
    dataStep?: number;
    /** `tickStep`: Interval between each tick mark on the timeline axis. Set in the X axis units, in `ms` for `Date[]` timeline data or in relative units for `number[]` timeline data. Custom `dateFormat` may be required for the proper display of tick labels if the timeline data is `Date[]`. Default: `undefined` */
    tickStep?: number;
    /** `formatter`: Formatter function for ticks displayed on the timeline axis. */
    formatter?: (date: Date | number) => string;
    /** `events`: Events for the `Timeline` component */
    events?: TimelineEvents;
}
export interface TimelineEvents {
    /**  `onBrush`: Callback for the range selection. Provides current selection of `Timeline`. */
    onBrush?: (selection: [Date, Date] | [number, number] | undefined, isManuallySelected?: boolean) => void;
    /**  `onBarHover`: Callback that is called when a bar is hovered over. Provides `BarData` for hovered bar: `rangeStart`, `rangeEnd` and `count` of records in this bar. */
    onBarHover?: (data: BarData) => void;
    /**  `onAnimationPlay`: Callback for the animation play that will be executed in `playAnimation. Provides `isAnimationRunning` state and current selection of `Timeline`. */
    onAnimationPlay?: (isAnimationRunning: boolean, selection: (number | Date)[] | undefined) => void;
    /**  `onAnimationPause`: Callback for the animation play that will be executed in `pauseAnimation`. Provides `isAnimationRunning` state and current selection of `Timeline`. */
    onAnimationPause?: (isAnimationRunning: boolean, selection: (number | Date)[] | undefined) => void;
}
