from dareplane_utils.module_handling.launcher import PythonLauncher
from pathlib import Path
import time

def test_python_launcher():
    launcher = PythonLauncher(
        entry_point="tests.resources.test_server",
        cwd=Path(__file__).parent.parent,
    )
    process = launcher.launch()
    time.sleep(2)
    assert process is not None
    assert process.poll() is None  # process should be running

    # Teardown
    launcher.terminate(process)
    time.sleep(1)
    assert process.poll() is not None  # process should be terminated

    if process.poll() is None:
        process.kill()

# TODO: add tests for ExeLauncher