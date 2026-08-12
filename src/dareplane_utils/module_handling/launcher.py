import os
import subprocess
import sys
import time
import warnings
from abc import ABC, abstractmethod
from pathlib import Path
from subprocess import Popen

import psutil


class Launcher(ABC):
    """Base class for launching different types of processes."""

    @abstractmethod
    def launch(self, relaunch: bool = False, **kwargs) -> Popen:
        """Launch the process.

        Parameters
        ----------
        relaunch : bool, optional
            If ``True``, will terminate an existing process before launching a new one. Defaults to ``False``.
        **kwargs
            Additional keyword arguments passed to ``subprocess.Popen``.

        Returns
        -------
        subprocess.Popen
            Handle to the launched process.
        """

    @abstractmethod
    def terminate(self) -> None:
        """Terminate and clean up a launched process."""


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
        self.process = None
        self.executable = executable
        self.entry_point = entry_point
        self.args = args or []
        self.kwargs = kwargs or {}
        if isinstance(cwd, str):
            cwd = Path(cwd)
        self.cwd = cwd

        assert self.cwd.exists(), f"Directory {self.cwd} does not exist"

    def launch(self, relaunch: bool = False, **popen_kwargs) -> Popen:
        if self.process and not relaunch:
            warnings.warn(
                    f"Module {self.name=} is already running with pid {self.process.pid}. Returning existing process.",
                    RuntimeWarning,
                    stacklevel=2
                )
            return self.process

        if self.process and relaunch:
            self.terminate()
            self.process = None

        cmd = [
            self.executable,
            "-m",
            self.entry_point,
            *self.args,
            *[f"--{k}={v}" for k, v in self.kwargs.items()],
        ]

        popen_kwargs["cwd"] = str(self.cwd.resolve())
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        self.process = subprocess.Popen(cmd, **popen_kwargs)
        return self.process

    def terminate(self) -> None:
        if self.process:
            close_process_and_child_processes(self.process)
            self.process = None


class ExeLauncher(Launcher):
    def __init__(self, exe_path: Path | str, args: list | None = None, cwd: Path | str | None = None):
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
        if isinstance(exe_path, str):
            exe_path = Path(exe_path)
        if isinstance(cwd, str):
            cwd = Path(cwd)
        self.exe_path = exe_path
        self.args = args or []
        self.cwd = cwd
        self.process = None
        if self.cwd is None:
            self.cwd = Path.cwd()

        assert self.cwd.exists(), f"Directory {self.cwd} does not exist"
        assert self.exe_path.exists(), f"Executable {self.exe_path} does not exist"


    def launch(self, relaunch: bool = False, **popen_kwargs) -> Popen:
        if self.process and not relaunch:
            warnings.warn(
                    f"Module {self.name=} is already running with pid {self.process.pid}. Returning existing process.",
                    RuntimeWarning,
                    stacklevel=2
                )
            return self.process

        if self.process and relaunch:
            self.terminate()
            self.process = None

        popen_kwargs["cwd"] = str(self.cwd) if self.cwd else None
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        self.process = subprocess.Popen([str(self.exe_path)] + self.args, **popen_kwargs)
        return self.process

    def terminate(self) -> None:
        if self.process:
            close_process_and_child_processes(self.process)
            self.process = None


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
            except Exception:
                pass
        i += 1

    parent_ps.terminate()
    try:
        parent_ps.wait(timeout=1)
    except psutil.TimeoutExpired:
        parent_ps.kill()
