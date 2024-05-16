import threading
import time

import numpy as np
import pylsl
import pytest

from dareplane_utils.logging.logger import get_logger
from dareplane_utils.stream_watcher.lsl_stream_watcher import StreamWatcher
from tests.resources.shared import get_test_thread

logger = get_logger("testlogger")


# for checking which process is running at a given port, we can use netstat with e.g.
# `netstat -anv -p tcp | grep 8080`


def provide_lsl_stream(
    stop_event: threading.Event, srate: float = 100, nsamples: int = 1000
):
    outlet = pylsl.StreamOutlet(
        pylsl.StreamInfo("test", "test", 5, 100, "float32", "test")
    )
    data = np.tile(np.linspace(0, 1, nsamples), (5, 1))
    data = data.T * np.arange(1, 6)  # 5 channels with linear increase
    data = data.astype(np.float32)

    isampl = 0
    nsent = 0
    tstart = time.time_ns()
    while not stop_event.is_set():
        dt = time.time_ns() - tstart
        req_samples = int((dt / 1e9) * srate) - nsent
        if req_samples > 0:
            outlet.push_chunk(data[isampl : isampl + req_samples, :].tolist())
            nsent += req_samples
            isampl = (isampl + req_samples) % data.shape[0]  # wrap around

        time.sleep(1 / srate)


@pytest.fixture
def spawn_lsl_stream():

    stop_event = threading.Event()
    stop_event.clear()
    th = threading.Thread(target=provide_lsl_stream, args=(stop_event,))
    th.start()

    yield stop_event

    # teardown
    stop_event.set()
    th.join()


def test_connecting(spawn_lsl_stream):
    sw = StreamWatcher("test")
    sw.connect_to_stream()

    # after connect, the number of channels should be known and the buffers
    # should be initialized, with the correct data type
    assert isinstance(sw.inlet, pylsl.StreamInlet)
    assert sw.channel_names == [f"ch_{i}" for i in range(1, 6)]
    assert sw.buffer.shape == (200, 5)
    assert sw.buffer_t.shape == (200,)
    assert sw.chunk_buffer.shape == (32768, 5)
    assert sw.buffer.dtype == np.float32


def test_ringbuffer_updates(spawn_lsl_stream):
    sw = StreamWatcher("test")
    sw.connect_to_stream()

    sw.update()
    time.sleep(0.6)
    sw.update()

    # data should be linearly increasing
    data = sw.unfold_buffer()[-sw.n_new :]
    diff = np.diff(data, axis=0)

    assert sw.n_new > 50

    # diff should be roughly constant and scaled along channels
    assert np.abs(diff - diff[0, :]).max() < 1e-6
    assert np.abs(diff[:, 1] - 2 * diff[:, 0]).max() < 1e-6
    assert np.abs(diff[:, 2] - 3 * diff[:, 0]).max() < 1e-6
    assert np.abs(diff[:, 3] - 4 * diff[:, 0]).max() < 1e-6
    assert np.abs(diff[:, 4] - 5 * diff[:, 0]).max() < 1e-6
