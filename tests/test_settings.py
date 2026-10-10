"""用户配置持久化测试。

重点不在「读得出来」，而在**读不出来时会怎样**：配置文件是人能手改的，
也会被断电、磁盘满、旧版本残留搞坏。这些路径必须全部回退到默认值，
而不是把异常抛给启动流程。
"""

from __future__ import annotations

import os

import pytest

from renamer import settings
from renamer.theme import Theme


def _write_raw(content: str) -> None:
    """绕过 save()，直接往配置文件里塞任意内容。"""
    os.makedirs(settings.config_dir(), exist_ok=True)
    with open(settings.settings_path(), "w", encoding="utf-8") as fh:
        fh.write(content)


# ------------------------------------------------------------------ 位置

def test_env_override_wins(monkeypatch, tmp_path):
    """测试隔离全靠这个环境变量，先把它本身钉住。"""
    target = str(tmp_path / "somewhere")
    monkeypatch.setenv(settings.ENV_OVERRIDE, target)
    assert settings.config_dir() == target
    assert settings.settings_path() == os.path.join(target, "settings.json")


def test_default_location_is_absolute_and_outside_the_repo(monkeypatch):
    monkeypatch.delenv(settings.ENV_OVERRIDE, raising=False)
    path = settings.config_dir()
    assert os.path.isabs(path)
    assert settings.APP_DIR_NAME in path


# ------------------------------------------------------------------ 读写

def test_missing_file_yields_defaults():
    assert settings.load() == {}
    assert settings.get_skin() == Theme.DEFAULT


def test_round_trip():
    settings.set_skin("midnight")
    assert settings.get_skin() == "midnight"
    assert settings.load() == {"skin": "midnight"}


def test_set_value_keeps_other_keys():
    settings.set_skin("eye")
    settings.set_value("window_width", 1200)
    assert settings.load() == {"skin": "eye", "window_width": 1200}


def test_saved_file_is_utf8_json():
    settings.set_skin("sand")
    with open(settings.settings_path(), encoding="utf-8") as fh:
        text = fh.read()
    assert text.startswith("{")
    assert text.endswith("}\n")


def test_write_leaves_no_temp_files_behind():
    """原子写入的临时文件必须被 os.replace 消费掉，不能留在配置目录里。"""
    settings.set_skin("sand")
    leftovers = [n for n in os.listdir(settings.config_dir())
                 if n.startswith(".settings-")]
    assert leftovers == []


# ------------------------------------------------------------------ 容错

@pytest.mark.parametrize("content", [
    "",
    "{ 被手改坏的 json",
    "[]",
    '"just a string"',
    '{"skin": 123}',
    '{"skin": "这个皮肤已经删掉了"}',
])
def test_broken_or_invalid_content_falls_back(content):
    _write_raw(content)
    assert settings.get_skin() == Theme.DEFAULT


def test_invalid_skin_is_not_written():
    settings.set_skin("light")
    settings.set_skin("不存在的皮肤")
    assert settings.load() == {"skin": "light"}


def test_write_failure_does_not_raise(monkeypatch, tmp_path):
    """写不进去只是「这次选择记不住」，不该让程序崩掉或弹窗。"""
    target = tmp_path / "nested" / "deep" / "settings.json"
    monkeypatch.setenv(settings.ENV_OVERRIDE, str(target.parent))

    def boom(*_args, **_kwargs):
        raise OSError("模拟磁盘写满")

    monkeypatch.setattr(os, "replace", boom)
    settings.set_skin("dark")            # 不抛异常即通过

    # 故意不用 monkeypatch.undo() 来「恢复现场」：它会把 conftest.py 里那条
    # autouse 隔离（FRA_CONFIG_DIR）也一并撤掉，于是下面读到的其实是开发机上
    # %APPDATA% 里的**真实配置**——只要本人切过一次深色皮肤，这条就会红，
    # 而在干净机器上又会「碰巧」通过。改为在隔离仍然生效时断言「什么都没写」。
    assert not target.exists()
    assert settings.get_skin() == Theme.DEFAULT


def test_non_object_top_level_does_not_crash_load():
    _write_raw('["skin", "dark"]')
    assert settings.load() == {}
