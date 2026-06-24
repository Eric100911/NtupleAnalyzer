from __future__ import annotations

import importlib
import sys
import warnings
from types import ModuleType


def shim(module_name: str, old_name: str) -> ModuleType:
    """Forward an old root-level script/module path to its new package path."""
    module = importlib.import_module(module_name)
    warnings.warn(
        f"{old_name} moved to {module_name.replace('.', '/')}.py",
        DeprecationWarning,
        stacklevel=2,
    )

    caller_globals = sys._getframe(1).f_globals
    public_names = getattr(module, "__all__", None)
    if public_names is None:
        public_names = [name for name in dir(module) if not name.startswith("_")]
    for name in public_names:
        caller_globals[name] = getattr(module, name)

    if caller_globals.get("__name__") == "__main__" and hasattr(module, "main"):
        module.main()
    return module
