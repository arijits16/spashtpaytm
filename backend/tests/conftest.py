"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    """A TestClient over a fresh app instance (runs lifespan startup/shutdown)."""
    with TestClient(create_app()) as test_client:
        yield test_client
