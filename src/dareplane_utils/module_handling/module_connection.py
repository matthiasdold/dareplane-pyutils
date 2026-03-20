from dataclasses import dataclass
from dataclasses import field
import time
from subprocess import Popen

from dareplane_utils.module_handling.launcher import Launcher
from dareplane_utils.module_handling.communication import Communicator
    
@dataclass
class ModuleConnection:
    """A class to manage the connection to a module, including launching the module and communicating with it."""
    name: str
    launcher: Launcher
    communicator: Communicator | None = None
    pcomms: list[str] = field(default_factory=list)
    module_kind: str = ""
    process: Popen | None = None

    @property
    def socket_c(self):
        if self.communicator and hasattr(self.communicator, "socket_c"):
            return self.communicator.socket_c
        return None

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

    def get_pcommands(self):
        if self.socket_c is None:
            return

        self.socket_c.sendall(b"GET_PCOMMS")
        time.sleep(0.1)
        msg = self.socket_c.recv(2048 * 8)
        decoded = msg.decode().strip()
        if decoded:
            self.pcomms = decoded.split("|")
    
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