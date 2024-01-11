import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from logging import Logger
from typing import Callable

from dareplane_utils.default_server.functions import (interpret_msg,
                                                      stop_process,
                                                      stop_thread)
from dareplane_utils.logging.logger import get_logger


class UnknownMsgInterpretation(Exception):
    """Raised when the interpretation of a message is unknown"""

    pass


@dataclass
class DefaultServer:
    """
    The default server which is being used and modified by pther dareplane
    projects
    """

    port: int = 8080
    ip: str = "0.0.0.0"
    nlisten: int = 10
    name: str = "default_server"
    thread_stopper: Callable = stop_thread
    proc_stopper: Callable = stop_process
    msg_interpreter: Callable = interpret_msg
    pcommand_map: dict = field(default_factory=dict)
    current_conn: socket.socket | None = None
    server_socket: socket.socket | None = None
    threads: dict[str, (threading.Thread, threading.Event)] = field(
        default_factory=dict
    )
    processes: dict[str, subprocess.Popen] = field(default_factory=dict)
    is_listening: bool = False
    logger: Logger = get_logger(__name__)

    def init_server(self, stop_event: threading.Event = threading.Event()):
        # spawn a socket
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.settimeout(None)
        server_socket.bind((self.ip, self.port))
        server_socket.listen(self.nlisten)
        self.server_socket = server_socket

        # adding a threading style stop event to potentially run listening in a separate thread
        # and still being able to stop from the controlling script. Otherwise only the socket client could send a stop
        self.listen_stop_event: threading.Event = stop_event

    def start_listening(self):
        # main loop for running the server
        while not self.listen_stop_event.is_set():
            self.is_listening = True
            # for now just work on one / the current connection, implement
            # TODO: implement dealing with multiple connection
            try:
                current_conn, addr = self.server_socket.accept()
            except Exception as err:
                self.logger.error(
                    f"Error accepting connection at {self.ip=}, {self.port=}, {self.server_socket=}"
                )
                raise err

            self.current_conn = current_conn
            self.current_conn.sendall(f"Connected to {self.name}\n".encode())
            while not self.listen_stop_event.is_set():
                try:
                    msg = self.current_conn.recv(1024)
                    if msg:
                        self.logger.info(f"Received: {msg}")
                        # interpret the message

                        # Default functionality which should always be there
                        # and the same for all servers
                        is_default_command = self.default_msg_interpretation(
                            msg
                        )

                        # if not a default command, check the pcmommand map
                        if not is_default_command:
                            msg = msg.replace(b"\r\n", b"")
                            # common start byte, would lead to an error in decode otherwise # noqa
                            msg = msg.replace(b"\xc2", b"")
                            # Ignore blanks -> e.g. accidental return in telnet
                            if (
                                msg != b""
                                and msg.decode("ascii").split("|")[0]
                                in self.pcommand_map.keys()
                            ):
                                self.msg_interpretation(msg)

                            else:
                                self.logger.warning(f"Unknown pcomm in {msg=}")

                except socket.timeout as err:
                    self.logger.info(f"Caugth timeout error {err=}")

                except KeyboardInterrupt as _:
                    self.logger.info(
                        "Received KeyboardInterrupt - stopping the server"
                    )

                except UnicodeDecodeError as _:
                    self.current_conn.sendall(
                        f"Was unable to decode {msg=} to ascii\n".encode()
                    )
                except Exception as err:
                    self.logger.error(f"Caught error {err=}")
                    self.is_listening = False
                    raise err

        self.is_listening = False

    def default_msg_interpretation(self, msg: str) -> bool:
        """This contains the default interpretation"""
        if (
            msg == b"STOP\r\n"
            or msg == b"STOP"
            or msg == b"STOP|\r\n"
            or msg == b"STOP|"
        ):
            # Stop any processes or threads which could have been spawend by interpreting messages
            self.close_threads()
            self.close_processes()

        # Closing the server
        elif (
            msg == b"CLOSE\r\n"
            or msg == b"CLOSE"
            or msg == b"CLOSE|\r\n"
            or msg == b"CLOSE|"
        ):
            # stop listening for TCP connections and traffic
            self.listen_stop_event.set()

        elif b"GET_PCOMMS" in msg:
            msg = msg.replace(b"\r\n", b"")
            msg = msg.replace(
                b"\xc2", b""
            )  # common start byte, would lead to an error in decode otherwise # noqa

            self.current_conn.sendall(
                (
                    "|".join(
                        list(self.pcommand_map.keys()) + ["STOP", "CLOSE"]
                    )
                ).encode()
            )
        elif msg == b"UP":
            self.current_conn.sendall(b"1")
        else:
            # Nothing was done
            return False

        return True

    def msg_interpretation(self, msg: str):
        """Interpret the message and perform book keeping if necessary"""
        ret = interpret_msg(msg, self.pcommand_map, logger=self.logger)

        # the book keeping part
        if isinstance(ret, int):
            self.logger.debug(f"{msg=} returned {ret=} after interpretation")
            pass

        # any implementation returning a thread should return the stop_event alongside
        # TODO: think about how this can be enforced
        elif (
            isinstance(ret, tuple)
            and isinstance(ret[0], threading.Thread)
            and isinstance(ret[1], threading.Event)
        ):
            self.logger.debug(f"{msg=} returned a thread after interpretation")
            self.threads[f"{time.time_ns()}_{msg}"] = ret

        elif isinstance(ret, subprocess.Popen):
            self.logger.debug(
                f"{msg=} returned a subprocess after interpretation"
            )
            self.processes[f"{time.time_ns()}_{msg}"] = ret

        else:
            raise UnknownMsgInterpretation(
                "Unknown msg interpretation return for "
                f"{msg=} and {ret=} "
                " valid interpretations should return int|tuple[threading.Thread, threading.Event]|subprocess.Popen"
            )

    def shutdown(self):
        """Shutdown the server and close all connections"""
        self.logger.info(f"Shutting down {self.name}")
        if self.current_conn:
            self.current_conn.close()

        if self.server_socket:
            self.server_socket.close()
        self.close_threads()
        self.close_processes()

    def close_threads(self):
        # clean up potential threads
        removed_threads = []
        for thid, (th, stop_event) in self.threads.items():
            stop_event.set()
            self.thread_stopper(th)
            removed_threads.append(thid)
        for k in removed_threads:
            self.threads.pop(k, None)

    def close_processes(self):
        # clean up potential subprocesses
        removed_sprocesses = []
        for spid, sp in self.processes.items():
            self.proc_stopper(sp)
            removed_sprocesses.append(spid)
        for k in removed_sprocesses:
            self.processes.pop(k, None)

    def __del__(self):
        # also use the shutdown in the finalizer in case the instance is
        # removed from memory
        self.shutdown()


