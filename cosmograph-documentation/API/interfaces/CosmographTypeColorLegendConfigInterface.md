# Interface: CosmographTypeColorLegendConfigInterface

Extended by: CosmographTypeColorLegendConfig

Summary: Configuration for categorical color legend.

## Properties

- useLinksData?: boolean
  - Use links instead of points.
  - Default: false

- selectOnClick?: boolean
  - Select items on click.
  - Default: true

- overrideItems?: TypeColorLegendItem[]
  - Override legend items completely.

- sortBy?: string
  - Field to sort legend items by.

- sortOrder?: 'desc' | 'asc'
  - Sort order.

- hideUnknown?: boolean
  - Hide items for unknown values.
  - Default: true

- resetSelectionOnCollapse?: boolean
  - If collapsed, deselects items that became hidden.
  - Default: true

- hidden?: boolean
  - Hide the legend.
  - Default: false

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographTypeColorLegendConfigInterface
