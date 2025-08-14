# Interfaces

- SelectionComponentConfig
- SelectionUIComponent
- CosmographBarsConfigInterface
- CosmographHistogramConfigInterface
- CosmographRangeColorLegendConfigInterface
- CosmographTypeColorLegendConfigInterface
- CosmographSizeLegendConfigInterface
- CosmographSearchConfigInterface
- CosmographTimelineConfigInterface
- BasicConfig
- CallbackConfig
- CosmographPointsConfig
- CosmographLinksConfig
- CosmographClustersConfig
- CosmographDataConfig
- LabelsCosmographConfig
- SimulationConfig
- SimulationEventConfig
- Crossfilter
- FilteringClientConfig
- ICosmographInternalApi
- ICosmograph
- OutputCosmographDataPrepConfig
- CosmographDataPrepPointsConfig
- CosmographDataPrepLinksConfig
- DisplayStateConfigInterface
- BarData
- ButtonConfigInterface
- RangeColorLegendConfigInterface
- TypeColorLegendConfigInterface
- SizeLegendConfigInterface
- SearchConfigInterface
- TimelineConfigInterface
- GraphConfigInterface

## Notable Properties by Interface

Below are key properties gathered from publicly available docs and examples. For a complete list, refer to the official docs.

### CosmographPointsConfig
- pointIdBy: string
- pointColor?: ColorAccessorFn | string
- pointSize?: SizeAccessorFn | number
- pointOpacity?: number

### CosmographLinksConfig
- linkSourceBy?: string
- linkTargetsBy?: string[]
- linkColor?: ColorAccessorFn | string
- linkWidth?: SizeAccessorFn | number
- linkOpacity?: number

### SimulationConfig
- simulation?: boolean
- simulationGravity?: number
- simulationCenter?: number
- simulationRepulsion?: number
- simulationRepulsionTheta?: number
- simulationLinkDistance?: number
- simulationLinkSpring?: number
- simulationFriction?: number
- simulationDecay?: number

### ICosmograph (selected capabilities)
- setConfig(config: CosmographConfig): void
- setData(points, links): void
- fitView(): void
- destroy(): void

