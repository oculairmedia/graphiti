import type { AccessorOption, SearchData } from './types';
export type SearchConfigInterface<T extends SearchData> = {
    /** `isDisabled`: Makes `Search` component inactive.
     *
     * Default: `false` */
    isDisabled?: boolean;
    /** `minMatch`: The minimum characters needed to show suggestions.
     *
     * Default: `1` */
    minMatch?: number;
    /** `limitSuggestions`: The maximum number of suggestions shown. When the number of suggestions exceeds `limitSuggestions`, the rest of the suggestions will be omitteed. This can be tweaked to improve rendering performance is suggestion list is very long.
     *
     * If value is `undefined`, suggestions will not be limited.
     *
     * Default: `50` */
    limitSuggestions?: number;
    /** `truncateValues`: Maximum number of characters to be shown for each property of data object. When the number of characters exceeds `truncateValues`, the rest of the characters will be hidden. If value is `undefined`, full values will be shown.
     *
     * Default: `100` */
    truncateValues?: number;
    /** `maxVisibleItems`: The maximum items visible in the suggestions dropdown at once. When the number of suggestions exceeds `maxVisibleItems`, a scrollbar will be added to the dropdown list. `Search` will use height of first `maxVisibleItems` elements for suggestions dropdown.
     *
     * Default: `10` */
    maxVisibleItems?: number;
    /** `openListUpwards`: When set to `true` will open the dropdown list above the input field. If set to `false` the dropdown list will open below the input field.
     *
     * Default: `false` */
    openListUpwards?: boolean;
    /** `placeholder`: Specifies the placeholder text to be displayed in the search input field.
     *
     * Default: `Search` */
    placeholder?: string;
    /** `activeAccessorIndex`: Index of the currently active accessor function in the accessorOptions array. Used to programmatically set the selected accessor in the accessor dropdown.
     *
     * If `activeAccessorIndex` is set, the parent component should handle the `onAccessorSelect` callback to update when the selection changes.
     *
     * If `undefined`, controlling accessor selection will be performed be `Search` component.
     *
     * Default: `undefined`. */
    activeAccessorIndex?: number;
    /** `accessors`: An array of options that define how to access properties of the `SearchData<T>` for search input. The first item will be applied as default accessor to search. Can be switched via button that displays current active accessor. By default, first option of `accessors` array is used to process search input.
     *
     * Each option is an object with two properties:
     * - `label`: A string that represents the human-readable name of the property. This is used for display purposes in the UI.
     * - `accessor`: Function that retrieves a property of the `SearchData<T>` item that should be used for the search operation.
     *
     * Default: `[{ label: 'id', accessor: (n: SearchData) => n.id }]` */
    accessors?: AccessorOption<T>[];
    /** `ordering`: An object that specifies the order and inclusion of properties in the found data objects.
     *
     * - `order`: An array of strings defining the order of the properties in the search results. The strings should correspond to the properties of the search data or labels from `accessors` object.
     * - `include`: An array of strings specifying which accessor labels or/and properties of the search data should be included in the search results. If not provided, all properties of `SearchData<T>` will be included.
     *
     * If `ordering` is not provided, all properties of the given data object will be displayed, in their original order.
     *
     * Default: `undefined` */
    ordering?: {
        order?: string[];
        include?: string[];
    };
    /** `matchPalette`: Colors used to differentiate search results. The colors should be specified in a format that is recognized by CSS.
     *
     * Default: `['#fbb4ae80', '#b3cde380', '#ccebc580', '#decbe480', '#fed9a680', '#ffffcc80', '#e5d8bd80', '#fddaec80']` */
    matchPalette?: string[];
    /** `events`: Callback functions for search events.
     *
     * - `onSelect`: Function that will be called when the user selects an item from the suggestions list. Provides selected item as argument.
     * - `onSearch`: Function that will be called when the user inputs a search term. Provides an array of `SearchData<T>` items that match current search term as argument.
     * - `onEnter`: Function that will be called when the user hits Enter key in a search input. Provides current text content of search input field as argument. */
    events?: SearchEvents<T>;
};
export declare const defaultSearchConfig: SearchConfigInterface<SearchData>;
export interface SearchEvents<T extends SearchData> {
    /** `onSelect`: Function that will be called when the user selects an item from the suggestions list. Provides selected item as argument. */
    onSelect?: (foundMatch: T) => void;
    /** `onSearch`: Function that will be called when the user inputs a search term. Provides an array of `SearchData<T>` items that match current search term as argument. */
    onSearch?: (foundMatches?: T[]) => void;
    /** `onEnter`: Function that will be called when the user hits Enter key in a search input. Provides current text content of search input field and current accessor as arguments. */
    onEnter?: (input: string, accessor?: AccessorOption<T>) => void;
    /** `onAccessorSelect`: Function that will be called when the user selects an accessor from the dropdown list. Provides selected accessor as argument and its index in accessors list. */
    onAccessorSelect?: (accessor: {
        accessor: AccessorOption<T>;
        index: number;
    }) => void;
}
