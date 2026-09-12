"""Load TodayImage's PURE modules without importing the package.

The plugin package's ``__init__.py`` declares ``Plugins(...)`` and imports GsCore, so importing
``tdi.gallery`` the normal way would drag GsCore into the test process. The modules marked PURE in
plan.md import only the standard library, so they can be loaded straight from their file and tested
with GsCore absent — which is the whole point of the pure/GsCore-facing split (research R9).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TDI_DIR = PLUGIN_ROOT / 'tdi'

# Modules that must never import gsuid_core, directly or transitively.
PURE_MODULES = (
    'gallery',
    'category_registry',
    'daily_store',
    'image_input',
    'file_cache',
    'upload_access',
    'help_text',
    'blocklist',
    'dispatch',
    'group_permissions',
    'permissions_text',
    'chat_context',
)


# Synthetic package the pure modules are loaded into. Some of them import their
# siblings relatively (dispatch -> blocklist, gallery), which only resolves inside a
# package -- but importing the real `tdi` package would execute __init__ and drag in
# GsCore, defeating the point. A namespace package rooted at tdi/ gives relative
# imports somewhere to resolve without touching the real one.
_PKG = 'todayimage_pure'


def _ensure_package() -> None:
    if _PKG in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        _PKG, TDI_DIR / '__init__.py', submodule_search_locations=[str(TDI_DIR)]
    )
    if spec is None or spec.loader is None:
        raise RuntimeError('cannot build the synthetic package spec')
    package = importlib.util.module_from_spec(spec)
    sys.modules[_PKG] = package
    spec.loader.exec_module(package)


def load_pure_module(name: str) -> ModuleType:
    """Load ``tdi/<name>.py`` without importing the real plugin package.

    Loading under ``todayimage_pure.<name>`` keeps the real ``tdi`` package -- and
    therefore GsCore -- out of ``sys.modules``, while still giving sibling relative
    imports a package to resolve against.
    """
    path = TDI_DIR / f'{name}.py'
    if not path.is_file():
        raise FileNotFoundError(f'no such module file: {path}')

    _ensure_package()
    module_name = f'{_PKG}.{name}'
    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot build a module spec for {path}')

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module
