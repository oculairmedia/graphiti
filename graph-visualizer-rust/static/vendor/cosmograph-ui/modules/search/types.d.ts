export declare enum Events {
    Input = "input",
    Select = "select",
    Enter = "enter",
    AccessorSelect = "accessorSelect"
}
export type SearchData = {
    id: string;
    [key: string]: any;
};
export type AccessorOption<T extends SearchData> = {
    label: string;
    accessor: (d: T) => string;
};
export interface SearchEvents<T extends SearchData> {
    [Events.Input]: T[];
    [Events.Select]: T;
    [Events.Enter]: {
        textInput: string;
        accessor: AccessorOption<T>;
    };
    [Events.AccessorSelect]: {
        accessor: AccessorOption<T>;
        index: number;
    };
}
