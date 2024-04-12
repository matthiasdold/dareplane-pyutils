# A simple numpy ring buffer for data + timestamps
# This was abstracted from the StreamWatcher class, as it is often useful on its own
import numpy as np

from dareplane_utils.logging.logger import get_logger

logger = get_logger(__name__)


class RingBuffer:
    def __init__(self, shape: tuple[int, int], dtype: type = np.float32):
        # Using numpy buffers
        self.buffer = np.empty((shape[0], shape[1]), dtype=dtype)
        self.buffer_t = np.empty(shape[0])
        self.last_t = 0  # last time stamp
        self.curr_i = 0
        self.logger = logger

    def add_samples(self, samples: list, times: list):
        if len(samples) > 0 and len(times) > 0:
            if len(samples) > self.n_buffer:
                self.logger.warning(
                    "Received more data than fitting into the"
                    " buffer. Will only add data to fill buffer"
                    " once with the latest data"
                )
                samples = samples[-self.n_buffer :]
                times = times[-self.n_buffer :]
            # make it a ring buffer with FIFO
            old_i = self.curr_i
            self.curr_i = (self.curr_i + len(samples)) % self.n_buffer
            # self.logger.debug(f"{old_i=}, {self.curr_i=}, {len(samples)=}")
            # plain forward fill
            if old_i < self.curr_i:
                self.buffer[old_i : self.curr_i] = samples
                self.buffer_t[old_i : self.curr_i] = times
            # fill buffer up
            elif self.curr_i == 0:
                self.buffer[old_i:] = samples
                self.buffer_t[old_i:] = times
            # split needed -> start over at beginning
            else:
                self.logger.debug("Splitting data to add as buffer is full")
                nfull = self.n_buffer - old_i
                self.buffer[old_i:] = samples[:nfull]
                self.buffer_t[old_i:] = times[:nfull]
                self.buffer[: self.curr_i] = samples[nfull:]
                self.buffer_t[: self.curr_i] = times[nfull:]

            self.last_t = times[-1]

    def unfold_buffer(self):
        return np.vstack(
            [self.buffer[self.curr_i :], self.buffer[: self.curr_i]]
        )

    def unfold_buffer_t(self):
        # Do hstack here as the time buffer will be of dim (n,1) anyways
        return np.hstack(
            [self.buffer_t[self.curr_i :], self.buffer_t[: self.curr_i]]
        )
