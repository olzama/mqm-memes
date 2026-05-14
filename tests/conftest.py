import subprocess, time, socket, pytest

TEST_PORT = 8099


def _port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("localhost", port)) != 0


@pytest.fixture(scope="session", autouse=True)
def http_server():
    if not _port_free(TEST_PORT):
        yield  # already running (e.g. manual dev server)
        return
    import os, sys
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(TEST_PORT)],
        cwd=str(__file__).replace("/tests/conftest.py", ""),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)
    yield
    proc.terminate()
