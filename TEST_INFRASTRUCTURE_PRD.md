# PRD: Graphiti Ingestion Quality Assurance (IQA) Framework

## 1. Executive Summary
As Graphiti transitions strictly to a **Temporal-based ingestion pipeline**, we must ensure that this migration does not degrade data quality. Recent bugs (e.g., silent failure to update summaries) highlight the need for a rigorous **End-to-End (E2E) Regression Suite** that validates not just *code execution*, but *data evolution*.

This document defines the requirements for the **Graphiti IQA Framework**: a test suite acting as the "Gatekeeper" for decommissioning legacy code.

## 2. Problem Statement
Current unit tests mock too much. They verify that functions *run*, but not that they *work* together to produce a high-quality Graph over time.
*   **The Gap:** We lack tests for **Temporal Evolution**. (e.g., "Does Alice's summary update when she gets a promotion in Episode 2?").
*   **The Risk:** Migrating to Temporal introduces complex data serialization boundaries. Data can be lost between steps (Activities), leading to silent quality rot.

## 3. Goals & Objectives
1.  **Verify Evolution:** Ensure entities and edges evolve correctly across sequential episodes.
2.  **Catch Regressions:** Specifically target known failure modes (missing summaries, broken deduplication, vector type mismatches).
3.  **Gatekeep Legacy Removal:** Provide 100% confidence to delete `Graphiti.add_episode` and `worker/worker_service.py` (Legacy).

## 4. Technical Architecture

### 4.1. Test Stack
*   **Framework:** `pytest` (standard Python testing).
*   **Infrastructure:** Real **FalkorDB** instance (via `testcontainers` or existing Docker dev env).
*   **LLM Interaction:** Real LLM calls (initially) or recorded VCR cassettes (for determinism/cost) using `vcrpy`.
*   **Target:** The **Temporal Activities** (`graphiti_core.utils.temporal_visibility.activities`).
    *   *Why Activities?* Testing the full Temporal Cluster is heavy/flaky in CI. Testing the Activities ensures the *logic* and *data passing* are correct without needing a running Temporal server for every test run.

### 4.2. The "Golden Path" Scenarios
The suite will revolve around **Story-Based Testing**. Instead of testing isolated functions, we test a narrative sequence.

#### Scenario A: "The Evolution of Alice" (Attribute Updates)
*   **Episode 1:** "Alice starts as a Junior Dev at TechCorp."
    *   *Assertion:* Entity `Alice` created. Summary mentions "Junior Dev".
*   **Episode 2:** "Alice is promoted to CTO."
    *   *Assertion:* Entity `Alice` (same UUID) updated. Summary now mentions "CTO".
    *   *Regression Check:* Fails if summary remains static (the bug we just fixed).

#### Scenario B: "The Duplicate Merge" (Resolution)
*   **Episode 1:** "Robert builds the backend."
    *   *Assertion:* Entity `Robert` created.
*   **Episode 2:** "Bob fixes a bug in the backend." (Bob = Robert)
    *   *Assertion:* `Bob` is resolved to `Robert`. No new node created. Graph connectivity increases.

#### Scenario C: "The Correction" (Fact Invalidation)
*   **Episode 1:** "Project X is cancelled."
*   **Episode 2:** "Actually, Project X is resumed."
    *   *Assertion:* Edge `Project X -> Status -> Cancelled` gets `invalid_at` set. New edge `Resumed` created.

## 5. Implementation Specifications

### 5.1. Test Fixture (`conftest.py`)
A robust fixture that:
1.  Spins up/Connects to a clean FalkorDB graph (`graphiti_test_<timestamp>`).
2.  Initializes the `ZepGraphiti` client with **DSPy enabled**.
3.  Tears down/cleans up after the test.

### 5.2. Activity Simulation Helper
A helper function to mimic the Temporal Workflow data passing:
```python
async def run_ingestion_sequence(client, episodes):
    state = {}
    for ep in episodes:
        # mimic workflow steps
        nodes = await activities.extract_nodes(ep)
        resolved, uuid_map = await activities.resolve_nodes(nodes, state)
        # CRITICAL: This is where we catch serialization bugs
        # effectively json.dumps(nodes) -> json.loads(nodes)
        await activities.persist(resolved)
```

## 6. Migration & Dismantling Strategy
Once this suite is green:
1.  **Code Freeze:** No new features in `Graphiti.add_episode` (Legacy).
2.  **Redirect:** Modify `Graphiti.add_episode` to raise a `DeprecationWarning` or internally call the Temporal logic (if feasible without Temporal Server).
3.  **Delete:** Remove `worker/worker_service.py` (Legacy Worker) and rely solely on `temporal_ingestion_worker.py`.

## 7. Success Metrics
*   **Coverage:** 100% coverage of the `activities.py` module.
*   **Regression Catch:** The suite *must* fail if we revert the `force_update=True` fix.
