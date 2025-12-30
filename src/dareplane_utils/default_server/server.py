import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from logging import Logger
from typing import Callable

from dareplane_utils.default_server.functions import (
    interpret_msg,
    stop_process,
    stop_thread,
)
from dareplane_utils.general.time import sleep_s
from dareplane_utils.logging.logger import get_logger


class UnknownMsgInterpretation(Exception):
    """Raised when the interpretation of a message is unknown"""

    pass


@dataclass
class DefaultServer:
    """
    A class representing a default server used and modified by other Dareplane projects.
    This server handles incoming TCP connections, interprets messages, and manages threads and processes.

    Attributes
    ----------
    port : int
        The port number on which the server listens. Default is 8080.
    ip : str
        The IP address on which the server listens. Default is "0.0.0.0".
    nlisten : int
        The maximum number of queued connections. Default is 10.
    name : str
        The name of the server. Default is "default_server".
    thread_stopper : Callable
        A function to stop threads. Default is `stop_thread`.
    proc_stopper : Callable
        A function to stop processes. Default is `stop_process`.
    msg_interpreter : Callable
        A function to interpret messages. Default is `interpret_msg`.
    pcommand_map : dict
        A dictionary mapping commands to their handlers.
    current_conn : socket.socket | None
        The current active connection.
    server_socket : socket.socket | None
        The server socket.
    threads : dict[str, tuple[threading.Thread, threading.Event]]
        A dictionary of active threads and their stop events.
    processes : dict[str, subprocess.Popen]
        A dictionary of active subprocesses.
    is_listening : bool
        A flag indicating whether the server is currently listening.
    logger : Logger
        The logger for the server.
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
    threads: dict[str, tuple[threading.Thread, threading.Event]] = field(
        default_factory=dict
    )
    processes: dict[str, subprocess.Popen] = field(default_factory=dict)
    is_listening: bool = False
    logger: Logger = get_logger(__name__)

    def init_server(self, stop_event: threading.Event = threading.Event()):
        """
        Initialize the server socket and set up the stop event.

        This method creates a socket, sets socket options, binds the socket to the specified IP and port,
        and sets it to listen for incoming connections. It also initializes a threading event to control
        the server's listening state.

        Parameters
        ----------
        stop_event : threading.Event, optional
            A threading event to control the server's listening state. Default is a new threading.Event.

        """
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
        """
        Start the server and listen for incoming connections.

        This method enters a loop where it waits for incoming TCP connections. When a connection is accepted,
        it handles incoming messages until the server is stopped. The method also manages the server's listening state
        and logs relevant information.
        """

        # main loop for running the server
        while not self.listen_stop_event.is_set():
            self.is_listening = True
            # for now just work on one / the current connection, implement
            # TODO: implement dealing with multiple connection
            try:
                current_conn, addr = self.server_socket.accept()  # type: ignore
            except Exception as err:
                self.logger.error(
                    f"Error accepting connection at {self.ip=}, {self.port=}, {self.server_socket=}"
                )
                raise err

            self.current_conn = current_conn
            self.current_conn.sendall(f"Connected to {self.name}\n".encode())
            while not self.listen_stop_event.is_set():
                try:
                    msg = self.current_conn.recv(2048)
                    if msg:
                        self.handle_msg(msg)

                except socket.timeout as err:
                    self.logger.info(f"Caugth timeout error {err=}")

                except KeyboardInterrupt as _:
                    self.logger.info("Received KeyboardInterrupt - stopping the server")

                except UnicodeDecodeError as _:
                    self.current_conn.sendall(
                        f"Was unable to decode {msg=} to ascii\n".encode()  # type: ignore
                    )
                except ConnectionResetError as err:
                    self.logger.info("Connection was reset by host- stopping the server")
                    self.is_listening = False
                    raise err
                except Exception as err:
                    self.logger.error(f"Caught error {err=}")
                    self.is_listening = False
                    raise err

        self.is_listening = False

    def handle_msg(self, msg: bytes):
        """
        Interpret the incoming message.

        This method processes the incoming message, checks if it is a concatenation of multiple commands,
        and handles each command individually. It also logs the received message and handles any errors that occur
        during message processing.

        Parameters
        ----------
        msg : bytes
            The incoming message to be interpreted.
        """

        self.logger.info(f"Received: {msg}")
        # Check if msg is concatenation of multiple commands, happends if
        # processing of a single command takes to long so multiple commands
        # end up at the socket
        if b";" in msg:
            for pc in msg.split(b";"):
                if pc != b"":
                    self.handle_msg(pc)
        else:

            # Default functionality which should always be there
            # and the same for all servers
            is_default_command = self.default_msg_interpretation(msg)

            # if not a default command, check the pcmommand map
            if not is_default_command:
                self.logger.debug("Interpreting non-default message")

                msg = msg.replace(b"\r\n", b"")
                # common start byte, would lead to an error in decode otherwise # noqa
                msg = msg.replace(b"\xc2", b"")
                # Ignore blanks -> e.g. accidental return in telnet
                if (
                    msg != b""
                    and msg.decode("ascii").split("|")[0] in self.pcommand_map.keys()
                ):
                    self.msg_interpretation(msg)  # type: ignore

                else:
                    self.logger.warning(f"Unknown pcomm in {msg=}")

    def default_msg_interpretation(self, msg: bytes) -> bool:
        """
        Interpret default messages.

        This method handles default commands such as stopping processes or threads, closing the server,
        and retrieving the list of available commands. It logs relevant information and performs the necessary actions
        based on the received message.

        Parameters
        ----------
        msg : bytes
            The incoming message to be interpreted.

        Returns
        -------
        bool
            True if the message was a default command, False otherwise.
        """
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
            )  # common start byte, would lead to an error in decode otherwise

            self.current_conn.sendall(  # type: ignore
                ("|".join(list(self.pcommand_map.keys()) + ["STOP", "CLOSE"])).encode()
            )
        elif msg == b"UP":
            self.current_conn.sendall(b"1")  # type: ignore
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
            self.logger.debug(f"{msg=} returned a subprocess after interpretation")
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
        self.logger.debug(f"Closing threads: {self.threads.items()}")
        removed_threads = []
        for thid, (th, stop_event) in self.threads.items():
            stop_event.set()
            self.thread_stopper(th, logger=self.logger)
            removed_threads.append(thid)
        for k in removed_threads:
            self.threads.pop(k, None)

    def close_processes(self):
        # clean up potential subprocesses
        self.logger.debug(f"Closing processes: {self.processes.items()}")
        removed_sprocesses = []
        for spid, sp in self.processes.items():
            self.proc_stopper(sp, logger=self.logger)
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
    DefaultCallbackServer

    The default server extended with a callback capability.

    This class extends the DefaultServer class to include a callback mechanism. It allows the server to send
    callback messages to connected clients. The callback messages are stored in a stack and sent to the client
    in a separate thread.

    Attributes
    ----------
    callback_stack : list[str]
        A list of callback payloads, which will be sent to connected clients.
    """

    callback_stack: list[str] = field(
        default_factory=list
    )  # list of callback payloads, which will be sent to connected clients

    def start_listening(self):
        # main loop for running the server
        self.logger.debug("Callback server starting to listen")
        while not self.listen_stop_event.is_set():
            self.is_listening = True
            # for now just work on one / the current connection, implement
            # TODO: refactor this part for a cleaner implementation of the dealing with callbacks -> all copy and paste from above, besides 4 lines
            try:
                current_conn, addr = self.server_socket.accept()

                # Initialize the callback thread
                callback_stop_event = threading.Event()
                callback_thread = threading.Thread(
                    target=process_callbacks,
                    args=(self, callback_stop_event),
                )
                # add to automatically manage closing
                self.threads["callbacks"] = (
                    callback_thread,
                    callback_stop_event,
                )
                callback_thread.start()

            except Exception as err:
                self.logger.error(
                    f"Error accepting connection at {self.ip=}, {self.port=}, "
                    f"{self.server_socket=}"
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
                        is_default_command = self.default_msg_interpretation(msg)

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
                    self.logger.info("Received KeyboardInterrupt - stopping the server")

                except UnicodeDecodeError as _:
                    self.current_conn.sendall(
                        f"Was unable to decode {msg=} to ascii\n".encode()  # type: ignore
                    )
                except Exception as err:
                    self.logger.error(f"Caught error {err=}")
                    self.is_listening = False
                    raise err

        self.is_listening = False


def process_callbacks(server: DefaultCallbackServer, stop_event: threading.Event):
    """
    Process callback messages and send them to the connected client.

    This function runs in a separate thread and continuously checks the callback stack for messages.
    If there are messages in the stack, it sends them to the connected client and removes them from the stack.
    The function stops processing when the stop event is set.

    Parameters
    ----------
    server : DefaultCallbackServer
        The server instance that contains the callback stack and the current connection.
    stop_event : threading.Event
        An event that, when set, signals the function to stop processing callbacks.
    """

    # Process callback stack
    while not stop_event.is_set():
        while len(server.callback_stack) > 0:
            server.current_conn.sendall(server.callback_stack.pop(0).encode())  # type: ignore
            sleep_s(0.001)
