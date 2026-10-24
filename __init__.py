"""MONETA FX — fictional forex paper-trading room.

N.E.K.O. 插件的加载入口。``plugin.toml`` 的 ``[plugin].entry`` 指向
``plugin.plugins.moneta_fx:MonetaFxPlugin``，宿主导入这个模块后取
``MonetaFxPlugin``。

``MonetaFxPlugin`` 通过 ``__getattr__`` 惰性导入：裸 ``import moneta_fx``
不会拉入 N.E.K.O. SDK，因此测试和云端服务端可以直接复用同级的
``market`` / ``engine`` / ``store`` / ``auth`` / ``world`` 模块。
"""

from typing import Any

__all__ = ["MonetaFxPlugin"]


def __getattr__(name: str) -> Any:
    if name == "MonetaFxPlugin":
        from .plugin import MonetaFxPlugin

        return MonetaFxPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
