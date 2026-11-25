"""Importing a module here registers its loader.

To add a new format: create formats/<name>.py with a function decorated by
@register(...), then add one import line below.
"""

from . import epub  # noqa: F401
from . import fb2  # noqa: F401
from . import pdf  # noqa: F401
from ..core.registry import UnsupportedFormatError, file_dialog_filter, load_book

__all__ = ["load_book", "file_dialog_filter", "UnsupportedFormatError"]
