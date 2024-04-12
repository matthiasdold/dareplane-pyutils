import time


# TODO: Think of parametrizing the thresholds
def sleep_s(
    s: float,
):
    """

    Sleep for s seconds.

    Parameters
    ----------
    s : float
        time in seconds to sleep

    """

    start = time.perf_counter_ns()
    if s > 0.1:
        # If not yet reached 90% of the sleep duration, sleep in 10% increments
        # The 90% threshold is somewhat arbitrary but when testing intervals
        # with 1 ms to 500ms this produced very accurate results with deviation
        # less than 0.1% of the desired target value. On Mac M1 with python 3.11
        while time.perf_counter_ns() - start < (s * 1e9 * 0.9):
            time.sleep(s / 10)

    # Sleep for the remaining time
    while time.perf_counter_ns() - start < s * 1e9:
        pass
