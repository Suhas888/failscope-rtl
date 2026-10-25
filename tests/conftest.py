"""Shared pytest fixtures and conftest for FailScope RTL tests."""
import os
import sys
from pathlib import Path

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
