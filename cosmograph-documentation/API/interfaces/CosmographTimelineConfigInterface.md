# Interface: CosmographTimelineConfigInterface

Extended by: CosmographTimelineConfig

Summary: Time range aggregation and selection control.

## Properties

- accessor?: string
  - Data column key for time values (ensure included appropriately).
  - Default: undefined

- customExtent?: [number, number]
  - Min and max extent for the timeline visualization.
  - Default: undefined

- useLinksData?: boolean
  - Use links data instead of points.
  - Default: false

- highlightSelectedData?: boolean
  - Highlight selected data on the timeline. Impacts performance.
  - Default: true

- onSelection?: (selection: undefined | [Date, Date] | [number, number], isManuallySelected?: boolean) => void
  - Callback providing current selection and whether it was manual.

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographTimelineConfigInterface
