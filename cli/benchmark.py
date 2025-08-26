#!/usr/bin/env python3
"""
Main CLI entry point for benchmarking commands.

This script provides a centralized entry point for all dry-run benchmarking functionality.
"""

import sys
from pathlib import Path

# Add the project root to Python path so we can import modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cli.commands.benchmark import benchmark

if __name__ == "__main__":
    benchmark()