import itertools
import socket
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from logging import Logger

from dareplane_utils.default_server.functions import (
    interpret_msg,
    stop_process,
    stop_thread,
)
from dareplane_utils.general.time import sleep_s
from dareplane_utils.logging.logger import get_logger

# Commands handled by the server itself, before any pcommand_map lookup. Listed
# in GET_PCOMMS responses so clients can discover them without a map entry.
BUILT_IN_PCOMMS = ["STOP", "CLOSE", "GET_PCOMMS", "UP"]


class UnknownMsgInterpretation(Exception):
    """Raised when the interpretation of a message is unknown"""


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
    delimiter : bytes
        The byte sequence terminating a single command on the wire. Incoming
        data is buffered until a delimiter is found, so commands split across
        multiple TCP segments are reassembled. Default is b";".
    """

    port: int = 8080
    ip: str = "0.0.0.0"
    nlisten: int = 10
    name: str = "default_server"
    # how long accept() blocks before the listen loop re-checks the stop event
    accept_timeout_s: float = 0.5
    delimiter: bytes = b";"
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
    # Book keeping keys must stay unique even when several commands are handled
    # within one clock tick. time.time_ns() returns nanosecond units but not
    # nanosecond resolution - ~15.6ms on Windows - so the timestamp alone
    # collides for identical commands arriving in a single packet.
    _bookkeeping_counter: itertools.count = field(
        default_factory=itertools.count, repr=False
    )
    logger: Logger = get_logger(__name__)

    def init_server(self, stop_event: threading.Event | None = None):
        """
        Initialize the server socket and set up the stop event.

        This method creates a socket, sets socket options, binds the socket to the specified IP and port,
        and sets it to listen for incoming connections. It also initializes a threading event to control
        the server's listening state.

        Parameters
        ----------
        stop_event : threading.Event | None, optional
            A threading event to control the server's listening state. If None, a
            fresh event is created for this server.

        """
        # spawn a socket
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # A finite timeout keeps accept() interruptible: the loop in
        # start_listening can only re-check listen_stop_event once accept()
        # returns, so a blocking accept() would ignore a stop request until the
        # next client connects.
        server_socket.settimeout(self.accept_timeout_s)
        server_socket.bind((self.ip, self.port))
        server_socket.listen(self.nlisten)
        self.server_socket = server_socket

        # adding a threading style stop event to potentially run listening in a separate thread
        # and still being able to stop from the controlling script. Otherwise only the socket client could send a stop
        self.listen_stop_event: threading.Event = (
            stop_event if stop_event is not None else threading.Event()
        )

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
                current_conn, _ = self.server_socket.accept()  # type: ignore
            except TimeoutError:
                # no client within accept_timeout_s - go back and re-check the
                # stop event, this is the normal idle path
                continue
            except Exception as err:
                if self.listen_stop_event.is_set():
                    break
                self.logger.error(  # type: ignore
                    f"Error accepting connection at {self.ip=}, {self.port=}, {self.server_socket=}"
                )
                raise err

            # an accepted socket inherits the listening socket's timeout - keep the
            # connection itself blocking so recv() is not woken every interval
            current_conn.settimeout(None)
            self.current_conn = current_conn
            self.on_connection_accepted()

            try:
                self.current_conn.sendall(f"Connected to {self.name}\n".encode())
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                self.logger.info("Client disconnected before banner could be sent")
                continue

            self.process_connection()
            # process_connection() only returns once the client is gone or the
            # server is stopping - either way the connection is finished with
            self.on_connection_closed()

        self.is_listening = False

    def on_connection_accepted(self):
        """Hook invoked after a connection was accepted, before the banner is sent"""

    def on_connection_closed(self):
        """Hook invoked after the current connection ended, before the next accept"""

    def process_connection(self):
        """
        Read from the current connection and dispatch complete commands.

        Data is accumulated in a buffer and only split off for handling once a
        `self.delimiter` is found. This is required because TCP provides a byte
        stream without message boundaries - a single `recv` can return a partial
        command or several concatenated commands. An incomplete trailing
        fragment stays in the buffer until the rest of it arrives.
        """
        buffer = b""

        while not self.listen_stop_event.is_set():
            try:
                chunk = self.current_conn.recv(2048)  # type: ignore
                if not chunk:
                    self.logger.info("Client disconnected")
                    break

                buffer += chunk
                while self.delimiter in buffer:
                    msg, buffer = buffer.split(self.delimiter, 1)
                    if msg.strip():
                        self.handle_msg(msg)

            except TimeoutError as err:
                self.logger.info(f"Caugth timeout error {err=}")

            except KeyboardInterrupt as _:
                self.logger.info("Received KeyboardInterrupt - stopping the server")

            except UnicodeDecodeError as _:
                self.current_conn.sendall(  # type: ignore
                    f"Was unable to decode {msg=} to ascii\n".encode()  # type: ignore
                )
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                self.logger.info("Connection was reset by host")
                break
            except Exception as err:
                # as in start_listening: a blocked recv() fails when the socket is
                # closed to stop the server, which is an intentional exit
                if self.listen_stop_event.is_set():
                    break
                self.logger.error(f"Caught error {err=}")
                self.is_listening = False
                raise err

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

        # UP is used as a periodic health check - it is not logged at all as it
        # would drown out the actual PCOMMS
        if msg.replace(b"\r\n", b"").rstrip(b"|") != b"UP":
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
                # common start byte, would lead to an error in decode otherwise
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
                ("|".join(list(self.pcommand_map.keys()) + BUILT_IN_PCOMMS)).encode()
            )
        # same variants as STOP/CLOSE above - clients may terminate with \r\n or
        # an empty argument separator, both of which must still be recognised
        elif msg in (b"UP", b"UP\r\n", b"UP|\r\n", b"UP|"):
            self.current_conn.sendall(b"1")  # type: ignore
        else:
            # Nothing was done
            return False

        return True

    def _bookkeeping_key(self, msg: bytes) -> str:
        """Build a unique key for the threads/processes book keeping.

        The counter is required because several identical commands can arrive in
        a single packet and be handled within one clock tick, which would make a
        purely timestamp based key collide and silently drop entries.
        """
        return f"{time.time_ns()}_{next(self._bookkeeping_counter)}_{msg}"

    def msg_interpretation(self, msg: bytes):
        """Interpret the message and perform book keeping if necessary"""
        ret = interpret_msg(msg, self.pcommand_map, logger=self.logger)

        # the book keeping part
        if isinstance(ret, int):
            self.logger.debug(f"{msg=} returned {ret=} after interpretation")

        # any implementation returning a thread should return the stop_event alongside
        # TODO: think about how this can be enforced
        elif (
            isinstance(ret, tuple)
            and isinstance(ret[0], threading.Thread)
            and isinstance(ret[1], threading.Event)
        ):
            self.logger.debug(f"{msg=} returned a thread after interpretation")
            self.threads[self._bookkeeping_key(msg)] = ret

        elif isinstance(ret, subprocess.Popen):
            self.logger.debug(f"{msg=} returned a subprocess after interpretation")
            self.processes[self._bookkeeping_key(msg)] = ret

        else:
            raise UnknownMsgInterpretation(
                "Unknown msg interpretation return for "
                f"{msg=} and {ret=} "
                " valid interpretations should return int|tuple[threading.Thread, threading.Event]|subprocess.Popen"
            )

    def shutdown(self):
        """Shutdown the server and close all connections"""
        self.logger.info(f"Shutting down {self.name}")
        # Signal first: closing the sockets below makes a blocked accept()/recv()
        # raise, and the listen loop only treats that as an orderly exit when the
        # stop event is already set. Without this, shutting down a running server
        # surfaces an OSError on the listening thread.
        if hasattr(self, "listen_stop_event"):
            self.listen_stop_event.set()

        if self.current_conn:
            self.current_conn.close()

        if self.server_socket:
            self.server_socket.close()
        self.close_threads()
        self.close_processes()

    def close_threads(self):
        # clean up potential threads
        self.logger.debug(f"Closing threads: {self.threads.items()}")
        # snapshot: stopping a thread can take long enough for another one to be
        # registered, and mutating the dict while iterating it raises
        removed_threads = []
        for thid, (th, stop_event) in list(self.threads.items()):
            stop_event.set()
            self.thread_stopper(th, logger=self.logger)
            removed_threads.append(thid)

        for k in removed_threads:
            self.threads.pop(k, None)

    def close_processes(self):
        # clean up potential subprocesses
        self.logger.debug(f"Closing processes: {self.processes.items()}")
        removed_sprocesses = []
        for spid, sp in list(self.processes.items()):  # snapshot, see close_threads
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
    callback_stack : collections.deque[str]
        Callback payloads, which will be sent to connected clients. A deque is
        used because `append` and `popleft` are atomic, so a producer thread and
        the callback thread can share it without additional locking.
    """

    callback_stack: deque[str] = field(default_factory=deque)

    def on_connection_closed(self):
        """Stop the callback thread belonging to the connection that just ended.

        The thread is bound to that socket, so it has nothing left to do. Relying
        on a failing send instead would keep it alive for as long as the stack is
        empty, and only surface the disconnect on the next payload.
        """
        self.close_threads()

    def on_connection_accepted(self):
        """Spawn the thread sending queued callbacks to the freshly connected client"""
        # Defensive: normally on_connection_closed() already stopped the previous
        # thread, but a client that disconnects before the banner is sent skips it.
        self.close_threads()

        callback_stop_event = threading.Event()
        callback_thread = threading.Thread(
            target=process_callbacks,
            args=(
                self,
                self.current_conn,
                callback_stop_event,
            ),  # make connection explicit such that no silent handover/reference to another future connection can happen
            daemon=True,
        )
        self.threads[self._bookkeeping_key(b"callbacks")] = (
            callback_thread,
            callback_stop_event,
        )
        callback_thread.start()


