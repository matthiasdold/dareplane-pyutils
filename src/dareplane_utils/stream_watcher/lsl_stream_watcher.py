import ctypes
import logging
from typing import Callable

import numpy as np
import pylsl
import xmltodict

from dareplane_utils.general.ringbuffer import RingBuffer
from dareplane_utils.logging.logger import get_logger

logger = get_logger(__name__)


class StreamWatcherNotConnected(ValueError):
    pass


def get_streams_names() -> list[str]:
    """Get a list of all available lsl stream names.

    Returns
    -------
    streams : list[str]
        names of all available LSL streams

    """

    return [s.name() for s in pylsl.resolve_streams()]


def pylsl_xmlelement_to_dict(inf: pylsl.pylsl.StreamInfo) -> dict:
    """
    The pylsl XMLElement is hard to investigate -> cast to a dict for
    simplicity
    """
    return xmltodict.parse(inf.as_xml())


def get_channel_names(inf: pylsl.pylsl.StreamInfo) -> list[str]:
    d = pylsl_xmlelement_to_dict(inf)

    # By adding to the xml meta data structure of LSL, if we only add one
    # channel, the data will be a dict instead of a list of dicts

    try:
        if isinstance(d["info"]["desc"]["channels"]["channel"], dict):
            return [d["info"]["desc"]["channels"]["channel"]["label"]]
        else:
            return [
                ch_inf["label"]
                for ch_inf in d["info"]["desc"]["channels"]["channel"]
            ]
    except TypeError as err:
        logger.debug(
            f"No channel info - continue with default: ch_1, ch_2,... - {err}"
        )
        return [f"ch_{i + 1}" for i in range(inf.channel_count())]


class StreamWatcher:
    def __init__(
        self,
        name: str = "",
        buffer_size_s: float = 2,
        logger: logging.Logger = logger,
    ):
        """
        Parameters
        ----------
        name : str
            Name tag to identify the manager -> could be same as the LSL stream
            it should be watching
        buffer_size_s : float
            the data buffer size in seconds
        """
        self.name = name
        # this concerns the ringbuffer
        self.buffer_size_s = buffer_size_s

        # the maximum number of samples to pull in one go
        self.chunk_buffer_size = 1024 * 32

        self.stream = None
        self.inlet = None
        self.buffer = None

        # Set after connection
        self.samples: list[list[float]] = []
        self.times: list[float] = []
        self.n_new: int = 0
        self.logger = logger

        # used to expose the ring buffer data structure directly
        self.buffer = np.array([])
        self.buffer_t = np.array([])
        self.last_t = 0
        self.curr_i = 0

        # The update method will be overwritting during _init_buffer
        # fit for the date type of the stream
        self.update: Callable = lambda: None

    def connect_to_stream(self, identifier: dict | None = None):
        """
        Either use the self.name or a provided identifier dict to hook up
        with an LSL stream, they should coincide
        """
        if identifier:
            name = identifier["name"]
            self.name = name
        else:
            name = self.name

        self.streams = pylsl.resolve_byprop("name", name)
        if len(self.streams) > 1:
            print(f"Selecting stream by {name=} was ambigous - taking first")

        self.inlet = pylsl.StreamInlet(self.streams[0])

        self.channel_names = get_channel_names(self.inlet.info())

        self._init_buffer()

        # The first update call will return empty, so do it here already
        self.update()

    def _init_buffer(self):
        if self.streams is None or self.inlet is None:
            raise StreamWatcherNotConnected(
                "StreamWatcher seems not connected, did you call"
                " connect_to_stream() on it?"
            )

        # set a default value for irregular streams
        if self.streams[0].nominal_srate() == 0:
            n_samples = 1000
        else:
            n_samples = int(
                self.streams[0].nominal_srate() * self.buffer_size_s
            )

        self.ring_buffer = RingBuffer((n_samples, len(self.channel_names)))

        self._adjust_buffer_data_type()

        # link properties -> for convenience of access
        self.buffer = self.ring_buffer.buffer
        self.buffer_t = self.ring_buffer.buffer_t
        self.last_t = self.ring_buffer.last_t
        self.curr_i = self.ring_buffer.curr_i

        self._define_update_method()

    def _adjust_buffer_data_type(self):
        dtype_map = {
            ctypes.c_char_p: "object",
            ctypes.c_double: np.float64,  # could also be any int type
            ctypes.c_byte: np.int8,
            ctypes.c_short: np.int16,
            ctypes.c_int: np.int32,
            ctypes.c_int: np.int32,
            ctypes.c_long: np.int64,
        }

        # default to np.float32 << LSL default
        dtype = dtype_map.get(self.inlet.value_type, np.float32)

        self.chunk_buffer = np.zeros(
            (self.chunk_buffer_size, len(self.channel_names))
        ).astype(dtype)

        self.ring_buffer.buffer = self.ring_buffer.buffer.astype(dtype)

    def _define_update_method(self):

        if self.inlet.value_type == ctypes.c_char_p:
            self.update = self.update_char_p
        else:
            self.update = self.update_numeric

    def update_numeric(self):
        """Look for new data and update the buffer"""

        # This logic works as long as the returned samples are not too many
        # samples, times = self.inlet.pull_chunk()
        # Better use the direct assignment

        _, times = self.inlet.pull_chunk(
            max_samples=self.chunk_buffer_size, dest_obj=self.chunk_buffer
        )

        if len(times) > 0:
            samples = self.chunk_buffer[: len(times), :]
            self.ring_buffer.add_samples(samples, times)
            self.overwriting_samples(samples)
            self.n_new += len(times)

    def update_char_p(self):

        samples, times = self.inlet.pull_chunk(
            max_samples=self.chunk_buffer_size
        )

        if len(times) > 0:
            self.ring_buffer.add_samples(samples, times)
            self.overwriting_samples(samples)
            self.n_new += len(times)

    def overwriting_samples(self, samples):
        self.samples = samples

    def unfold_buffer(self):
        return self.ring_buffer.unfold_buffer()

    def unfold_buffer_t(self):
        # Do hstack here as the time buffer will be of dim (n,1) anyways
        return self.ring_buffer.unfold_buffer_t()

    def disconnect(self):
        """Destroying the inlet will disconnect -> see pylsl.pylsl.py"""
        logger.info(f"Disconnecting from LSL stream - LSLInlet:{self.inlet}")
        del self.inlet
        self.inlet = None


if __name__ == "__main__":
    sw = StreamWatcher("mock_EEG_stream")
    sw.connect_to_stream()
