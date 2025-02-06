import time


def sleep_s(s: float, partial_sleep_threshold: float = 0.0005, nsteps: int = 30):
    """
    Sleep for a specified duration with partial sleep optimization.

    Parameters
    ----------
    s : float
        The total duration to sleep in seconds.
    partial_sleep_threshold : float, optional
        The threshold duration above which partial sleep optimization is applied, by default 0.0005.
        I.e., only for durations `s` above the threshold, the optimization is applied.
    nsteps : int, optional
        The number of steps for partial sleep, by default 30. Empirical testing showed very good accuracy for 30.
        If you want to optimize for CPU load, reduce to `nsteps` > 4.

    """
    start = time.perf_counter()
    if s >= partial_sleep_threshold:
        partial_sleep(s, start, nsteps)

    # Sleep for the remaining time
    full_speed(s, start)


def partial_sleep(s: float, start: float, nsteps: int = 30):
    """Sleep for 90% of `s` or up to 30ms to the end, whatever is longer"""

    assert nsteps > 4, (
        "Empirical tests showed that irrespective of the size of `s`, sleeping"
        " seemes to maximally overshoot by a factor of 4. Keep nsteps larger "
        "than 4 to be on the safe side."
    )

    s_max = max(s - 0.03, s * 0.9)

    while time.perf_counter() - start < s_max:
        time.sleep(s / nsteps)


def full_speed(s: float, start: float):
    while time.perf_counter() - start < s:
        pass
