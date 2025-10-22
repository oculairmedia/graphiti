import { TimelineEvents, type TimelineConfigInterface } from '@cosmograph/ui';
import { FilterType } from '../cosmograph/types';
export type CosmographTimelineConfigInterface<Datum> = {
    /** `timeAccessor`: Data key to access time values from `L` data for the `CosmographTimeline`. Default: `date` */
    accessor?: (d: Datum) => Date | number;
    /** `filterType` Defines which types of Cosmograph Crossfilter to use.
     * Can only be set once during initialization. Default: `nodes` */
    filterType?: FilterType | string;
    /**  `onSelection`: Callback for the range selection. Provides current selection of `CosmographTimeline`. */
    onSelection?: Exclude<TimelineEvents['onBrush'], undefined>;
} & Omit<TimelineEvents, 'onBrush'>;
export declare const defaultCosmographTimelineConfig: CosmographTimelineConfigInterface<unknown>;
export type CosmographTimelineInputConfig<Datum> = CosmographTimelineConfigInterface<Datum> & Omit<TimelineConfigInterface, 'events'>;
