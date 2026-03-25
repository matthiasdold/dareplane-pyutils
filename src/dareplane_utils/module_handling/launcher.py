from abc import ABC, abstractmethod
from subprocess import Popen
from pathlib import Path
import os
import subprocess
import time
import sys

import psutil


class Launcher(ABC):
    """Base class for launching different types of processes."""
    
    @abstractmethod
    def launch(self) -> Popen:
        """Launch the process.

        Returns
        -------
        subprocess.Popen
            Handle to the launched process.
        """
        pass
    
    @abstractmethod
    def terminate(self, process: Popen) -> None:
        """Terminate and clean up a launched process.

        Parameters
        ----------
        process : subprocess.Popen
            Process handle to terminate.
        """
        pass


class PythonLauncher(Launcher):
    def __init__(
        self,
        entry_point: str,
        cwd: Path | str,
        executable: str = sys.executable,
        args: list[str] | None = None,
        kwargs: dict | None = None,
    ):
        """Initialize a launcher for Python module subprocesses.

        Parameters
        ----------
        entry_point : str
            Python module entry point for ``python -m <entry_point>``.
        cwd : pathlib.Path or str
            Working directory used when launching the subprocess.
        executable : str, optional
            Python executable to use. Defaults to the current interpreter.
            This can be a path to a specific Python environment.
        args : list of str or None, optional
            Additional positional arguments passed to module invocation.
        kwargs : dict or None, optional
            Additional keyword arguments passed as ``--key=value``.
        """
        self.executable = executable
        self.entry_point = entry_point
        self.args = args or []
        self.kwargs = kwargs or {}
        if isinstance(cwd, str):
            cwd = Path(cwd)
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
        """Initialize a launcher for generic executables.

        Parameters
        ----------
        exe_path : pathlib.Path
            Path to the executable to launch.
        args : list or None, optional
            Arguments passed to the executable.
        cwd : pathlib.Path or None, optional
            Working directory for the subprocess. If ``None``, the current
            process working directory is used.
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
    
def close_process_and_child_processes(process: subprocess.Popen) -> None:
    """Close a process and its child processes.

    Parameters
    ----------
    process : subprocess.Popen
        Parent process to terminate.
    """
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
                try:
                    ch.wait(timeout=1)
                except psutil.TimeoutExpired:
                    ch.kill()
            except:
                pass
        i += 1

    parent_ps.terminate()
    try:
        parent_ps.wait(timeout=1)
    except psutil.TimeoutExpired:
        parent_ps.kill()