@dataclass
class DefaultCallbackServer(DefaultServer):
    """
    The default server extended with a callback capability
    """

    callback_stack: list[str] = field(
        default_factory=list
    )  # list of callback payloads, which will be sent to connected clients

    def start_listening(self):
        # main loop for running the server
        while not self.listen_stop_event.is_set():
            self.is_listening = True
            # for now just work on one / the current connection, implement
            # TODO: implement dealing with multiple connection
            # TODO: refactor this part for a cleaner implementation of the dealing with callbacks -> all copy and paste from above, besides 4 lines
            try:
                current_conn, addr = self.server_socket.accept()
            except Exception as err:
                self.logger.error(
                    f"Error accepting connection at {self.ip=}, {self.port=}, {self.server_socket=}"
                )
                raise err

            self.current_conn = current_conn
            self.current_conn.sendall(f"Connected to {self.name}\n".encode())
            while not self.listen_stop_event.is_set():
                try:
                    # Process incoming
                    msg = self.current_conn.recv(1024)
                    if msg:
                        self.logger.info(f"Received: {msg}")
                        # interpret the message

                        # Default functionality which should always be there
                        # and the same for all servers
                        is_default_command = self.default_msg_interpretation(
                            msg
                        )

                        # if not a default command, check the pcmommand map
                        if not is_default_command:
                            msg = msg.replace(b"\r\n", b"")
                            # common start byte, would lead to an error in decode otherwise # noqa
                            msg = msg.replace(b"\xc2", b"")
                            # Ignore blanks -> e.g. accidental return in telnet
                            if (
                                msg != b""
                                and msg.decode("ascii").split("|")[0]
                                in self.pcommand_map.keys()
                            ):
                                self.msg_interpretation(msg)

                            else:
                                self.logger.warning(f"Unknown pcomm in {msg=}")

                        # Process callback stack
                        while len(self.callback_stack) > 0:
                            self.current_conn.sendall(
                                self.callback_stack.pop(0).encode()
                            )

                except socket.timeout as err:
                    self.logger.info(f"Caugth timeout error {err=}")

                except KeyboardInterrupt as _:
                    self.logger.info(
                        "Received KeyboardInterrupt - stopping the server"
                    )

                except UnicodeDecodeError as _:
                    self.current_conn.sendall(
                        f"Was unable to decode {msg=} to ascii\n".encode()
                    )
                except Exception as err:
                    self.logger.error(f"Caught error {err=}")
                    self.is_listening = False
                    raise err

        self.is_listening = False
