"""Test configuration.

These tests deliberately need **no database, no network and no broker**. Every
rule worth protecting in this project is a pure decision — what warning level
this evidence earns, whether a coarse location may contradict an observation,
whether "than" is a town in Gujarat — and those can be exercised directly.

Integration against Postgres/PostGIS is a separate concern; a suite that needs
a live database is a suite people stop running.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
