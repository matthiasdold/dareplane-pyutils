from functools import partial

import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import convolve
from scipy.signal import butter, sosfilt, sosfilt_zi, sosfiltfilt

from dareplane_utils.general.ringbuffer import RingBuffer

FILTER_MAP = {
    "butter": butter,
}


class FilterBufferOverflow(Exception):
    pass


class FilterBank:
    def __init__(
        self,
        bands: dict[str, list[float, float]],
        order: int = 8,
        type: str = "butter",
        sfreq: int = 1000,
        output: str = "abs_ma",
        n_in_channels: int = 1,
        filter_buffer_s: float = 1,
        n_lookback: int = 5,
    ):
        self.sfreq = sfreq
        self.output = output
        self.n_in_channels = n_in_channels
        self.ch_names = [f"ch_{i}" for i in range(n_in_channels)]

        # Used if output is 'abs_ma'
        self.n_lookback = n_lookback

        self.sos = {
            k: butter(
                order,
                (v[0], v[1]),
                btype="bandpass",
                output="sos",
                fs=self.sfreq,
            )
            for k, v in bands.items()
        }

        self.zis = {
            # create the initial zi for the filter and expand for the number of channels
            k: np.repeat(
                np.expand_dims(sosfilt_zi(v), axis=1),
                self.n_in_channels,
                axis=1,
            )
            for k, v in self.sos.items()
        }

        self.ring_buffer = RingBuffer(
            (int(sfreq * filter_buffer_s), len(self.ch_names), len(bands))
        )

        self.output_posprocessing_map = {
            "abs_ma": partial(abs_moving_average, n_lookback=n_lookback),
            "signal": noop,
            "square": lambda x: x**2,
        }
        self.output_transform = self.output_posprocessing_map[output]
        self.n_new = 0

    def filter(self, data: np.ndarray, times: np.ndarray):
        """Assume incoming data to be n_samples x n_in_channels"""

        # I tried to have this write to the buffer directly without stacking
        # an array here, but this feels like premature optimization
        #
        # TODO: have a look at how numpy's strides and as_strided could
        # be used to write to mulitple slices with one return!
        # --> this concerns more the buffer
        #
        # Also check if using a ring buffer per channel could be faster
        # --> should only make a difference if filter() is called much more often
        # than pushing to LSL.

        # TODO: consider reshaping the zis so that sosfilt can be used with axis=0
        # plain %timeit suggests that we loose about 50ns per transpose...
        # the allocation total is ~400ns for 100 samples with 2 channels
        fdata = np.zeros((data.shape[0], len(self.ch_names), len(self.sos))).T

        for i, (k, sos) in enumerate(self.sos.items()):
            (fdata[i, :, :], self.zis[k]) = sosfilt(
                sos, data.T, zi=self.zis[k]
            )

        self.ring_buffer.add_samples(fdata.T, times)
        self.n_new += data.shape[0]

    def get_data(self) -> np.ndarray:

        # get some extra history for the MA
        data = self.ring_buffer.unfold_buffer()[
            -(self.n_new + self.n_lookback) :, ...
        ]

        out = self.output_transform(data)[-self.n_new :, ...]

        return out


def abs_moving_average(
    data: np.ndarray,
    n_lookback: int = 5,
) -> np.ndarray:

    kernel = (
        np.ones((n_lookback, *([1] * len(data.shape[1:])))) * 1 / n_lookback
    )

    ma = convolve(np.abs(data), kernel, mode="constant", cval=0.0)

    # Cut off the edges, so that we return the same as would be for non-nan
    # pandas.rolling(n_lookback).mean()
    pre = (n_lookback - 1) // 2
    post = n_lookback // 2

    return ma[pre:-post]


def noop(data: np.ndarray, *args) -> np.ndarray:
    return data


if __name__ == "__main__":
    sfreq = 1000
    x = np.sin(np.linspace(0, 200, 20 * sfreq)).reshape(-1, 1)
    x += np.random.randn(*x.shape) * 0.5
    x = np.hstack([x, x * 2])

    fb = FilterBank(
        bands={"alpha": [8, 12], "beta": [12, 30], "gamma": [30, 80]},
        sfreq=sfreq,
        n_in_channels=x.shape[1],
        output="abs_ma",
        # output="signal",
        filter_buffer_s=2,
        n_lookback=sfreq // 10,
    )

    rets = []
    inc = 100
    times = np.arange(x.shape[0]) / sfreq

    for iseg in range(0, x.shape[0] // 2 - 5 * inc, inc):
        data = x[iseg : iseg + inc, :]
        t = times[iseg : iseg + inc]
        fb.filter(data, t)

        if fb.ring_buffer.curr_i > 200:
            rets.append(fb.get_data())

    b = np.cumsum([r.shape[0] for r in rets])
    xf = np.vstack(rets)

    nstart = 300
    nend = len(x)
    fig, axs = plt.subplots(3, 1, sharex=True)
    axs[0].plot(x[nstart:nend, 0])
    axs[1].plot(xf[nstart:nend, 0], "r.-", label=fb.ch_names[0])
    axs[1].plot(b - 1 - nstart, xf[b - 1, 0], "b.")
    axs[2].plot(xf[nstart:nend, 1], "r.-", label=fb.ch_names[1])

    # add filtfilt results
    xff = np.hstack([sosfiltfilt(sos, x, axis=0) for sos in fb.sos.values()])
    axs[1].plot(xff[nstart:nend, 0], "g.-", label=fb.ch_names[0] + "_filtfilt")
    axs[2].plot(xff[nstart:nend, 1], "g.-", label=fb.ch_names[1] + "_filtfilt")

    # add filt but whole chunk at once
    zis = {
        k: np.repeat(
            np.expand_dims(sosfilt_zi(v), axis=1),
            1,
            axis=1,
        )
        for k, v in fb.sos.items()
    }
    xfonce = np.hstack(
        [
            sosfilt(fb.sos[bn], x.T, axis=1, zi=zi)[0].T
            for bn, zi in zis.items()
        ]
    )

    axs[1].plot(xfonce[nstart:nend, 0], "b.-", label=fb.ch_names[0] + "_filt")
    axs[2].plot(xfonce[nstart:nend, 1], "b.-", label=fb.ch_names[1] + "_filt")

    axs[1].legend()
    axs[2].legend()

    plt.show()

    # import pandas as pd
    #
    # def foo(data, n_lookback):
    #     df = pd.DataFrame(np.abs(data))
    #     ma = df.rolling(n_lookback).mean()
    #     return ma.loc[~ma[0].isna(), :]
    #
    # data = np.arange(30).reshape(10, 3)
    #
    # %timeit foo(data, 5)
    #
    # %timeit abs_moving_average(data, 5)

    # In [70]:     %timeit foo(data, 5)
    # 156 µs ± 217 ns per loop (mean ± std. dev. of 7 runs, 10,000 loops each)
    #
    # In [71]:     %timeit abs_moving_average(data, 5)
    # 7.42 µs ± 71.5 ns per loop (mean ± std. dev. of 7 runs, 100,000 loops each)
