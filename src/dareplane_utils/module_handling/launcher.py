from abc import ABC, abstractmethod
from subprocess import Popen
from pathlib import Path
import os
import subprocess
from time import time
import sys

import psutil


class Launcher(ABC):
    """Base class for launching different types of processes"""
    
    @abstractmethod
    def launch(self) -> Popen:
        """Launch the process, return Popen"""
        pass
    
    @abstractmethod
    def terminate(self, process: Popen) -> None:
        """Clean up the process"""
        pass


class PythonLauncher(Launcher):
    def __init__(
        self,
        entry_point: str,
        cwd: Path,
        executable: str = sys.executable,
        args: list[str] | None = None,
        kwargs: dict | None = None,
    ):
        """Launch a Python module as a subprocess
        
        Args:
            entry_point: Python module entry point for `python -m <entry_point>`
            cwd: Working directory for launching the process
            executable: Python executable to use (default: current Python). Can be a path to a specific Python interpreter or environment.
            args: Additional positional arguments to pass to the module invocation
            kwargs: Additional keyword arguments to pass as --key=value
        """
        self.executable = executable
        self.entry_point = entry_point
        self.args = args or []
        self.kwargs = kwargs or {}
        self.cwd = cwd
    
    def launch(self) -> Popen:
        modpath = self.cwd

        assert modpath.exists(), f"not a valid path {modpath}"

        cmd = [
            self.executable,
            "-m",
            self.entry_point,
            *self.args,
            *[f"--{k}={v}" for k, v in self.kwargs.items()],
        ]

        popen_kwargs = {"cwd": str(modpath.resolve())}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        return subprocess.Popen(cmd, **popen_kwargs)
    
    def terminate(self, process: Popen) -> None:
        if process:
            close_process_and_child_processes(process)


class ExeLauncher(Launcher):
    def __init__(self, exe_path: Path, args: list | None = None, cwd: Path | None = None):
        """Launch a generic executable as a subprocess
        
        Args:
            exe_path: Path to the executable to launch
            args: List of arguments to pass to the executable
        """
        self.exe_path = exe_path
        self.args = args or []
        self.cwd = cwd
    
    def launch(self) -> Popen:
        popen_kwargs = {"cwd": str(self.cwd) if self.cwd else None}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        return subprocess.Popen([str(self.exe_path)] + self.args, **popen_kwargs)
    
    def terminate(self, process: Popen) -> None:
        if process:
            close_process_and_child_processes(process)
    
def close_process_and_child_processes(process: subprocess.Popen) -> int:
    """Close a process and its child processes"""
    try:
        parent_ps = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        return 0

    max_iter = 5
    i = 0

    while i <= max_iter:
        if i > 0:
            time.sleep(0.2)
        try:
            children = parent_ps.children()
        except psutil.NoSuchProcess:
            # Parent process is gone, so we are done
            return 0

        # If no children, break
        if children == []:
            break

        # Otherwise, try to terminate children
        for ch in children:
            try:
                ch.terminate()
            except:
                pass
        i += 1

    try:
        parent_ps.kill()
    except:
        pass
    return 0

