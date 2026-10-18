import socket
import pytest
from app.config import settings


def is_falkordb_available(host: str | None = None, port: int | None = None) -> bool:
    target_host = host or settings.falkordb_host
    target_port = port or settings.falkordb_port
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        res = sock.connect_ex((target_host, target_port))
        sock.close()
        return res == 0
    except Exception:
        return False


_FALKOR_UP = is_falkordb_available()


def pytest_collection_modifyitems(config, items):
    """Mark legacy tests requiring live FalkorDB as skipped if FalkorDB is offline."""
    if not _FALKOR_UP:
        skip_marker = pytest.mark.skip(reason="FalkorDB service container is offline at localhost:6379")
        for item in items:
            test_path = str(item.fspath)
            if "test_m" in test_path:
                if item.name not in ("test_sanitize_tenant_id",):
                    item.add_marker(skip_marker)


@pytest.fixture(autouse=True)
def configure_test_environment(monkeypatch, request):
    """Auto-configure test environment for legacy test_m* files so legacy tests authenticate as admin seamlessly."""
    test_path = str(request.fspath)
    if "test_m" in test_path:
        monkeypatch.setattr(settings, "auth_dev_mode", True)
