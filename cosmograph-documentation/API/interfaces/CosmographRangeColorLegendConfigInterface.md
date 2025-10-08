# Interface: CosmographRangeColorLegendConfigInterface

Extended by: CosmographRangeColorLegendConfig

Summary: Configuration for numeric gradient color legend.

## Properties

- useLinksData?: boolean
  - Use links instead of points.
  - Default: false

- selectOnClick?: boolean
  - Select items with corresponding values on click.
  - Default: true

- steps?: number
  - Number of color gradations; divides accessor extent into steps. Overridden by overrideColors length.
  - Default: 10

- overrideColors?: RangeLegendColor[]
  - Custom color scheme array. Accepts RGBA tuples [r,g,b,a] or CSS color strings.

- useDiscreteColors?: boolean
  - Renders discrete bands instead of a gradient when overrideColors provided.
  - Default: false

- useQuantiles?: boolean
  - Use quantiles to compute legend min/max.

- hidden?: boolean
  - Hide the legend.
  - Default: false

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographRangeColorLegendConfigInterface
