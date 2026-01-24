#!/usr/bin/env python3
"""
Main CLI entry point for MIPROv2 optimization commands.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.commands.optimize import optimize

if __name__ == '__main__':
    optimize()
