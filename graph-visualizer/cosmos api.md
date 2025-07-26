https://next.cosmograph.app/docs/lib/api/classes/CosmographBars/  https://next.cosmograph.app/docs/lib/api/classes/CosmographButtonFitView/                                           │
│   https://next.cosmograph.app/docs/lib/api/classes/CosmographButtonPlayPause/ https://next.cosmograph.app/docs/lib/api/classes/CosmographButtonPolygonalSelection/                      │
│   https://next.cosmograph.app/docs/lib/api/classes/CosmographButtonRectangularSelection/ https://next.cosmograph.app/docs/lib/api/classes/CosmographButtonZoomInOut/                    │
│   https://next.cosmograph.app/docs/lib/api/classes/CosmographHistogram/ https://next.cosmograph.app/docs/lib/api/classes/CosmographPopup/                                               │
│   https://next.cosmograph.app/docs/lib/api/classes/CosmographRangeColorLegend/ https://next.cosmograph.app/docs/lib/api/classes/CosmographSearch/                                       │
│   https://next.cosmograph.app/docs/lib/api/classes/CosmographSizeLegend/ https://next.cosmograph.app/docs/lib/api/classes/CosmographTimeline/                                           │
│   https://next.cosmograph.app/docs/lib/api/classes/CosmographTypeColorLegend/ https://next.cosmograph.app/docs/lib/api/interfaces/CosmographBarsConfig/                                 │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographButtonFitViewConfigInterface/                                                                                           │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographButtonPlayPauseConfigInterface/                                                                                         │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographButtonPolygonalSelectionConfigInterface/                                                                                │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographButtonRectangularSelectionConfigInterface/                                                                              │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographButtonZoomInOutConfigInterface https://next.cosmograph.app/docs/lib/api/interfaces/CosmographConfig/                    │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographDataPrepConfig/ https://next.cosmograph.app/docs/lib/api/interfaces/CosmographDataPrepResult/                           │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographHistogramConfig/ https://next.cosmograph.app/docs/lib/api/interfaces/CosmographPopupConfig/                             │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographRangeColorLegendConfig/ https://next.cosmograph.app/docs/lib/api/interfaces/CosmographSearchConfig/                     │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographSizeLegendConfig/ https://next.cosmograph.app/docs/lib/api/interfaces/CosmographTimelineConfig/                         │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographTypeColorLegendConfig/ https://next.cosmograph.app/docs/lib/api/enumerations/CosmographPointColorStrategy/              │
│   https://next.cosmograph.app/docs/lib/api/enumerations/CosmographPointSizeStrategy/ https://next.cosmograph.app/docs/lib/api/type-aliases/CosmographCustomLabel/                       │
│   https://next.cosmograph.app/docs/lib/api/type-aliases/CosmographData/ https://next.cosmograph.app/docs/lib/api/type-aliases/CosmographInputData/                                      │
│   https://next.cosmograph.app/docs/lib/api/type-aliases/WasmDuckDBConnection/ https://next.cosmograph.app/docs/lib/api/functions/downloadCosmographData/                                │
│   https://next.cosmograph.app/docs/lib/api/functions/prepareCosmographData/ https://next.cosmograph.app/docs/lib/api/functions/prepareCosmographDataFiles/                              │
│   https://next.cosmograph.app/docs/lib/api/interfaces/CosmographConfig/ https://next.cosmograph.app/docs/lib/api/internal/interfaces/CosmographDataConfig/     
JavaScript & React library
API
Class: Graph
Constructors
Constructor
new Graph(div, config?): Graph

Parameters
Parameter	Type
div	HTMLDivElement
config?	GraphConfigInterface
Returns
Graph

Properties
Property	Type
config	GraphConfig
graph	GraphData
Accessors
progress
get progress(): number

Returns the current simulation progress

Returns
number

isSimulationRunning
get isSimulationRunning(): boolean

A value that gives information about the running simulation status.

Returns
boolean

maxPointSize
get maxPointSize(): number

The maximum point size. This value is the maximum size of the gl.POINTS primitive that WebGL can render on the user’s hardware.

Returns
number

Methods
setConfig()
setConfig(config): void

Set or update Cosmos configuration. The changes will be applied in real time.

Parameters
Parameter	Type	Description
config	Partial<GraphConfigInterface>	Cosmos configuration object.
Returns
void

