# A simple numpy ring buffer for data + timestamps
# This was abstracted from the StreamWatcher class, as it is often useful on its own
import numpy as np

from dareplane_utils.logging.logger import get_logger

logger = get_logger(__name__)


class RingBuffer:
    """
    A simple numpy ring buffer for data and timestamps.

    This class implements a ring buffer using numpy arrays to store data and corresponding timestamps.
    It is designed to efficiently handle a fixed-size buffer with FIFO (First In, First Out) behavior.
    The buffer can be used to store and retrieve data samples along with their timestamps.

    Attributes
    ----------
    buffer : np.ndarray
        The data buffer.
    buffer_t : np.ndarray
        The time buffer.
    last_t : float
        The latest timestamp.
    curr_i : int
        The index of the latest data point in the buffer.
    logger : logging.Logger
        The logger used for warnings and debug messages.

    Parameters
    ----------
    shape : tuple[int, int]
        The shape of the buffer, which needs to be at least 2D (n_samples, n_features).
        Arbitrary further dimensions can be added.
    dtype : type, optional
        A numpy data type for the buffer. Defaults to np.float32.

    Examples
    --------

    >>> rb = RingBuffer(shape=(10, 3), dtype=np.float32)
    >>> samples = [np.random.rand(3) for _ in range(5)]
    >>> times = list(range(5))
    >>> rb.add_samples(samples, times)
    >>>
    >>> print(rb.buffer)
    [[0.6456422  0.6063579  0.46437985]
    [0.77531135 0.12675048 0.10201751]
    [0.05525873 0.5852236  0.09854987]
    [0.7515863  0.20880483 0.7236128 ]
    [0.7157382  0.55806357 0.6247236 ]
    [0.         0.         0.        ]
    [0.         0.         0.        ]
    [0.         0.         0.        ]
    [0.         0.         0.        ]
    [0.         0.         0.        ]]
    >>>
    >>> print(rb.buffer_t)
    [0. 1. 2. 3. 4. 0. 0. 0. 0. 0.]
    >>>
    >>> print(rb.unfold_buffer())  # most recent sample is index=-1, second to most recent index=-2, etc.
    [[0.         0.         0.        ]
    [0.         0.         0.        ]
    [0.         0.         0.        ]
    [0.         0.         0.        ]
    [0.         0.         0.        ]
    [0.6456422  0.6063579  0.46437985]
    [0.77531135 0.12675048 0.10201751]
    [0.05525873 0.5852236  0.09854987]
    [0.7515863  0.20880483 0.7236128 ]
    [0.7157382  0.55806357 0.6247236 ]]
    >>>
    >>> print(rb.unfold_buffer_t())
    [0. 0. 0. 0. 0. 0. 1. 2. 3. 4.]


    >>> samples2 = [np.random.rand(3) for _ in range(8)]
    >>> times2 = list(range(8))
    >>> rb.add_samples(samples2, times2)
    >>> print(rb.buffer_t)
    [5. 6. 7. 3. 4. 0. 1. 2. 3. 4.]
    >>>
    >>> print(rb.unfold_buffer_t())
    [3. 4. 0. 1. 2. 3. 4. 5. 6. 7.]

    """

    def __init__(self, shape: tuple[int, int], dtype: type = np.float32):
        """
        Initialize the RingBuffer with a given shape and data type.

        Parameters
        ----------
        shape : tuple[int, int]
            The shape of the buffer, which needs to be at least 2D (n_samples, n_features).
            Arbitrary further dimensions can be added.
        dtype : type, optional
            A numpy data type for the buffer. Defaults to np.float32.
        """

        # Using numpy buffers
        self.buffer = np.zeros(shape, dtype=dtype)
        self.buffer_t = np.zeros(shape[0])
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
        """
        Unfold the buffer to return the data in chronological order.

        This method returns the data in the buffer in chronological order, ending with the most recent sample.

        Returns
        -------
        np.ndarray
            The unfolded data buffer.
        """
        return np.vstack([self.buffer[self.curr_i :], self.buffer[: self.curr_i]])

    def unfold_buffer_t(self):
        """
        Unfold the buffer_t (time stamp buffer) to return time stamps in chronological order.

        This method returns the time stamps in the buffer in chronological order, ending with the most recent time stamp.

        Returns
        -------
        np.ndarray
            The unfolded data buffer.
        """
        # Do hstack here as the time buffer will be of dim (n,1) anyways
        return np.hstack([self.buffer_t[self.curr_i :], self.buffer_t[: self.curr_i]])

    def get_insert_slices(
        self, len_samples: int
    ) -> tuple[list[slice], list[slice], int]:
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
        """Add samples to the buffer and progress the index"""

        if len(samples) == 0 or len(times) == 0:
            self.logger.warning(
                f"Received empty data {samples=}, {times=}, " "not adding to buffer"
            )
        else:
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
            # This step should take about 300ns for 1024 samples
            slice_buffer, slice_samples, self.curr_i = self.get_insert_slices(
                len(samples)
            )

            if len(slice_buffer) > 1:
                self.add_split_buffer(slice_buffer, slice_samples, samples, times)

            else:
                self.add_continuous_buffer(slice_buffer, samples, times)

            self.last_t = times[-1]

    # create a lot of smaller function calls for profiling
    def add_split_buffer(self, slice_buffer, slice_samples, samples, times):
        # self.logger.debug("Splitting data to add as buffer is full")
        self.buffer[slice_buffer[0]] = samples[slice_samples[0]]
        self.buffer[slice_buffer[1]] = samples[slice_samples[1]]
        self.buffer_t[slice_buffer[0]] = times[slice_samples[0]]
        self.buffer_t[slice_buffer[1]] = times[slice_samples[1]]

    def add_continuous_buffer(self, slice_buffer, samples, times):
        """
        Slice samples should not be necessary >>> as we add continuously
        + slice selection from lists is slow
        """
        self.buffer[slice_buffer[0]] = samples
        self.buffer_t[slice_buffer[0]] = times


if __name__ == "__main__":
    rb = RingBuffer(shape=(10, 3), dtype=np.float32)
    samples = [np.random.rand(3) for _ in range(5)]
    times = list(range(5))

    rb.add_samples(samples, times)

    print(rb.buffer)
    print(rb.buffer_t)
    print(
        rb.unfold_buffer()
    )  # most recent sample is index=-1, second to most recent index=-2, etc.
    print(rb.unfold_buffer_t())

    samples2 = [np.random.rand(3) for _ in range(8)]
    times2 = list(range(8))
    rb.add_samples(samples2, times2)

    print(rb.buffer_t)
    print(rb.unfold_buffer_t())
