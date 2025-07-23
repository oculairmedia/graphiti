export declare const isNumber: <T>(a: T) => boolean;
export declare const isFunction: <T>(a: T) => boolean;
export declare const isUndefined: <T>(a: T) => boolean;
export declare const isNil: <T>(a: T) => boolean;
export declare const isString: <T>(a: T) => boolean;
export declare const isArray: <T>(a: T) => boolean;
export declare const isObject: <T>(a: T) => boolean;
export declare const isAClassInstance: <T>(a: T) => boolean;
export declare const isPlainObject: <T>(a: T) => boolean;
export declare const cloneDeep: <T>(obj: T, stack?: Map<any, any>) => T;
export declare const merge: <T, K>(obj1: T, obj2: K, visited?: Map<any, any>) => T & K;
export declare const isBetween: (num: number, min: number, max: number) => boolean;
export declare const getCountsInRange: (valuesMap: Map<number | Date, number>, range: [Date | number, Date | number]) => number;
export declare const getInnerDimensions: (node: HTMLElement) => {
    width: number;
    height: number;
};
export declare class Config {
    init<T extends Record<string | number, any>>(config: T): this;
}
