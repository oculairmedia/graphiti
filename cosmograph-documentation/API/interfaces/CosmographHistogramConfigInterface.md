# Interface: CosmographHistogramConfigInterface

Extended by: CosmographHistogramConfig

Summary: Configuration for CosmographHistogram, a numeric distribution histogram linked to Crossfilter.

## Properties

- accessor?: string
  - Data column key to access numeric values for the histogram. Include it in pointIncludeColumns/linkIncludeColumns if not used elsewhere.
  - Default: undefined

- customExtent?: [number, number]
  - Min and max extent for the histogram visualization.
  - Default: undefined

- useLinksData?: boolean
  - Use links data instead of points.
  - Default: false

- highlightSelectedData?: boolean
  - Highlight the currently selected data on histogram. Impacts performance.
  - Default: true

- onSelection?: (selection: undefined | [number, number], isManuallySelected?: boolean) => void
  - Callback with current selection range and whether it was set manually.

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographHistogramConfigInterface
