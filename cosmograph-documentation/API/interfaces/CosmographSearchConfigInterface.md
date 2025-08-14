# Interface: CosmographSearchConfigInterface<T>

Extends: Omit<SearchConfigInterface<T>, "placeholderRenderer">
Extended by: CosmographSearchConfig

Summary: Configuration for autosuggest search, with optional accessor-bound behavior and UI.

## Properties

- accessor?: string
  - Data column key to access values for search (ensure included in pointIncludeColumns if needed).
  - Default: undefined

- placeholderText?: string
  - Placeholder text in input.
  - Default: 'Search...'

- showAccessorsMenu?: boolean
  - Toggle the accessors menu.
  - Default: true

- suggestionFields?: Record<string, string>
  - Map of field -> display label for suggestions.

- suggestionFieldsPalette?: string[]
  - Colors used to render suggestion field chips.
  - Default: ['#fbb4aebf', '#b3cde3bf', '#ccebc5bf', '#decbe4bf', '#fed9a6bf', '#ffffccbf', '#e5d8bdbf', '#fddaecbf']

- disabled?: boolean (inherited)
  - Disable the search.
  - Default: false

- openListUpwards?: boolean (inherited)
  - Open suggestion list upwards.
  - Default: false

- onInput?: (value: string, results: T[], event: InputEvent) => void (inherited)

- debounceTime?: number (inherited)
  - Default: 300

- searchFn?: (query: string, limit?: number) => Promise<T[]> (inherited)

- suggestionsLimit?: number (inherited)
  - Default: 50

- maxVisibleItems?: number (inherited)
  - Default: 10

- onSelect?: (suggestion: T) => void (inherited)

- suggestionRenderer?: (suggestion: T, value?: string) => string | HTMLElement (inherited)

- selectedSuggestionRenderer?: (suggestion: T, value?: string) => string (inherited)

- inputClassName?: string (inherited)

- suggestionListClassName?: string (inherited)

- minSearchLength?: number (inherited)
  - Default: 2

- onEnter?: (value: string, results: T[]) => void (inherited)

- highlightMatch?: boolean (inherited)
  - Default: true

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/CosmographSearchConfigInterface
