# A simple numpy ring buffer for data + timestamps
# This was abstracted from the StreamWatcher class, as it is often useful on its own
import numpy as np

from dareplane_utils.logging.logger import get_logger

logger = get_logger(__name__)


class RingBuffer:
    """

    Attributes
    ----------
    buffer : np.ndarray
        the data buffer
    buffer_t : np.ndarray
        the time buffer
    last_t : float
        latest time stamp
    curr_i : int
        index of the latest data point int the buffer
    logger : logging.Logger
        the logger used for warnings and debug messages
    """

    def __init__(self, shape: tuple[int, int], dtype: type = np.float32):
        # Using numpy buffers
        self.buffer = np.empty((shape[0], shape[1]), dtype=dtype)
        self.buffer_t = np.empty(shape[0])
        self.last_t = 0  # last time stamp
        self.curr_i = 0
        self.logger = logger

    def legacy_add_samples(self, samples: list, times: list):
        if len(samples) > 0 and len(times) > 0:
            buffer_size = self.buffer.shape[0]
            if len(samples) > buffer_size:
                self.logger.warning(
                    "Received more data than fitting into the"
                    " buffer. Will only add data to fill buffer"
                    " once with the latest data"
                )
                samples = samples[-buffer_size:]
                times = times[-buffer_size:]
            # make it a ring buffer with FIFO
            old_i = self.curr_i
            self.curr_i = (self.curr_i + len(samples)) % buffer_size
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
                nfull = buffer_size - old_i
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

    def get_insert_slices(self, len_samples: int) -> tuple[slice, slice, int]:
        """Get slices mapping data from the samples to the buffer

        Parameters
        ----------
        len_samples : int
            number of samples to add

        Returns
        -------
        tuple[list[slice], list[slice], int]

        """
        old_i = self.curr_i
        new_i = (self.curr_i + len_samples) % self.buffer.shape[0]

        if old_i < new_i:
            return [slice(old_i, new_i)], [slice(0, len_samples)], new_i
        elif new_i == 0:
            return [slice(old_i, None)], [slice(0, len_samples)], new_i
        else:
            nfull = self.buffer.shape[0] - old_i
            return (
                [slice(old_i, None), slice(0, new_i)],
                [slice(0, nfull), slice(nfull, None)],
                new_i,
            )

    def add_samples(self, samples: list, times: list):
        if len(samples) > 0 and len(times) > 0:
            buffer_size = self.buffer.shape[0]
            if len(samples) > buffer_size:
                self.logger.warning(
                    "Received more data than fitting into the"
                    " buffer. Will only add data to fill buffer"
                    " once with the latest data"
                )
                samples = samples[-buffer_size:]
                times = times[-buffer_size:]
            # make it a ring buffer with FIFO
            slice_buffer, slice_samples, self.curr_i = self.get_insert_slices(
                len(samples)
            )
            if len(slice_buffer) > 1:
                self.logger.debug("Splitting data to add as buffer is full")
                self.buffer[slice_buffer[0]] = samples[slice_samples[0]]
                self.buffer_t[slice_buffer[0]] = times[slice_samples[0]]
                self.buffer[slice_buffer[1]] = samples[slice_samples[1]]
                self.buffer_t[slice_buffer[1]] = times[slice_samples[1]]

            else:
                self.buffer[slice_buffer[0]] = samples[slice_samples[0]]
                self.buffer_t[slice_buffer[0]] = times[slice_samples[0]]

            self.last_t = times[-1]


if __name__ == "__main__":

    x = np.random.rand(500_000, 5)
    rb = RingBuffer((20_000, 5))
    rb.add_samples(x[:1500], np.arange(1500))

    np.random.seed(42)
    inc = (np.random.rand(10) * 1000).astype(int)
    ts = [np.arange(i) for i in inc]

    def test_foo():
        i = 0
        for ic, t in zip(inc, ts):
            rb.legacy_add_samples(x[i : i + ic], t)
            i += ic

    def test_foo_new():
        i = 0
        for ic, t in zip(inc, ts):
            rb.add_samples(x[i : i + ic], t)
            i += ic

    # %timeit test_foo_new()
    # %timeit test_foo()

    # %timeit test_foo()
    # --> old version without using get_insert_slices and using if statements
    # In [18]:     %timeit test_foo()
    # 15.5 µs ± 86.7 ns per loop (mean ± std. dev. of 7 runs, 100,000 loops each)
    #
    # New version is slower for a few 100 inserts, but up to 50% faster for smaller number of samples to add
    # %timeit test_foo_new()
    # 18.8 µs ± 35.4 ns per loop (mean ± std. dev. of 7 runs, 100,000 loops each)
    #
    # Also for a few 1000 inserts, speed is the same
    #     #In [62]:     %timeit test_foo_new()
    # 56 µs ± 1.03 µs per loop (mean ± std. dev. of 7 runs, 10,000 loops each)
    #
    # In [63]:     %timeit test_foo()
    # 53.3 µs ± 1.21 µs per loop (mean ± std. dev. of 7 runs, 10,000 loops each)
    #
    # In [64]: inc
    # Out[64]: array([3745, 9507, 7319, 5986, 1560, 1559,  580, 8661, 6011, 7080])

    #
    # %timeit a=slice(5, 2000) --> ~40ns for defining as slice
    #
    # Select with slice vs index
    # s = slice(5, 2000)
    # idx = np.arange(5, 2000)
    # %timeit x[s] --> 75ns
    # %timeit x[idx] --> 17us!!!
    #
    #
    #
    # In [5]: %timeit rb.unfold_buffer()
    # 8.3 µs ± 79.7 ns per loop (mean ± std. dev. of 7 runs, 100,000 loops each)
    #
