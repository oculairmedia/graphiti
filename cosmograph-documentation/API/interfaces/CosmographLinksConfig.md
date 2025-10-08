# Interface: CosmographLinksConfig

Extended by: CosmographDataConfig

Summary: Links (edges) configuration including color, width, arrows, and strength.

## Properties

- links?: CosmographInputData
  - Input data for links (File | string | Table | Uint8Array | ArrayBuffer | Record<string, unknown>[]).

- linkSourceBy?: string
  - Source point id column (matches pointIdBy).

- linkSourceIndexBy?: string
  - Source point index column (matches pointIndexBy).

- linkTargetBy?: string
  - Target point id column.

- linkTargetIndexBy?: string
  - Target point index column.

- linkColorBy?: string
  - Column for link color values.

- linkColorByFn?: ColorAccessorFn<number | string | boolean | unknown>
  - Function to derive link color from linkColorBy values.

- linkWidthBy?: string
  - Column for link width.

- linkWidthRange?: [number, number]
  - Range for automatic width scaling (default [1, 9]).

- linkWidthByFn?: SizeAccessorFn<number | string | boolean | unknown>
  - Function to derive width from linkWidthBy values.

- linkArrowBy?: string
  - Column determining whether to show arrow.

- linkArrowByFn?: BooleanAccessorFn<string | number | unknown>
  - Function to derive arrow boolean from linkArrowBy values.

- linkStrengthBy?: string
  - Column for link strength for simulation.

- linkStrengthByFn?: SizeAccessorFn<number | string | boolean | unknown>
  - Function to derive link strength from linkStrengthBy.

- linkStrengthRange?: [number, number]
  - Range for automatic strength scaling ([0, 1], default [0.2, 1.0]).

- linkIncludeColumns?: string[]
  - Additional columns to include on link objects.

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographLinksConfig
