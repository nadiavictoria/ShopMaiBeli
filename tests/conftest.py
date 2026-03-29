"""
Pytest configuration for async tests.

This file enables pytest-asyncio support for running async test functions.
"""

import pytest
import asyncio


# Fixture to provide event loop for async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


def pytest_collection_modifyitems(items):
    """Mark async test functions with the asyncio marker if not already marked."""
    for item in items:
        if asyncio.iscoroutinefunction(item.function):
            if "asyncio" not in item.keywords:
                item.add_marker(pytest.mark.asyncio)


def pytest_configure(config):
    """Register asyncio marker."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as an asyncio test"
    )
