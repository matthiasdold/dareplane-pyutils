from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dareplane_utils")
except PackageNotFoundError:  # not installed, e.g. running from a source tree
    __version__ = "unknown"
