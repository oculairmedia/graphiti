# Interface: CosmographPointsConfig

Extended by: CosmographDataConfig

Summary: Points (nodes) configuration including colors, sizes, labels, positions, and clustering.

## Properties

- points?: CosmographInputData
  - Input data for points.

- pointIdBy?: string
  - Unique identifier column for each point. Required for linking.

- pointIndexBy?: string
  - Numeric index column (0..n-1) for each point.

- pointColorBy?: string
  - Column for point color values (CSS color or [r,g,b,a]).

- pointColorByFn?: ColorAccessorFn<number | string | boolean | unknown>
  - Function to derive color from pointColorBy values.

- pointColorPalette?: string[]
  - Colors used with palette/interpolatePalette/degree strategies.

- pointColorByMap?: Record<string, string | [number, number, number, number]>
  - Value->color mapping used with 'map' strategy.

- pointColorStrategy?: 'palette' | 'interpolatePalette' | 'map' | 'degree' | 'direct' | undefined
  - Coloring strategy.

- pointSizeBy?: string
  - Column for numeric point sizes.

- pointSizeStrategy?: 'auto' | 'degree' | 'direct' | undefined
  - Sizing strategy.

- pointSizeRange?: [number, number]
  - Range for automatic sizing (default [2, 9]).

- pointSizeByFn?: SizeAccessorFn<number | string | boolean | unknown>
  - Function to derive size from pointSizeBy values.

- pointClusterBy?: string
  - Column with cluster assignments.

- pointClusterByFn?: (value: any, index?: number) => unknown
  - Function to derive cluster values from pointClusterBy.

- pointClusterStrengthBy?: string
  - Column controlling cluster attraction strength.

- pointLabelBy?: string
  - Column for labels.

- pointLabelWeightBy?: string
  - Column for label weight (priority).

- pointXBy?: string
  - Column for x-coordinate (used with pointYBy).

- pointYBy?: string
  - Column for y-coordinate.

- pointIncludeColumns?: string[]
  - Additional columns to include on point objects.

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographPointsConfig
