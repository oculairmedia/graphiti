# EmbedderClient Abstract Methods

## Overview
The `EmbedderClient` is an abstract base class in the Graphiti codebase that defines the interface for embedding clients. Any custom embedder implementation must inherit from this class and implement its abstract methods.

## Required Abstract Method

### `create()`
**Must be implemented** - This is the core abstract method that all embedder implementations must provide.

```python
@abstractmethod
async def create(
    self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
) -> list[float]:
    pass
```

**Details:**
- **Purpose**: Creates embeddings for the given input data
- **Input Types**: 
  - `str` - Single string to embed
  - `list[str]` - List of strings to embed
  - `Iterable[int]` - Iterable of integers (token IDs)
  - `Iterable[Iterable[int]]` - Iterable of iterables of integers
- **Return Type**: `list[float]` - A single embedding vector as a list of floats
- **Async**: Must be implemented as an async method

## Optional Method

### `create_batch()`
**Optional to override** - Has a default implementation that raises `NotImplementedError`.

```python
async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
    raise NotImplementedError()
```

**Details:**
- **Purpose**: Creates embeddings for multiple inputs in a single batch operation
- **Input**: `list[str]` - List of strings to embed
- **Return Type**: `list[list[float]]` - List of embedding vectors
- **Default Behavior**: Raises `NotImplementedError` if not overridden
- **When to Override**: Implement this if your embedding service supports efficient batch processing

## Implementation Example

Here's a basic structure for implementing a custom embedder:

```python
from graphiti_core.embedder.client import EmbedderClient

class CustomEmbedder(EmbedderClient):
    def __init__(self, config):
        self.config = config
        # Initialize your embedding client/service here
    
    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        # Convert input_data to appropriate format for your service
        # Call your embedding service
        # Return the embedding as list[float]
        pass
    
    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        # Optional: Implement batch processing if supported
        # Otherwise, you can call create() for each item
        pass
```

## Key Points

1. **Only `create()` is required** - This is the single abstract method you must implement
2. **Handle multiple input types** - The `create()` method must handle various input formats
3. **Return single embedding** - Even for list inputs, `create()` returns a single embedding vector
4. **Batch processing is optional** - Only implement `create_batch()` if you want batch functionality
5. **Async required** - All methods must be async

## Location in Codebase
- **Abstract class**: `graphiti_core/embedder/client.py`
- **Existing implementations**: 
  - `graphiti_core/embedder/openai.py` (OpenAIEmbedder)
  - `graphiti_core/embedder/gemini.py` (GeminiEmbedder)
  - `graphiti_core/embedder/voyage.py` (VoyageAIEmbedder)
