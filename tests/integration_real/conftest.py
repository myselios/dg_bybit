"""
tests/integration_real/conftest.py
Shared fixtures for integration_real tests (live Testnet tests)

SSOT: CLAUDE.md Section 5.7 Gate 1a/1b (중복 제거)
"""

import os
import pytest


@pytest.fixture
def api_credentials():
    """
    Testnet API credentials from environment variables

    Auto-skip if credentials not available (정당한 사유: API key 누락)

    Returns:
        dict: {"api_key": str, "api_secret": str}

    Raises:
        pytest.skip: If credentials not available
    """
    api_key = os.getenv("BYBIT_TESTNET_API_KEY")
    api_secret = os.getenv("BYBIT_TESTNET_API_SECRET")

    if not api_key or not api_secret:
        pytest.skip("Testnet API credentials not available (set BYBIT_TESTNET_API_KEY/API_SECRET)")

    return {"api_key": api_key, "api_secret": api_secret}
