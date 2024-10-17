import os
import threading
import time

import numpy as np
import pylsl
import pytest

from dareplane_utils.logging.logger import get_logger
from dareplane_utils.stream_watcher.lsl_stream_watcher import StreamWatcher

# from tests.resources.shared import get_test_thread

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


@pytest.fixture
def get_markers_outlet() -> pylsl.StreamOutlet:
    info = pylsl.StreamInfo(
        "TestMarkers",
        "Markers",
        1,
        nominal_srate=pylsl.IRREGULAR_RATE,
        channel_format="string",
    )

    return pylsl.StreamOutlet(info)


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


def test_reading_string_marker(get_markers_outlet):
    markers_outlet = get_markers_outlet
    # markers_outlet = get_markers_outlet()

    sw = StreamWatcher("TestMarkers")
    sw.connect_to_stream()
    sw.update()

    for i in range(10):
        markers_outlet.push_sample([f"Marker - {i + 1}"])

    time.sleep(0.1)
    # check that the correct update method is selected
    assert sw.update == sw.update_char_p

    sw.update()

    assert sw.buffer[0] == ["Marker - 1"]
    assert sw.buffer[2] == ["Marker - 3"]
    assert sw.buffer[9] == ["Marker - 10"]


@pytest.mark.parametrize(
    "fmt", ["float32", "double64", "string", "int32", "int16", "int8", "int64"]
)
def test_data_format_derivation(fmt):
    # The valid formats are provided in the keys of pylsl.string2fmt
    # string2fmt = {
    #     "float32": cf_float32,
    #     "double64": cf_double64,
    #     "string": cf_string,
    #     "int32": cf_int32,
    #     "int16": cf_int16,
    #     "int8": cf_int8,
    #     "int64": cf_int64,
    # }
    fmt_map = {
        "float32": np.float32,
        "double64": np.float64,
        "string": "object",
        "int32": np.int32,
        "int16": np.int16,
        "int8": np.int8,
        "int64": np.int64,
    }
    sname = f"TestStream_{fmt}"
    info = pylsl.StreamInfo(
        sname,
        "EEG",
        10,
        nominal_srate=100,
        channel_format=fmt,
    )
    outlet = pylsl.StreamOutlet(info)

    # Abort for windows as test will fail: https://github.com/labstreaminglayer/pylsl/issues/84
    if os.name == "nt":
        if fmt == "int32":
            with pytest.raises(ValueError):
                sw = StreamWatcher(sname)
                sw.connect_to_stream()
        if fmt == "int64":
            with pytest.raises(NotImplementedError):
                sw = StreamWatcher(sname)
                sw.connect_to_stream()
    else:
        sw = StreamWatcher(sname)
        sw.connect_to_stream()
        sw.update()

        time.sleep(0.1)

        if fmt == "string":
            data = [[f"mrk_{i}" for i in range(10)]] * 5
        else:
            data = np.arange(100).reshape((-1, 10)).astype(fmt_map[fmt])

        outlet.push_chunk(data)

        time.sleep(0.1)

        # check that the correct update method is selected
        if fmt == "string":
            assert sw.update == sw.update_char_p
        else:
            assert sw.update == sw.update_numeric

        sw.update()

        for i, d in enumerate(data):
            assert np.all(sw.buffer[i] == d)
