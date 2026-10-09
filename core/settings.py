# -*- coding: utf-8 -*-
"""用户配置的持久化：记住上次用过的勾选项、字体、更新地址等。

**配置只放 %APPDATA%\\员工工资申报转换工具\\settings.json**，
不会在程序旁边生成任何文件 —— 程序放在哪个文件夹，那里就只应该有程序本身。
（早期版本会在 exe 旁边写 settings.json，启动时会自动迁移过来并把旧的删掉。）
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any


def app_dir() -> str:
    """程序所在目录（打包后是 exe 目录，源码运行时是项目根目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _appdata_dir() -> str:
    """配置目录：%APPDATA%\\员工工资申报转换工具\\"""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "员工工资申报转换工具")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def default_settings_path() -> str:
    """配置文件的正式位置（永远在 %APPDATA% 下）。"""
    return os.path.join(_appdata_dir(), "settings.json")


def legacy_settings_path() -> str:
    """老版本会在 exe 旁边写 settings.json —— 只用来迁移。"""
    return os.path.join(app_dir(), "settings.json")


def _migrate_legacy(new_path: str):
    """把 exe 旁边的老配置搬到 %APPDATA%，顺手把外面那个删掉。"""
    old = legacy_settings_path()
    try:
        if os.path.abspath(old) == os.path.abspath(new_path):
            return
        if not os.path.exists(old):
            return
        if not os.path.exists(new_path):
            shutil.copy2(old, new_path)          # 先把设置搬过去
            with open(new_path, "r", encoding="utf-8") as f:
                json.load(f)                     # 确认能读，再删旧的
        os.remove(old)                           # 清掉外面那个
    except Exception:
        pass                                     # 迁移失败不影响启动


DEFAULTS: dict[str, Any] = {
    # —— 输出选项（原来每次都恢复默认的那几项）——
    "out.rename_enabled": True,
    "out.rename_position": "after_first",
    "out.period_to_date": True,
    "out.clear_example_row": True,
    # —— 输出字体/颜色 ——
    "fmt.enabled": False,          # 默认不应用，完全跟随样表
    "fmt.family": "微软雅黑",
    "fmt.size": 11,
    "fmt.color": "#000000",
    "fmt.bold": False,
    "fmt.align": "",               # 空 = 不改对齐
    "fmt.apply_header": False,     # 是否连表头行一起改
    # —— 更新 ——
    # 可以写多行，按顺序依次尝试（现在只用 GitHub，以后想加备用地址就换行写）
    "update.url": "https://github.com/zt215/wage-tool",
    "update.check_on_start": True,
    "update.last_check": "",
    "update.proxy_mode": "",       # direct / system，连上后自动记住
    # —— 上次用的文件 ——
    "last.source": "",
    "last.sample": "",
    # —— 窗口 ——
    "ui.geometry": "",
}


class Settings:
    """极简配置读写。改完调用 save() 落盘。"""

    def __init__(self, path: str | None = None):
        self.path = path or default_settings_path()
        if path is None:
            _migrate_legacy(self.path)
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except FileNotFoundError:
            pass
        except Exception:
            # 配置坏了不该影响程序启动，直接用默认值
            pass

    def save(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        if key in self.data:
            return self.data[key]
        if default is not None:
            return default
        return DEFAULTS.get(key)

    def get_bool(self, key: str) -> bool:
        v = self.get(key)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    def get_int(self, key: str) -> int:
        try:
            return int(float(self.get(key)))
        except (TypeError, ValueError):
            return int(DEFAULTS.get(key, 0) or 0)

    def get_str(self, key: str) -> str:
        v = self.get(key)
        return "" if v is None else str(v)

    def set(self, key: str, value: Any):
        self.data[key] = value

    def reset(self):
        """恢复默认值（保留更新地址，免得又要重填服务器）。"""
        url = self.data.get("update.url")
        self.data = dict(DEFAULTS)
        if url:
            self.data["update.url"] = url
