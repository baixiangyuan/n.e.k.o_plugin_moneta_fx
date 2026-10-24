"""测试夹具：注册最小 plugin.sdk.plugin stub。

插件根目录的 ``__init__.py`` 只惰性导出 MonetaFxPlugin，裸 import 不会
拉入 SDK；但本目录的测试会直接 import 插件模块，因此需要一个可用的
``plugin.sdk.plugin``。这里安装一个最小 stub，绝不随插件发布。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PLUGIN_ROOT = HERE.parents[1]

for path in (str(PLUGIN_ROOT), str(HERE.parent)):
    if path not in sys.path:
        sys.path.insert(0, path)

from stub_plugin_sdk import install  # noqa: E402

install()
