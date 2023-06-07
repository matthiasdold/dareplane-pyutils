import orjson
import time
import psutil
import signal
import threading
import subprocess

from typing import Callable

from dareplane_utils.logging.logger import get_logger
from logging import Logger


logger = get_logger(__name__)


def parse_msg(msg: str, pcommand_map: dict) -> tuple[Callable, tuple, dict]:
    """
    Parse a bytes msg and return the relevant function + potential kwargs

    Parameters
    ----------
    msg : str
        the msg which arrived at the socket
    pcommand_map : dict
        primary command map to link a <primary_command_str> to a Callable

    Returns
    -------
    func : Callable
        the function to call
    args : tuple
        args to use for the function call
    kwargs : dict
        kwargs to pass to the function

    """

    logger.info(f"Splitting: {msg=}")
    split = msg.decode().split("|")
    pcomm = split[0]
    args = split[1:-1]
    logger.info(f"{split[-1:]}")
    kwargs = orjson.loads(split[-1]) if len(split) > 1 else {}

    return pcommand_map[pcomm], args, kwargs


# This is the default behavior for interpretation of messages
def interpret_msg(
    binary_msg: str, pcommand_map: dict, **kwargs
) -> threading.Thread | subprocess.Popen | int:
    """Interpret a message and start a threading, subprocess or return an int

    Parameters
    ----------
    binary_msg : str
        the binary string msg as received by the socket
    pcommand_map : dict
        a map of primary commands to functions
    **kwargs
        additonally passed kwargs to the function

    Returns
    -------
    threading.Thread | subprocess.Popen | int
        depending on the implementation of this function in individual modules
        this function could return a thread, subprocess or just integers.
        the server will keep track of subprocesses and threads and will close
        them during the shutdown
    """
    # Get correct function and parse kwargs from json payload
    func, pargs, pkwargs = parse_msg(binary_msg, pcommand_map=pcommand_map)

    # Add kwargs which might have been passed to the server     # noqa
    pkwargs.update(**kwargs)
    logger.debug(f"Interpreting {func=}, {pargs=}, {pkwargs=}")
    ret = func(*pargs, **pkwargs)

    return ret


def stop_thread(thread: threading.Thread):
    """Stopping a thread, the standard way

    Parameters
    ----------
    thread : threading.Thread

    """
    logger.info("Stopping threads")
    # stop_event.set()
    # logger.info("Stop event was set, joining the threads")
    try:
        thread.join()  # clean-up
    except RuntimeError as e:
        if str(e) != "cannot join thread before it is started":
            raise
        else:
            logger.info("Closing thread before it started")


def stop_process(process: subprocess.Popen):
    """Close all child processes of a Popen instance"""
    parent_ps = psutil.Process(process.pid)
    max_iter = 5
    i, j = 0, 0

    # close the children
    while parent_ps and parent_ps.children() != [] and i <= max_iter:
        if i > 0:
            time.sleep(0.2)
        # try SIGINT first
        if i <= max_iter - 1:
            for ch in parent_ps.children():
                logger.debug(f"Sending kill to child process={ch}")
                ch.send_signal(signal.SIGINT)
        # last iteration, if it is not gone yet, kill it
        else:
            for ch in parent_ps.children():
                logger.debug(f"Sending kill to child process={ch}")
                ch.kill()

        i += 1
        logger.debug(f"Remaining childern={parent_ps.children()}")
    #
    # while psutil.pid_exists(parent_ps.pid) and j <= max_iter:
    #     parent_ps.send_signal(signal.SIGINT)
    #     if j > 0:
    #         time.sleep(0.2)
    #
    #     logger.debug(f"Sent SIGINT to parent={parent_ps.pid}")
    #
    # parent_ps.kill()
