from dataclasses import dataclass
from dataclasses import field
import time
from subprocess import Popen

from dareplane_utils.module_handling.launcher import Launcher
from dareplane_utils.module_handling.communication import Communicator, SocketCommunicator
    
@dataclass
class ModuleConnection:
    """A class to manage the connection to a module, including launching the module and communicating with it."""
    name: str
    launcher: Launcher
    communicator: Communicator | None = None

    def start_module_server(self):
        self.process = self.launcher.launch()

    def connect_to_module(self):
        if self.communicator:
            try:
                self.communicator.connect()
            except ConnectionRefusedError as e:
                    # If connection failed because host process is not running, give a more specific error
                    if self.process is not None and self.process.poll() is not None:
                        raise ConnectionRefusedError(
                            f"Cannot connect to module {self.name=} at {self.ip}:{self.port}. Host process not running."
                        )
                    else:
                        raise e

    def stop_connection(self):
        if self.communicator:
            self.communicator.disconnect()

    def stop_process(self):
        if self.process is not None:
            self.launcher.terminate(self.process)
            self.process = None

    def send_message(self, msg: bytes):
        if self.communicator:
            self.communicator.send(msg)
        else:
            raise ConnectionError(f"Cannot send message to module {self.name=} because it has no communicator")
        
    def receive_message(self, size: int) -> bytes:
        if isinstance(self.communicator, SocketCommunicator):
            return self.communicator.receive(size)
        else:
            raise NotImplementedError(f"Receive message is only implemented for SocketCommunicator, but have {type(self.communicator)}")

    def start(self):
        """Start the module and establish communication"""
        self.start_module_server()
        self.connect_to_module()
    
    def stop(self):
        """Stop communication and terminate process"""
        self.stop_connection()
        self.stop_process()
    
    def __del__(self):
        try:
            self.stop()
        except:
            pass