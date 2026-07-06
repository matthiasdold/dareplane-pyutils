from abc import ABC, abstractmethod
from socket import SHUT_RDWR
import socket
import time

from subprocess import Popen

class Communicator(ABC):
    """Base class for communication with modules"""
    
    @abstractmethod
    def connect(self) -> None:
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        pass
    
    @abstractmethod
    def send(self, data: bytes) -> None:
        pass
    
    @abstractmethod
    def receive(self, size: int) -> bytes:
        pass


class SocketCommunicator(Communicator):
    def __init__(self, ip: str, port: int, name: str, 
                 retry_after_s: float = 1, max_connect_retries: int = 3, logger=None):
        self.ip = ip
        self.port = port
        self.name = name
        self.retry_after_s = retry_after_s
        self.max_connect_retries = max_connect_retries
        self.logger = logger
        self.socket_c = None
        self.near_port = 0
    
    def connect(self):
        if self.logger:
            self.logger.debug(f"{self.name=} - connecting socket to {self.ip}:{self.port}")

        try:
            self.socket_c = self.create_socket_client(
                host_ip=self.ip,
                port=self.port,
                retry_connection_after_s=self.retry_after_s,
            )
        except ConnectionRefusedError as err:
            if self.logger:
                self.logger.debug(
                    f"{self.name=}- Cannot connect to socket at {self.ip}:{self.port}. Connection refused."
                )
            raise err

        # Time-out as non of the sockets should block indefinitely
        self.socket_c.setblocking(0)

        # read out the actual socket -> if port == 0, a random free port
        # was assigned
        self.near_port = self.socket_c.getsockname()[1]

        # There might be a response / confirmation of the connetion
        try:
            self.socket_c.settimeout(1)
            # msg = self.socket_c.recv(2048 * 8)
            fragments = []
            while True:
                chunk = self.socket_c.recv(1024)
                if not chunk:
                    break
                fragments.append(chunk)
            msg = b"".join(fragments)

            if self.logger:
                self.logger.debug(f"connection returned: {msg.decode()}")
            self.socket_c.settimeout(None)
        except ConnectionResetError as err:
            if self.logger:
                self.logger.debug(
                    f"Connection refused for - {self.name=}, {self.ip=}, {self.port=}"
                )
            raise err
        except TimeoutError as err:
            if self.logger:
                self.logger.debug(f"No response upon connection for {self.name=} - {err=}")
        except Exception as err:
            if self.logger:
                self.logger.debug(f"Other error upon connection for {self.name=}, {err=}")
            raise err
    
    def create_socket_client(
            self, host_ip: str, port: int, retry_connection_after_s: float = 1
        ) -> socket.socket:
        """
        Create a socket client and attempt to connect to a specified host and port.

        This function attempts to establish a TCP connection to the specified host and port.
        It retries the connection up to a maximum number of times (3) if the connection is refused.
        If the connection is successful, the socket object is returned.

        Parameters
        ----------
        host_ip : str
            The IP address of the host to connect to.
        port : int
            The port number on the host to connect to.
        retry_connection_after_s : float, optional
            The number of seconds to wait between connection attempts, by default 1.

        Returns
        -------
        socket.socket
            A socket object representing the connection to the host.

        Raises
        ------
        ConnectionRefusedError
            If the connection is refused after the maximum number of 3 retries.
        """
        conn_try = 0
        while conn_try < self.max_connect_retries:
            try:
                if self.logger:
                    self.logger.debug(f"Trying connection to: {host_ip=}, {port=}")
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((host_ip, port))
                if self.logger:
                    self.logger.debug(f"Connected to: {host_ip=}, {port=} using {s=}")
                return s
            except ConnectionRefusedError:
                if self.logger:
                    self.logger.debug(
                        f"Connection refused for - {self.name=}, {host_ip=}, {port=}. Retrying in {retry_connection_after_s} seconds..."
                    )

                # Close the socket and start fresh as otherwise
                # we will get a an Errno 22 in the second try
                s.close()

                time.sleep(retry_connection_after_s)
                pass
            conn_try += 1

        raise ConnectionRefusedError(
            f"Connection refused after {self.max_connect_retries} tries: {host_ip=}, {port=}"
        )
    
    def disconnect(self) -> None:
        if not self.socket_c:
            return
        try:
            if self.logger:
                self.logger.debug(f"{self.name} trying to gracefully shurtdown {self.socket_c}")
            self.socket_c.shutdown(SHUT_RDWR)
        except OSError:
            if self.logger:
                self.logger.debug(
                    f"{self.name} caught OSError on connection.shutdown"
                    " - connection already closed?"
                )
        finally:
            try:
                self.socket_c.close()
            except OSError:
                pass
            self.socket_c = None
                
    def send(self, data: bytes) -> None:
        if self.socket_c:
            self.socket_c.sendall(data)
    
    def receive(self, size: int) -> bytes:
        if self.socket_c:
            return self.socket_c.recv(size)
        return b""
