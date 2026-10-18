"""End-to-End Real-Time Verification Test (T9)
Runs the complete real-time lifecycle test:
fault injection -> alert webhook -> incident open -> SSE ordered stream
-> mid-run restart & resume -> action approval -> demo recovery -> outcome recording.
"""

import os
import sys
import pytest

# Ensure scripts directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

from e2e_realtime_test import run_e2e


def test_realtime_end_to_end_lifecycle():
    """Verify complete end-to-end real-time incident lifecycle using TestClient."""
    success = run_e2e(
        base_url="http://localhost:8000",
        tenant="storefront",
        service="paymentservice",
        use_testclient=True,
    )
    assert success is True, "End-to-end real-time test suite failed"