setPointPositions()
setPointPositions(pointPositions, dontRescale?): void

Sets the positions for the graph points.

Parameters
Parameter	Type	Description
pointPositions	Float32Array	A Float32Array representing the positions of points in the format [x1, y1, x2, y2, …, xn, yn], where n is the index of the point. Example: new Float32Array([1, 2, 3, 4, 5, 6]) sets the first point to (1, 2), the second point to (3, 4), and so on.
dontRescale?	boolean	For this call only, don’t rescale the points. - true: Don’t rescale. - false or undefined (default): Use the behavior defined by config.rescalePositions.
Returns
void

setPointColors()
setPointColors(pointColors): void

Sets the colors for the graph points.

Parameters
Parameter	Type	Description
pointColors	Float32Array	A Float32Array representing the colors of points in the format [r1, g1, b1, a1, r2, g2, b2, a2, …, rn, gn, bn, an], where each color is represented in RGBA format. Example: new Float32Array([255, 0, 0, 1, 0, 255, 0, 1]) sets the first point to red and the second point to green.
Returns
void

getPointColors()
getPointColors(): Float32Array

Gets the current colors of the graph points.

Returns
Float32Array

A Float32Array representing the colors of points in the format [r1, g1, b1, a1, r2, g2, b2, a2, …, rn, gn, bn, an], where each color is in RGBA format. Returns an empty Float32Array if no point colors are set.

setPointSizes()
setPointSizes(pointSizes): void

Sets the sizes for the graph points.

Parameters
Parameter	Type	Description
pointSizes	Float32Array	A Float32Array representing the sizes of points in the format [size1, size2, …, sizen], where n is the index of the point. Example: new Float32Array([10, 20, 30]) sets the first point to size 10, the second point to size 20, and the third point to size 30.
Returns
void

getPointSizes()
getPointSizes(): Float32Array

Gets the current sizes of the graph points.

Returns
Float32Array

A Float32Array representing the sizes of points in the format [size1, size2, …, sizen], where n is the index of the point. Returns an empty Float32Array if no point sizes are set.

setLinks()
setLinks(links): void

Sets the links for the graph.

Parameters
Parameter	Type	Description
links	Float32Array	A Float32Array representing the links between points in the format [source1, target1, source2, target2, …, sourcen, targetn], where source and target are the indices of the points being linked. Example: new Float32Array([0, 1, 1, 2]) creates a link from point 0 to point 1 and another link from point 1 to point 2.
Returns
void

setLinkColors()
setLinkColors(linkColors): void

Sets the colors for the graph links.

Parameters
Parameter	Type	Description
linkColors	Float32Array	A Float32Array representing the colors of links in the format [r1, g1, b1, a1, r2, g2, b2, a2, …, rn, gn, bn, an], where each color is in RGBA format. Example: new Float32Array([255, 0, 0, 1, 0, 255, 0, 1]) sets the first link to red and the second link to green.
Returns
void

getLinkColors()
getLinkColors(): Float32Array

Gets the current colors of the graph links.

Returns
Float32Array

A Float32Array representing the colors of links in the format [r1, g1, b1, a1, r2, g2, b2, a2, …, rn, gn, bn, an], where each color is in RGBA format. Returns an empty Float32Array if no link colors are set.

setLinkWidths()
setLinkWidths(linkWidths): void

Sets the widths for the graph links.

Parameters
Parameter	Type	Description
linkWidths	Float32Array	A Float32Array representing the widths of links in the format [width1, width2, …, widthn], where n is the index of the link. Example: new Float32Array([1, 2, 3]) sets the first link to width 1, the second link to width 2, and the third link to width 3.
Returns
void

getLinkWidths()
getLinkWidths(): Float32Array

Gets the current widths of the graph links.

Returns
Float32Array

A Float32Array representing the widths of links in the format [width1, width2, …, widthn], where n is the index of the link. Returns an empty Float32Array if no link widths are set.

setLinkArrows()
setLinkArrows(linkArrows): void

Sets the arrows for the graph links.

Parameters
Parameter	Type	Description
linkArrows	boolean[]	An array of booleans indicating whether each link should have an arrow, in the format [arrow1, arrow2, …, arrown], where n is the index of the link. Example: [true, false, true] sets arrows on the first and third links, but not on the second link.
Returns
void

