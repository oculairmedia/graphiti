# Interface: GraphConfigInterface

Summary: Core rendering, interaction, and simulation options for the Cosmograph renderer.

## Visuals
- backgroundColor?: string | [number, number, number, number] (default '#222222')
- pointColor?: string | [number, number, number, number] (default '#b3b3b3')
- pointGreyoutColor?: string | [number, number, number, number]
- pointGreyoutOpacity?: number
- pointOpacity?: number (default 1.0)
- linkColor?: string | [number, number, number, number] (default '#666666')
- linkOpacity?: number (default 1.0)
- linkGreyoutOpacity?: number (default 0.1)

## Sizing
- spaceSize?: number (default 8192)
- pointSize?: number (default 4)
- pointSizeScale?: number (default 1)
- linkWidth?: number (default 1)
- linkWidthScale?: number (default 1)
- linkArrowsSizeScale?: number (default 1)

## Links appearance
- renderLinks?: boolean (default true)
- scaleLinksOnZoom?: boolean (default false)
- curvedLinks?: boolean (default false)
- curvedLinkSegments?: number (default 19)
- curvedLinkWeight?: number (default 0.8)
- curvedLinkControlPointDistance?: number (default 0.5)
- linkArrows?: boolean (default false)
- linkVisibilityDistanceRange?: number[] (default [50, 150])
- linkVisibilityMinTransparency?: number (default 0.25)

## Interaction & Events
- hoveredPointCursor?: string (default 'auto')
- renderHoveredPointRing?: boolean (default false)
- hoveredPointRingColor?: string | [number, number, number, number] (default 'white')
- focusedPointRingColor?: string | [number, number, number, number] (default 'white')
- focusedPointIndex?: number
- onClick?: (index?: number, pointPosition?: [number, number], e: MouseEvent) => void
- onMouseMove?: (index?: number, pointPosition?: [number, number], e: MouseEvent) => void
- onPointMouseOver?: (index: number, pointPosition: [number, number], e: any) => void
- onPointMouseOut?: (e: any) => void
- onZoomStart?: (e: any, userDriven: boolean) => void
- onZoom?: (e: any, userDriven: boolean) => void
- onZoomEnd?: (e: any, userDriven: boolean) => void
- onDragStart?: (e: any) => void
- onDrag?: (e: any) => void
- onDragEnd?: (e: any) => void

## Simulation
- enableSimulation?: boolean (default true, init-only)
- useClassicQuadtree?: boolean (default false, init-only)
- simulationDecay?: number (default 5000)
- simulationGravity?: number (default 0.25)
- simulationCenter?: number (default 0)
- simulationRepulsion?: number (default 1.0)
- simulationRepulsionTheta?: number (default 1.15)
- simulationRepulsionQuadtreeLevels?: number (default 12, requires classic quadtree)
- simulationLinkSpring?: number (default 1)
- simulationLinkDistance?: number (default 10)
- simulationLinkDistRandomVariationRange?: number[] (default [1, 1.2])
- simulationRepulsionFromMouse?: number (default 2)
- enableRightClickRepulsion?: boolean (default false)
- simulationFriction?: number (default 0.85)
- simulationCluster?: number (default 0.1)
- onSimulationStart?: () => void
- onSimulationTick?: (alpha: number, hoveredIndex?: number, pointPosition?: [number, number]) => void
- onSimulationEnd?: () => void
- onSimulationPause?: () => void
- onSimulationRestart?: () => void

## Zoom & Fit
- pixelRatio?: number (default 2)
- scalePointsOnZoom?: boolean (default false)
- initialZoomLevel?: number (init-only)
- enableZoom?: boolean (default true)
- enableSimulationDuringZoom?: boolean (default false)
- enableDrag?: boolean (default false)
- fitViewOnInit?: boolean (default true)
- fitViewDelay?: number (default 250)
- fitViewPadding?: number (default 0.1)
- fitViewDuration?: number (default 250)
- fitViewByPointsInRect?: [number, number][] | [[number, number], [number, number]]

## Misc
- showFPSMonitor?: boolean (default false)
- randomSeed?: string | number (init-only)
- pointSamplingDistance?: number (default 150)
- rescalePositions?: boolean
- attribution?: string

Source: https://next.cosmograph.app/docs-lib/api/internal/interfaces/GraphConfigInterface
