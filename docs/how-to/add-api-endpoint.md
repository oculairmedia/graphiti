# How-to: Add a New API Endpoint

> **Keywords**: `api`, `endpoint`, `fastapi`, `router`, `dto`, `server`, `http`

## Quick Path

1. Add request/response models in `server/graph_service/dto/` if needed.
2. Add a route handler in the relevant router under `server/graph_service/routers/`.
3. Wire or verify router registration in `server/graph_service/main.py`.
4. Add tests in `server/tests/`.
5. Update `docs/reference/api-reference.md`.

---

## 1) Choose the Right Router

Use an existing router when the endpoint fits its domain:

- `server/graph_service/routers/ingest.py` for data writes and ingestion actions
- `server/graph_service/routers/retrieve.py` for read endpoints
- `server/graph_service/routers/ingest_temporal.py` for Temporal-native ingestion
- `server/graph_service/routers/tools.py` for maintenance operations
- `server/graph_service/routers/utils.py` for utility helpers

If no existing router fits, create a new file in `server/graph_service/routers/` and register it in `server/graph_service/main.py`.

---

## 2) Define DTOs (If Needed)

Place request and response models in `server/graph_service/dto/`.

Example pattern:

```python
from pydantic import BaseModel


class MyRequest(BaseModel):
    group_id: str
    query: str


class MyResponse(BaseModel):
    success: bool
    message: str
```

Reuse existing DTOs when possible to keep request/response formats consistent.

---

## 3) Add the Route Handler

Example FastAPI route pattern:

```python
from fastapi import APIRouter, status

router = APIRouter()


@router.post('/my-endpoint', status_code=status.HTTP_200_OK)
async def my_endpoint(request: MyRequest) -> MyResponse:
    return MyResponse(success=True, message='ok')
```

Follow existing conventions in nearby routers:

- Use explicit status codes
- Validate and normalize input early
- Return structured response models
- Use the existing Graphiti dependency injection patterns when interacting with graph state

---

## 4) Register Router in App

Routers are included in `server/graph_service/main.py`.

Pattern examples from existing code:

- `app.include_router(ingest.router)`
- `app.include_router(ingest_temporal.router, prefix='/api')`
- `app.include_router(tools_router.router, prefix='/api')`

If your route should live under `/api`, include the `prefix='/api'` at registration time.

---

## 5) Add or Update Tests

Add coverage under `server/tests/`.

Common test targets:

- Happy path with valid payload
- Validation failures (missing/invalid fields)
- Dependency failures and error responses
- Response schema shape

Run server tests:

```bash
pytest server/tests -q
```

---

## 6) Document the Endpoint

Update `docs/reference/api-reference.md` with:

- Method + path
- Request schema
- Response schema
- Error cases

If this endpoint introduces a new recurring workflow, add or update a matching guide in `docs/how-to/`.

---

## Files to Know

| File | Purpose |
|------|---------|
| `server/graph_service/main.py` | Router registration and app wiring |
| `server/graph_service/routers/` | Endpoint handlers |
| `server/graph_service/dto/` | Request/response models |
| `server/tests/` | API tests |
| `docs/reference/api-reference.md` | API reference documentation |

---

## See Also

- [write-tests.md](write-tests.md) - Testing patterns
- [../reference/api-reference.md](../reference/api-reference.md) - API surface
- [../explanation/architecture.md](../explanation/architecture.md) - Service layout