setLinkStrength()
setLinkStrength(linkStrength): void

Sets the strength for the graph links.

Parameters
Parameter	Type	Description
linkStrength	Float32Array	A Float32Array representing the strength of each link in the format [strength1, strength2, …, strengthn], where n is the index of the link. Example: new Float32Array([1, 2, 3]) sets the first link to strength 1, the second link to strength 2, and the third link to strength 3.
Returns
void

setPointClusters()
setPointClusters(pointClusters): void

Sets the point clusters for the graph.

Parameters
Parameter	Type	Description
pointClusters	(undefined | number)[]	Array of cluster indices for each point in the graph. - Index: Each index corresponds to a point. - Values: Integers starting from 0; undefined indicates that a point does not belong to any cluster and will not be affected by cluster forces.
Returns
void

Example
`[0, 1, 0, 2, undefined, 1]` maps points to clusters: point 0 and 2 to cluster 0, point 1 to cluster 1, and point 3 to cluster 2.
Points 4 is unclustered.
Note
Clusters without specified positions via setClusterPositions will be positioned at their centermass by default.

setClusterPositions()
setClusterPositions(clusterPositions): void

Sets the positions of the point clusters for the graph.

Parameters
Parameter	Type	Description
clusterPositions	(undefined | number)[]	Array of cluster positions. - Every two elements represent the x and y coordinates for a cluster position. - undefined means the cluster’s position is not defined and will use centermass positioning instead.
Returns
void

Example
`[10, 20, 30, 40, undefined, undefined]` places the first cluster at (10, 20) and the second at (30, 40);
the third cluster will be positioned at its centermass automatically.
setPointClusterStrength()
setPointClusterStrength(clusterStrength): void

Sets the force strength coefficients for clustering points in the graph.

This method allows you to customize the forces acting on individual points during the clustering process. The force coefficients determine the strength of the forces applied to each point.

Parameters
Parameter	Type	Description
clusterStrength	Float32Array	A Float32Array of force strength coefficients for each point in the format [coeff1, coeff2, …, coeffn], where n is the index of the point. Example: new Float32Array([1, 0.4, 0.3]) sets the force coefficient for point 0 to 1, point 1 to 0.4, and point 2 to 0.3.
Returns
void

render()
render(simulationAlpha?): void

Renders the graph.

Parameters
Parameter	Type	Description
simulationAlpha?	number	Optional value between 0 and 1 that controls the initial energy of the simulation.The higher the value, the more initial energy the simulation will get. Zero value stops the simulation.
Returns
void

zoomToPointByIndex()
zoomToPointByIndex(index, duration?, scale?, canZoomOut?): void

Center the view on a point and zoom in, by point index.

Parameters
Parameter	Type	Description
index	number	The index of the point in the array of points.
duration?	number	Duration of the animation transition in milliseconds (700 by default).
scale?	number	Scale value to zoom in or out (3 by default).
canZoomOut?	boolean	Set to false to prevent zooming out from the point (true by default).
Returns
void

zoom()
zoom(value, duration?): void

Zoom the view in or out to the specified zoom level.

Parameters
Parameter	Type	Description
value	number	Zoom level
duration?	number	Duration of the zoom in/out transition.
Returns
void

setZoomLevel()
setZoomLevel(value, duration?): void

Zoom the view in or out to the specified zoom level.

Parameters
Parameter	Type	Description
value	number	Zoom level
duration?	number	Duration of the zoom in/out transition.
Returns
void

getZoomLevel()
getZoomLevel(): number

Get zoom level.

Returns
number

Zoom level value of the view.

getPointPositions()
getPointPositions(): number[]

Get current X and Y coordinates of the points.

Returns
number[]

Array of point positions.

getClusterPositions()
getClusterPositions(): number[]

Get current X and Y coordinates of the clusters.

Returns
number[]

Array of point cluster.

fitView()
fitView(duration?, padding?): void

Center and zoom in/out the view to fit all points in the scene.

Parameters
Parameter	Type	Description
duration?	number	Duration of the center and zoom in/out animation in milliseconds (250 by default).
padding?	number	Padding around the viewport in percentage (0.1 by default).
Returns
void

fitViewByPointIndices()
fitViewByPointIndices(indices, duration?, padding?): void

Center and zoom in/out the view to fit points by their indices in the scene.

