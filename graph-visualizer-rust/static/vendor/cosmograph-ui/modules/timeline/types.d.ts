export type Padding = {
    top: number;
    left: number;
    bottom: number;
    right: number;
};
export type BarData = {
    rangeStart: Date | number;
    rangeEnd: Date | number;
    count: number;
};
export type BarsData = BarData[];
export type TimelineData = undefined | (number | Date)[];
