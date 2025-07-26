Interface: CosmographLinksConfig
Extended by
CosmographDataConfig
Properties
links?
optional links: CosmographInputData

The input data for the links.

CosmographInputData Accepts File | string | Table | Uint8Array | ArrayBuffer | Record<string, unknown>[]

linkSourceBy?
optional linkSourceBy: string

The column name for the source point of each link. This should match the pointIdBy values in the points data.

linkSourceIndexBy?
optional linkSourceIndexBy: string

The column name for the index of the source point of each link. This is used for efficient lookups and should match the pointIndexBy values in the points data.

linkTargetBy?
optional linkTargetBy: string

The column name for the target point of each link. This should match the pointIdBy values in the points data.

linkTargetIndexBy?
optional linkTargetIndexBy: string

The column name for the index of the target point of each link. This is used for efficient lookups and should match the pointIndexBy values in the points data.

linkColorBy?
optional linkColorBy: string

The column name for the link color.

If provided, links will be colored based on the values in this column, which should be either a color string or an array of numeric [r, g, b, a] values.

linkColorByFn?
optional linkColorByFn: ColorAccessorFn<number> | ColorAccessorFn<string> | ColorAccessorFn<boolean> | ColorAccessorFn<unknown>

Specifies the function that will be used to generate the color for each link based on the value in the linkColorBy column. It takes a link record as input and its index, and should return a color string or an array of [r, g, b, a] values.

Works only when linkColorBy is provided. Overrides the values in linkColorBy column by processing them (in this case the values in the linkColorBy column can be of any type, not just colors).

Param
The value from the LinkColor column.

Param
The index of the link.

Returns
The color as a string or an array of [r, g, b, a] value to be applied to the link.

linkWidthBy?
optional linkWidthBy: string

The column name for the link width.

If provided, links will have their widths set based on the values in this column, which should be numeric values.

linkWidthRange?
optional linkWidthRange: [number, number]

Defines the range for automatic link width scaling. Takes [min, max] values in pixels.

When linkWidthBy column contains numeric values, they will be automatically remapped to fit within this range to prevent oversized links if no linkWidthByFn provided.

Note: Only works when linkWidthBy column is provided and contains numeric values and when linkWidthByFn is not set.

Default
[1, 9]
linkWidthByFn?
optional linkWidthByFn: SizeAccessorFn<number> | SizeAccessorFn<string> | SizeAccessorFn<boolean> | SizeAccessorFn<unknown>

Specifies the function that will be used to generate the width for each link based on the value in the linkWidthBy column. It takes a link record as input and its index, and should return a numeric value.

Works only when linkWidthBy is provided. Overrides the values in the linkWidthBy column by processing them (in this case the values in the linkWidthBy column can be of any type, not just numbers).

Param
The value from the LinkWidth column.

Param
The index of the link.

Returns
The numeric width value to be applied to the link.

linkArrowBy?
optional linkArrowBy: string

The column name that determines whether a link should have an arrow. If provided, links will have arrows based on the boolean values in this column.

linkArrowByFn?
optional linkArrowByFn: BooleanAccessorFn<string> | BooleanAccessorFn<number> | BooleanAccessorFn<unknown>

Specifies the function that determines if a link should have an arrow based on the value in the linkArrowBy column. It takes a link record as input and its index, and should return a boolean value.

Works only when linkArrowBy is provided. Overrides the values in the linkArrowBy column by processing them (in this case the values in the linkArrowBy column can be of any type, not just booleans).

Param
The value from the LinkArrow column.

Param
The index of the link.

Returns
A boolean indicating whether the link should have an arrow.

linkStrengthBy?
optional linkStrengthBy: string

The column name for the link strength. If provided, links will have their strengths set based on the values in this column, which should be numeric values. Link strength affects the force simulation.

linkStrengthByFn?
optional linkStrengthByFn: SizeAccessorFn<number> | SizeAccessorFn<string> | SizeAccessorFn<boolean> | SizeAccessorFn<unknown>

Specifies the function that will be used to generate the strength for each link based on the value in the linkStrengthBy column. It takes a link record as input and its index, and should return a numeric value.

Works only when linkStrengthBy is provided. Overrides the values in the linkStrengthBy column by processing them (in this case the values in the linkStrengthBy column can be of any type, not just numbers).

Param
The value from the LinkStrength column.

Param
The index of the link.

Returns
The numeric strength value to be applied to the link.

linkStrengthRange?
optional linkStrengthRange: [number, number]

Defines the range for automatic link strength scaling. Takes [min, max] values in the range [0, 1].

This setting can be used to control the strength of the links during the simulation.

Note: Only works when linkStrength column is provided and contains numeric values and when linkStrengthFn is not set. Has effect only during the active simulation.

Default
[0.2, 1.0]
linkIncludeColumns?
optional linkIncludeColumns: string[]

An array of additional column names to include in the link data.

These columns will be available on the link objects but not used by Cosmograph directly, can be used as accessors for Cosmograph components. Useful for storing additional information about the links.