def process_callbacks(
    server: DefaultCallbackServer,
    conn: socket.socket,
    stop_event: threading.Event,
):
    """
    Process callback messages and send them to a specific connected client.

    This function runs in a separate thread and continuously checks the callback stack for messages.
    If there are messages in the stack, it sends them to the connected client and removes them from the stack.
    The function stops processing when the stop event is set.

    The thread is bound to `conn` rather than reading `server.current_conn`, so it
    can never deliver payloads queued for one client to the next one. It ends when
    the stop event is set - which `DefaultCallbackServer.on_connection_closed`
    does as soon as the client disconnects - or when a send fails. Delivery is at
    most once: a payload popped for a connection that dies is not re-queued.

    Parameters
    ----------
    server : DefaultCallbackServer
        The server instance holding the callback stack.
    conn : socket.socket
        The connection this thread sends to, as accepted by `start_listening`.
    stop_event : threading.Event
        An event that, when set, signals the function to stop processing callbacks.
    """

    # Process callback stack
    while not stop_event.is_set():
        try:
            payload = server.callback_stack.popleft()
        except IndexError:  # nothing queued - deque keeps this atomic
            sleep_s(0.001)
            continue

        try:
            conn.sendall(payload.encode())
        except OSError:
            # the socket was closed under us: either an orderly shutdown, or the
            # client vanished. Either way this thread's connection is gone.
            if not stop_event.is_set():
                server.logger.warning(
                    "Callback connection lost, stopping callback thread"
                )
            break
