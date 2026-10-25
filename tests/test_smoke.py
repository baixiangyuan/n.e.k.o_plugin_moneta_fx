"""冒烟测试：插件清单、入口注册与 Hosted TSX 面板文件。"""

from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (PLUGIN_ROOT / relative).read_text(encoding="utf-8")


def test_plugin_toml_declares_identity():
    text = read("plugin.toml")
    assert 'id = "moneta_fx"' in text
    assert 'name = "MONETA FX · 外汇模拟交易室"' in text
    assert 'entry = "plugin.plugins.moneta_fx.plugin:MonetaFxPlugin"' in text
    assert 'version = "1.0.0"' in text


def test_plugin_toml_declares_ui_and_i18n():
    text = read("plugin.toml")
    assert "[plugin.ui]" in text
    assert 'entry = "ui/panel.tsx"' in text
    assert 'context = "terminal"' in text
    assert "[plugin.i18n]" in text
    assert 'default_locale = "zh-CN"' in text
    assert "[plugin.store]" in text


def test_entry_module_matches_manifest():
    text = read("__init__.py")
    assert "MonetaFxPlugin" in text


def test_required_files_exist():
    for relative in (
        "plugin.toml",
        "__init__.py",
        "config.example.toml",
        "config.schema.json",
        "pyproject.toml",
        "ruff.toml",
        "README.md",
        "LICENSE",
        "ui/panel.tsx",
        "docs/quickstart.md",
        "i18n/zh-CN.json",
        "i18n/en.json",
        ".github/workflows/verify.yml",
        ".github/workflows/release.yml",
    ):
        assert (PLUGIN_ROOT / relative).is_file(), f"缺少 {relative}"


def test_workflows_target_this_plugin_id():
    for workflow in ("verify.yml", "release.yml"):
        text = read(f".github/workflows/{workflow}")
        assert "plugin-id: moneta_fx" in text


def test_i18n_files_are_valid_json_and_share_keys():
    import json

    zh = json.loads(read("i18n/zh-CN.json"))
    en = json.loads(read("i18n/en.json"))
    assert zh and en
    missing = set(zh) - set(en)
    assert not missing, f"en.json 缺少键: {sorted(missing)[:5]}"


def test_panel_exports_a_default_component():
    text = read("ui/panel.tsx")
    assert "export default function" in text


def test_panel_imports_only_supported_modules():
    text = read("ui/panel.tsx")
    for match in re.finditer(r'^import\s+(?:type\s+)?.*?from\s+"([^"]+)"', text, re.MULTILINE):
        specifier = match.group(1)
        assert specifier.startswith(".") or specifier == "@neko/plugin-ui", f"不支持的导入: {specifier}"


def test_panel_uses_no_dynamic_import():
    assert "import(" not in read("ui/panel.tsx")


def test_config_schema_is_valid_json():
    import json

    schema = json.loads(read("config.schema.json"))
    assert schema["type"] == "object"
    assert "moneta" in schema["properties"]


def test_config_schema_declares_every_moneta_key():
    """[moneta] 里的每个键都必须在 config.schema.json 里声明。

    宿主用 JSON Schema 校验配置，schema 未声明的键会让插件在列表里
    显示"config could not be parsed or validated"。
    """

    import json
    import tomllib

    manifest = tomllib.loads(read("plugin.toml"))
    example = tomllib.loads(read("config.example.toml"))
    schema = json.loads(read("config.schema.json"))

    declared = set(schema["properties"]["moneta"]["properties"])
    for source, config in (("plugin.toml", manifest), ("config.example.toml", example)):
        actual = set(config.get("moneta", {}))
        missing = actual - declared
        assert not missing, f"{source} 的 [moneta] 有 schema 未声明的键: {sorted(missing)}"


def test_sdk_range_contains_the_host_version():
    """[plugin.sdk] 的 supported 必须覆盖宿主的 SDK_VERSION。

    宿主的 SDK_VERSION 目前是 0.1.0（plugin/sdk/shared/constants.py）。
    文档里的 "SDK v2" 指 API 代次而不是版本号，写成 >=2.0.0 会让
    _check_sdk_compatibility 直接判不兼容，插件根本加载不了。
    """

    import tomllib

    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    HOST_SDK_VERSION = "0.1.0"

    sdk = tomllib.loads(read("plugin.toml"))["plugin"]["sdk"]
    for key in ("recommended", "supported"):
        spec = sdk.get(key)
        assert spec, f"plugin.sdk.{key} 未声明"
        assert Version(HOST_SDK_VERSION) in SpecifierSet(spec), (
            f"plugin.sdk.{key} = {spec!r} 不包含宿主 SDK 版本 {HOST_SDK_VERSION}"
        )
