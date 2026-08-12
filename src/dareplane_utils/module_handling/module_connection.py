from dataclasses import dataclass

from dareplane_utils.module_handling.communication import (
    Communicator,
    SocketCommunicator,
)
from dareplane_utils.module_handling.launcher import Launcher


@dataclass
class ModuleConnection:
    """A class to manage the connection to a module, including launching the module and communicating with it."""

    name: str
    launcher: Launcher
    communicator: Communicator | None = None

    def launch_module(self, relaunch: bool = False, **popen_kwargs):
        self.launcher.launch(relaunch=relaunch, **popen_kwargs)

    def connect_to_module(self):
        if self.communicator:
            try:
                self.communicator.connect()
            except ConnectionRefusedError as e:
                # If connection failed because host process is not running, give a more specific error
                if (
                    self.launcher.process is not None  # type: ignore
                    and self.launcher.process.poll() is not None  # type: ignore
                ):
                    raise ConnectionRefusedError(
                        f"Cannot connect to module {self.name=}. Host process not running."
                    )
                else:
                    raise e

    def stop_connection(self):
        if self.communicator:
            self.communicator.disconnect()

    def stop_process(self):
        self.launcher.terminate()

    def send_message(self, msg: bytes):
        if not msg.endswith(b";"):
            msg += b";"

        if self.communicator:
            self.communicator.send(msg)
        else:
            raise ConnectionError(
                f"Cannot send message to module {self.name=} because it has no communicator"
            )

    def receive_message(self, size: int) -> bytes:
        if isinstance(self.communicator, SocketCommunicator):
            return self.communicator.receive(size)
        else:
            raise NotImplementedError(
                f"Receive message is only implemented for SocketCommunicator, but have {type(self.communicator)}"
            )

    def start(self, relaunch: bool = False, **popen_kwargs):
        """Start the module and establish communication"""
        self.launch_module(relaunch=relaunch, **popen_kwargs)
        self.connect_to_module()

    def stop(self):
        """Stop communication and terminate process"""
        self.stop_connection()
        self.stop_process()

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

