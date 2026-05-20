"""docpact — docstring contract validator for Python.

See docs/spec/docpact-spec.md for the full specification.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("docpact")
except PackageNotFoundError:
    __version__ = "unknown"
