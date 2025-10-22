# Valid FalkorDB Date Format Reference

This is a snapshot of valid data from a clean FalkorDB instance (314 nodes, 404 edges).

## Date Format Pattern
All dates use ISO 8601 format with microseconds and timezone: `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`

## Entity Nodes
All Entity nodes HAVE created_at field:
- Example: `2025-09-04T05:46:33.520050+00:00`
- Field: `created_at` (always present)

## Episodic Nodes  
All Episodic nodes have BOTH created_at and valid_at:
- `created_at`: When the episode was ingested (e.g., `2025-09-04T05:53:00.446565+00:00`)
- `valid_at`: When the episode occurred (e.g., `2025-09-01T23:19:38.788839+00:00`)

## RELATES_TO Edges
Have up to 4 temporal fields:
- `created_at`: Always present (e.g., `2025-09-04T05:50:11.760912+00:00`)
- `valid_at`: Often present (e.g., `2025-09-03T16:46:49.948643+00:00`)
- `invalid_at`: Optional (e.g., `2025-09-03T15:56:40.571749+00:00`)
- `expired_at`: Optional (e.g., `2025-09-04T05:47:09.168667+00:00`)

## Key Observations
1. ALL nodes have created_at in the valid dataset
2. Date format is consistent: ISO 8601 with microseconds
3. Timezone is always +00:00 (UTC)
4. No synthetic 1979 dates
5. created_at reflects ingestion time
6. valid_at reflects event/document time