Parameters
Parameter	Type	Description
indices	number[]	-
duration?	number	Duration of the center and zoom in/out animation in milliseconds (250 by default).
padding?	number	Padding around the viewport in percentage
Returns
void

fitViewByPointPositions()
fitViewByPointPositions(positions, duration?, padding?): void

Center and zoom in/out the view to fit points by their positions in the scene.

Parameters
Parameter	Type	Description
positions	number[]	-
duration?	number	Duration of the center and zoom in/out animation in milliseconds (250 by default).
padding?	number	Padding around the viewport in percentage
Returns
void

getPointsInRect()
getPointsInRect(selection): Float32Array

Get points indices inside a rectangular area.

Parameters
Parameter	Type	Description
selection	[[number, number], [number, number]]	Array of two corner points [[left, top], [right, bottom]]. The left and right coordinates should be from 0 to the width of the canvas. The top and bottom coordinates should be from 0 to the height of the canvas.
Returns
Float32Array

A Float32Array containing the indices of points inside a rectangular area.

getPointsInRange()
getPointsInRange(selection): Float32Array

Get points indices inside a rectangular area.

Parameters
Parameter	Type	Description
selection	[[number, number], [number, number]]	Array of two corner points [[left, top], [right, bottom]]. The left and right coordinates should be from 0 to the width of the canvas. The top and bottom coordinates should be from 0 to the height of the canvas.
Returns
Float32Array

A Float32Array containing the indices of points inside a rectangular area.

Deprecated
Use getPointsInRect instead. This method will be removed in a future version.

getPointsInPolygon()
getPointsInPolygon(polygonPath): Float32Array

Get points indices inside a polygon area.

Parameters
Parameter	Type	Description
polygonPath	[number, number][]	Array of points [[x1, y1], [x2, y2], ..., [xn, yn]] that defines the polygon. The coordinates should be from 0 to the width/height of the canvas.
Returns
Float32Array

A Float32Array containing the indices of points inside the polygon area.

selectPointsInRect()
selectPointsInRect(selection): void

Select points inside a rectangular area.

Parameters
Parameter	Type	Description
selection	null | [[number, number], [number, number]]	Array of two corner points [[left, top], [right, bottom]]. The left and right coordinates should be from 0 to the width of the canvas. The top and bottom coordinates should be from 0 to the height of the canvas.
Returns
void

selectPointsInRange()
selectPointsInRange(selection): void

Select points inside a rectangular area.

Parameters
Parameter	Type	Description
selection	null | [[number, number], [number, number]]	Array of two corner points [[left, top], [right, bottom]]. The left and right coordinates should be from 0 to the width of the canvas. The top and bottom coordinates should be from 0 to the height of the canvas.
Returns
void

Deprecated
Use selectPointsInRect instead. This method will be removed in a future version.

selectPointsInPolygon()
selectPointsInPolygon(polygonPath): void

Select points inside a polygon area.

Parameters
Parameter	Type	Description
polygonPath	null | [number, number][]	Array of points [[x1, y1], [x2, y2], ..., [xn, yn]] that defines the polygon. The coordinates should be from 0 to the width/height of the canvas. Set to null to clear selection.
Returns
void

selectPointByIndex()
selectPointByIndex(index, selectAdjacentPoints?): void

Select a point by index. If you want the adjacent points to get selected too, provide true as the second argument.

Parameters
Parameter	Type	Description
index	number	The index of the point in the array of points.
selectAdjacentPoints?	boolean	When set to true, selects adjacent points (false by default).
Returns
void

selectPointsByIndices()
selectPointsByIndices(indices?): void

Select multiples points by their indices.

Parameters
Parameter	Type	Description
indices?	null | (undefined | number)[]	Array of points indices.
Returns
void

unselectPoints()
unselectPoints(): void

Unselect all points.

Returns
void

getSelectedIndices()
getSelectedIndices(): null | number[]

Get indices of points that are currently selected.

Returns
null | number[]

Array of selected indices of points.

getAdjacentIndices()
getAdjacentIndices(index): undefined | number[]

Get indices that are adjacent to a specific point by its index.

Parameters
Parameter	Type	Description
index	number	Index of the point.
Returns
undefined | number[]

Array of adjacent indices.

spaceToScreenPosition()
spaceToScreenPosition(spacePosition): [number, number]

