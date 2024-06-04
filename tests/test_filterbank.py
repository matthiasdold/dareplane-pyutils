import numpy as np
import pytest
from scipy.signal import sosfilt

from dareplane_utils.signal_processing.filtering import FilterBank


@pytest.fixture
def x():
    sfreq = 1000

    # test with two channels
    x = np.sin(np.linspace(0, 200, 20 * sfreq)).reshape(-1, 1)
    x += np.random.randn(*x.shape) * 0.5
    x = np.hstack([x, x * 2])
    return x


def test_filterbank_vs_manual_filtering(x):

    sfreq = 1000

    fb = FilterBank(
        bands={"alpha": [8, 12], "beta": [12, 30], "gamma": [30, 80]},
        sfreq=sfreq,
        n_in_channels=x.shape[1],
        output="abs_ma",
        filter_buffer_s=2,
        n_lookback=sfreq // 10,
    )

    # single data chunk -> 20k samples, should fill over the buffer
    times = np.arange(x.shape[0]) / sfreq
    fb.filter(x, times)
    xf = fb.ring_buffer.unfold_buffer()

    xf_alpha, _ = sosfilt(fb.sos["alpha"], x, zi=fb.zis["alpha"], axis=0)
    xf_beta, _ = sosfilt(fb.sos["beta"], x, zi=fb.zis["beta"], axis=0)

    assert np.allclose(xf_alpha[-1000:, 0], xf[-1000:, 0, 0])
    assert np.allclose(xf_alpha[-1000:, 1], xf[-1000:, 1, 0])
    assert np.allclose(xf_beta[-1000:, 0], xf[-1000:, 0, 1])
    assert np.allclose(xf_beta[-1000:, 1], xf[-1000:, 1, 1])


def test_filterbank_get_data(x):

    sfreq = 1000
    n_lookback = sfreq // 10

    fb = FilterBank(
        bands={"alpha": [8, 12], "gamma": [30, 80]},
        sfreq=sfreq,
        n_in_channels=x.shape[1],
        output="abs_ma",
        filter_buffer_s=2,
        n_lookback=n_lookback,
    )

    times = np.arange(x.shape[0]) / sfreq
    fb.filter(x, times)

    xf = fb.ring_buffer.unfold_buffer()

    xta = np.mean(np.abs(xf[-n_lookback:, 0, 0]))
    xtag = np.mean(np.abs(xf[-n_lookback:, 0, 1]))
    xtb = np.mean(np.abs(xf[-n_lookback:, 1, 0]))
    xta2 = np.mean(np.abs(xf[-(n_lookback + 10) : -10, 0, 0]))

    # AbsMovingAverage -> the default
    mva = fb.get_data()
    assert np.allclose(mva[-1, 0, 0], xta)
    assert np.allclose(mva[-1, 1, 0], xtb)
    assert np.allclose(mva[-11, 0, 0], xta2)
    assert np.allclose(mva[-1, 0, 1], xtag)

    # Signal == noop
    fb.output = "signal"
    fb.output_transform = fb.output_posprocessing_map[fb.output]
    xs = fb.get_data()
    assert np.allclose(xs, xf[-xs.shape[0] :, ...])

    # Square
    fb.output = "square"
    fb.output_transform = fb.output_posprocessing_map[fb.output]
    xs = fb.get_data()
    assert np.allclose(xs, xf[-xs.shape[0] :, ...] ** 2)


def test_filterbank_single_vs_chunk_processing(x):

    sfreq = 1000
    n_lookback = sfreq // 10

    fb = FilterBank(
        bands={"alpha": [8, 12], "gamma": [30, 80]},
        sfreq=sfreq,
        n_in_channels=x.shape[1],
        output="abs_ma",
        filter_buffer_s=2,
        n_lookback=n_lookback,
    )

    fb2 = FilterBank(
        bands={"alpha": [8, 12], "gamma": [30, 80]},
        sfreq=sfreq,
        n_in_channels=x.shape[1],
        output="abs_ma",
        filter_buffer_s=2,
        n_lookback=n_lookback,
    )

    times = np.arange(x.shape[0]) / sfreq

    inc = 100
    times = np.arange(x.shape[0]) / sfreq

    for iseg in range(0, x.shape[0] // 2, inc):
        data = x[iseg : iseg + inc, :]
        t = times[iseg : iseg + inc]
        fb2.filter(data, t)

    fb.filter(x[: iseg + inc], times)

    assert np.allclose(
        fb.ring_buffer.unfold_buffer(), fb2.ring_buffer.unfold_buffer()
    )
