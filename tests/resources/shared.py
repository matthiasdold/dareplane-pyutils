# functions shard between test files
import subprocess
import threading
import time

from dareplane_utils.default_server.server import DefaultServer


def get_default_server(port: int = 8080) -> DefaultServer:
    server = DefaultServer(port=port)
    server.init_server()
    return server


def get_test_subprocess() -> subprocess.Popen:
    p = subprocess.Popen(["python", "-m", "tests.resources.infinite_sleep"])
    return p


def get_test_thread() -> subprocess.Popen:
    stop_event = threading.Event()
    thread = threading.Thread(
        target=thread_event_interupted_sleep, kwargs={"stop_event": stop_event}
    )

    return thread, stop_event


def thread_event_interupted_sleep(stop_event: threading.Event):
    while not stop_event.is_set():
        time.sleep(1)
