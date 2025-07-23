import { Config } from '../../utils';
import type { BarData, Padding } from './types';
export declare const DEFAULT_PADDING: Padding;
export declare class HistogramConfig extends Config implements HistogramConfigInterface {
    padding: Padding;
    barsCount: number;
    barPadding: number;
    minBarHeight: number;
    selectionRadius: number;
    selectionPadding: number;
    barCount: number;
    dataStep: undefined;
    barRadius: number;
    barTopMargin: number;
    labelSideMargin: number;
    formatter: undefined;
    allowSelection: boolean;
    stickySelection: boolean;
    events: HistogramEvents;
}
export type HistogramConfigInterface = {
    /** `padding`: Padding for the `Histogram` component. */
    padding?: Padding;
    /** `minBarHeight`: Minimum height for each bar in the `Histogram` component. Default: `2` */
    minBarHeight?: number;
    /** `selectionPadding`: Padding for the data selection brush. Set in pixels. Default: `8` */
    selectionPadding?: number;
    /** `selectionRadius`: Radius of the data selection brush. Default: `3` */
    selectionRadius?: number;
    /** `barPadding`: Padding between each bar. Set in percent of bar width from 0 (as 0% of the bar width) to 1 (as 100% of the bar width). Default: `0.1`. */
    barPadding?: number;
    /** `barRadius`: Corners roundness of each bar in the `Histogram`. Set in pixels. Default: `1` */
    barRadius?: number;
    /** `barCount`: Number of bars to be displayed in the `Histogram`. Ignored if `dataStep` is set. Default: `100` */
    barCount?: number;
    /** `barTopMargin`: Margin between the top edge of the `Histogram` and the maximum height bar. Set in pixels. Default: `3` */
    barTopMargin?: number;
    /** `dataStep`: Option to generate bars of a specified width in the X axis units. Overrides `barCount`. Default: `undefined` */
    dataStep?: number;
    /** `allowSelection`: Determines whether or not the `Histogram` allows users to select bars using a selection brush control. Default: `true` */
    allowSelection?: boolean;
    /** `stickySelection`: Stick selection brush coodrinates to the bar edges. Default: `true` */
    stickySelection?: boolean;
    /** `labelSideMargin`: Adjust the margin between the axis tick edge labels and the horizontal edges of the `Histogram` component bounding box. Default: `3` */
    labelSideMargin?: number;
    /** `formatter`: Function to format the axis tick edge labels in the Histogram component. */
    formatter?: (n: number) => string;
    /** `events`: Events for the `Histogram` component. */
    events?: HistogramEvents;
};
export interface HistogramEvents {
    /**  `onBrush`: Callback for the range selection. Provides current selection of `Histogram`. */
    onBrush?: (selection: [number, number] | undefined, isManuallySelected?: boolean) => void;
    /**  `onBarHover`: Callback that is called when a bar is hovered over. Provides `BarData` for hovered bar: `rangeStart`, `rangeEnd` and `count` of records in this bar. */
    onBarHover?: (data: BarData) => void;
}