Converts the X and Y point coordinates from the space coordinate system to the screen coordinate system.

Parameters
Parameter	Type	Description
spacePosition	[number, number]	Array of x and y coordinates in the space coordinate system.
Returns
[number, number]

Array of x and y coordinates in the screen coordinate system.

screenToSpacePosition()
screenToSpacePosition(screenPosition): [number, number]

Converts the X and Y point coordinates from the screen coordinate system to the space coordinate system.

Parameters
Parameter	Type	Description
screenPosition	[number, number]	Array of x and y coordinates in the screen coordinate system.
Returns
[number, number]

Array of x and y coordinates in the space coordinate system.

spaceToScreenRadius()
spaceToScreenRadius(spaceRadius): number

Converts the point radius value from the space coordinate system to the screen coordinate system.

Parameters
Parameter	Type	Description
spaceRadius	number	Radius of point in the space coordinate system.
Returns
number

Radius of point in the screen coordinate system.

getPointRadiusByIndex()
getPointRadiusByIndex(index): undefined | number

Get point radius by its index.

Parameters
Parameter	Type	Description
index	number	Index of the point.
Returns
undefined | number

Radius of the point.

trackPointPositionsByIndices()
trackPointPositionsByIndices(indices): void

Track multiple point positions by their indices on each Cosmos tick.

Parameters
Parameter	Type	Description
indices	number[]	Array of points indices.
Returns
void

getTrackedPointPositionsMap()
getTrackedPointPositionsMap(): Map<number, [number, number]>

Get current X and Y coordinates of the tracked points.

Returns
Map<number, [number, number]>

A Map object where keys are the indices of the points and values are their corresponding X and Y coordinates in the [number, number] format.

getTrackedPointPositionsArray()
getTrackedPointPositionsArray(): number[]

Get current X and Y coordinates of the tracked points as an array.

Returns
number[]

Array of point positions in the format [x1, y1, x2, y2, …, xn, yn] for tracked points only. The positions are ordered by the tracking indices (same order as provided to trackPointPositionsByIndices). Returns an empty array if no points are being tracked.

getSampledPointPositionsMap()
getSampledPointPositionsMap(): Map<number, [number, number]>

For the points that are currently visible on the screen, get a sample of point indices with their coordinates. The resulting number of points will depend on the pointSamplingDistance configuration property, and the sampled points will be evenly distributed.

Returns
Map<number, [number, number]>

A Map object where keys are the index of the points and values are their corresponding X and Y coordinates in the [number, number] format.

getSampledPoints()
getSampledPoints(): object

For the points that are currently visible on the screen, get a sample of point indices and positions. The resulting number of points will depend on the pointSamplingDistance configuration property, and the sampled points will be evenly distributed.

Returns
object

An object containing arrays of point indices and positions.

Name	Type
indices	number[]
positions	number[]
getScaleX()
getScaleX(): undefined | (x) => number

Gets the X-axis of rescaling function.

This scale is automatically created when position rescaling is enabled.

Returns
undefined | (x) => number

getScaleY()
getScaleY(): undefined | (y) => number

Gets the Y-axis of rescaling function.

This scale is automatically created when position rescaling is enabled.

Returns
undefined | (y) => number

start()
start(alpha?): void

Start the simulation.

Parameters
Parameter	Type	Description
alpha?	number	Value from 0 to 1. The higher the value, the more initial energy the simulation will get.
Returns
void

pause()
pause(): void

Pause the simulation.

Returns
void

restart()
restart(): void

Restart the simulation.

Returns
void

step()
step(): void

Render only one frame of the simulation (stops the simulation if it was running).

Returns
void

destroy()
destroy(): void

Destroy this Cosmos instance.

Returns
void

create()
create(): void

Updates and recreates the graph visualization based on pending changes.

Returns
void

flatten()
flatten(pointPositions): number[]

Converts an array of tuple positions to a single array containing all coordinates sequentially

Parameters
Parameter	Type	Description
pointPositions	[number, number][]	An array of tuple positions
Returns
number[]

A flatten array of coordinates

pair()
pair(pointPositions): [number, number][]

Converts a flat array of point positions to a tuple pairs representing coordinates

Parameters
Parameter	Type	Description
pointPositions	number[]	A flattened array of coordinates
Returns
[number, number][]

An array of tuple positions

