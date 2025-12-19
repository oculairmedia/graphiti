"""
Mock implementation of EmbedderClient for testing.

Provides controllable embeddings for testing embedding-dependent code
without actual embedding API calls.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from typing import Any


def get_mock_embedding_dimension() -> int:
    """Get mock embedding dimension from environment or default."""
    return int(os.getenv('EMBEDDING_DIMENSION', '2560'))


class MockEmbedderClient:
    """
    Mock implementation of EmbedderClient for testing.

    Provides deterministic embeddings based on input content,
    making tests reproducible.

    Attributes:
        embedding_dim: Dimension of generated embeddings
        call_log: List of inputs passed to create/create_batch
        custom_embeddings: Dict mapping input strings to custom embeddings
    """

    def __init__(self, embedding_dim: int | None = None):
        self.embedding_dim = embedding_dim or get_mock_embedding_dimension()
        self.call_log: list[str | list[str]] = []
        self.custom_embeddings: dict[str, list[float]] = {}

    def set_embedding(self, input_text: str, embedding: list[float]):
        """
        Set a custom embedding for a specific input.

        Args:
            input_text: The input text
            embedding: The embedding to return for this input
        """
        self.custom_embeddings[input_text] = embedding

    def clear(self):
        """Clear call log and custom embeddings."""
        self.call_log.clear()
        self.custom_embeddings.clear()

    def _generate_deterministic_embedding(self, text: str) -> list[float]:
        """
        Generate a deterministic embedding from text.

        Uses MD5 hash to create reproducible embeddings for testing.
        The same input always produces the same embedding.

        Args:
            text: Input text

        Returns:
            List of floats of length embedding_dim
        """
        # Create hash of input
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()

        # Generate embedding from hash
        embedding = []
        for i in range(self.embedding_dim):
            # Use different parts of the hash to generate different values
            idx = (i * 2) % len(text_hash)
            hex_val = (
                int(text_hash[idx : idx + 2], 16)
                if idx + 2 <= len(text_hash)
                else int(text_hash[idx], 16)
            )
            # Normalize to [-1, 1] range
            normalized = (hex_val / 255.0) * 2 - 1
            embedding.append(normalized)

        return embedding

    async def create(
        self, input_data: str | list[str] | Iterable[int] | Iterable[Iterable[int]]
    ) -> list[float]:
        """
        Create embedding for input data.

        Args:
            input_data: String or list of strings to embed

        Returns:
            Embedding vector
        """
        # Handle different input types
        if isinstance(input_data, str):
            text = input_data
        elif isinstance(input_data, list) and input_data and isinstance(input_data[0], str):
            text = input_data[0]  # Take first string
        else:
            text = str(input_data)

        self.call_log.append(text)

        # Return custom embedding if set
        if text in self.custom_embeddings:
            return self.custom_embeddings[text]

        return self._generate_deterministic_embedding(text)

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        """
        Create embeddings for a batch of inputs.

        Args:
            input_data_list: List of strings to embed

        Returns:
            List of embedding vectors
        """
        self.call_log.append(input_data_list)

        embeddings = []
        for text in input_data_list:
            if text in self.custom_embeddings:
                embeddings.append(self.custom_embeddings[text])
            else:
                embeddings.append(self._generate_deterministic_embedding(text))

        return embeddings


# Utility functions for testing


def create_zero_embedding(dim: int | None = None) -> list[float]:
    """Create a zero embedding of specified dimension."""
    dim = dim or get_mock_embedding_dimension()
    return [0.0] * dim


def create_random_embedding(dim: int | None = None, seed: int = 42) -> list[float]:
    """
    Create a reproducible 'random' embedding.

    Args:
        dim: Embedding dimension
        seed: Random seed for reproducibility
    """
    import random

    dim = dim or get_mock_embedding_dimension()
    random.seed(seed)
    return [random.uniform(-1, 1) for _ in range(dim)]


def create_unit_embedding(dim: int | None = None, index: int = 0) -> list[float]:
    """
    Create a unit embedding with 1.0 at specified index.

    Useful for testing similarity/distance calculations.
    """
    dim = dim or get_mock_embedding_dimension()
    embedding = [0.0] * dim
    if 0 <= index < dim:
        embedding[index] = 1.0
    return embedding
