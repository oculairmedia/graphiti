# Interface: CosmographSizeLegendConfigInterface

Extended by: CosmographSizeLegendConfig

Summary: Configuration for size legend.

## Properties

- useLinksData?: boolean
  - Use links instead of points.
  - Default: false

- hideWhenSizeMoreThan?: number
  - Hide the legend if derived size exceeds this value.

- selectOnClick?: boolean
  - Select items on click.
  - Default: true

- overrideExtent?: [number, number]
  - Custom [min, max] extent for the legend.

- useQuantiles?: boolean
  - Use quantiles to compute legend min/max.

- hidden?: boolean
  - Hide the legend.
  - Default: false

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographSizeLegendConfigInterface
