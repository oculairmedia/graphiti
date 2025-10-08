# Cosmograph Master Documentation

## Table of Contents

1. [Overview](#overview)
2. [Installation & Setup](#installation--setup)
3. [Core Concepts](#core-concepts)
4. [API Reference](#api-reference)
5. [Components](#components)
6. [Configuration](#configuration)
7. [Data Management](#data-management)
8. [Examples](#examples)
9. [Advanced Usage](#advanced-usage)

## Overview

Cosmograph is a powerful JavaScript/React library for visualizing large graph datasets and machine learning embeddings. It provides blazingly fast network graph visualizations that run entirely in the browser, utilizing GPU acceleration for optimal performance.

### Key Features

- **High Performance**: GPU-accelerated rendering for large datasets
- **Browser-based**: No server required, all processing happens client-side
- **Multiple Formats**: Support for CSV, JSON, Parquet, Arrow formats
- **Interactive Components**: Timeline, Histogram, Search, Legends
- **Framework Support**: React components and vanilla JavaScript
- **TypeScript Support**: Full TypeScript definitions included

### What You Can Do

- Visualize network graphs and ML embeddings
- Explore temporal data evolution
- Identify communities and anomalies
- Filter and analyze with histograms
- Share and embed visualizations
- Analyze pre-calculated embeddings

## Installation & Setup

### React Installation

```bash
npm install @cosmograph/react@beta
```

### JavaScript Installation

```bash
npm install @cosmograph/cosmograph@beta
```

### Basic React Setup

```typescript
import { Cosmograph, CosmographConfig } from '@cosmograph/react'

export const Component = () => {
  const [cosmographConfig, setCosmographConfig] = useState<CosmographConfig>({
    // Configuration options
  })

  return <Cosmograph {...cosmographConfig} />
}
```

### Basic JavaScript Setup

```typescript
import { Cosmograph, CosmographConfig } from '@cosmograph/cosmograph'

// Create container element
const div = document.createElement('div')
document.body.appendChild(div)

// Define configuration
const cosmographConfig: CosmographConfig = {
  // Configuration options
}

// Create Cosmograph instance
const cosmograph = new Cosmograph(div, cosmographConfig)
```

## Core Concepts

### Data Requirements

Cosmograph requires pre-indexed data. The library provides the Cosmograph Data Kit for automatic data transformation.

### Supported Data Types

| Type | Description |
|------|-------------|
| `File` | CSV (.csv, .tsv), JSON (.json, max 100MB), Parquet (.parquet, .pq), Arrow (.arrow) |
| `string` | URL pointing to supported format |
| `Table` | Apache Arrow Table instance |
| `Uint8Array/ArrayBuffer` | Binary data in Apache Arrow format |
| `Record<string, unknown>[]` | Array of objects |

### Basic Data Structure

```typescript
// Points data
const rawPoints = [
  { id: 'a', color: '#88C6FF' },
  { id: 'b', color: '#FF99D2' },
  { id: 'c', color: '#7B61FF' }
]

// Links data
const rawLinks = [
  { source: 'a', target: 'b' },
  { source: 'b', target: 'c' },
  { source: 'c', target: 'a' }
]
```

## API Reference

### Main Classes

#### Cosmograph
The primary class for creating graph visualizations.

**Constructor Parameters:**
- `containerElement: HTMLElement` - Container for the visualization
- `config: CosmographConfig` - Configuration options
- `duckDbConnection?: WasmDuckDBConnection` - Optional database connection

**Key Methods:**
- `setConfig(config: CosmographConfig)` - Update configuration
- `setData(points, links)` - Set graph data
- `fitView()` - Fit graph to view
- `destroy()` - Clean up instance

### Configuration Interfaces

#### CosmographConfig
Main configuration interface for Cosmograph instances.

#### CosmographDataPrepConfig
Configuration for data preparation and mapping.

**Required Properties:**
- `points.pointIdBy: string` - Field containing unique point identifiers

**Optional Properties:**
- `links.linkSourceBy: string` - Source field for links
- `links.linkTargetsBy: string[]` - Target field(s) for links

### Data Preparation

#### prepareCosmographData()
Transforms raw data into Cosmograph-ready format.

```typescript
const { points, links, cosmographConfig } = await prepareCosmographData(
  dataConfig,
  rawPoints,
  rawLinks
)
```

**Returns:**
- `points` - Processed points data
- `links` - Processed links data
- `cosmographConfig` - Generated configuration
- `pointsSummary` - Points data aggregates
- `linksSummary` - Links data aggregates

## Components

Cosmograph provides various UI components for enhanced functionality:

### Core Components
- `Cosmograph` - Main graph visualization
- `CosmographBars` - Bar chart component
- `CosmographHistogram` - Histogram visualization
- `CosmographTimeline` - Timeline component
- `CosmographSearch` - Search functionality
- `CosmographPopup` - Popup/tooltip component

### Legend Components
- `CosmographRangeColorLegend` - Color range legend
- `CosmographTypeColorLegend` - Categorical color legend
- `CosmographSizeLegend` - Size legend

### Button Components
- `CosmographButtonFitView` - Fit to view button
- `CosmographButtonPlayPause` - Play/pause controls
- `CosmographButtonPolygonalSelection` - Polygonal selection tool
- `CosmographButtonRectangularSelection` - Rectangular selection tool
- `CosmographButtonZoomInOut` - Zoom controls

## Configuration

### Point Configuration
```typescript
interface CosmographPointsConfig {
  pointIdBy?: string
  pointColor?: ColorAccessorFn | string
  pointSize?: SizeAccessorFn | number
  pointOpacity?: number
  // Additional point properties
}
```

### Link Configuration
```typescript
interface CosmographLinksConfig {
  linkSourceBy?: string
  linkTargetsBy?: string[]
  linkColor?: ColorAccessorFn | string
  linkWidth?: SizeAccessorFn | number
  linkOpacity?: number
  // Additional link properties
}
```

### Simulation Configuration
```typescript
interface SimulationConfig {
  simulation?: boolean
  simulationGravity?: number
  simulationCenter?: number
  simulationRepulsion?: number
  simulationRepulsionTheta?: number
  simulationLinkDistance?: number
  simulationLinkSpring?: number
  simulationFriction?: number
  simulationDecay?: number
  // Additional simulation properties
}
```
