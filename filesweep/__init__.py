"""FileSweep - tidy any folder by file type, undo anytime."""

from .core import VERSION, Rules, plan_moves, execute, undo

__all__ = ["VERSION", "Rules", "plan_moves", "execute", "undo"]
__version__ = VERSION
