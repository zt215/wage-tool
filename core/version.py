# -*- coding: utf-8 -*-
"""版本号（发布新版本时只改这里）。"""
from __future__ import annotations

import re

__version__ = "1.2.2"
APP_NAME = "员工工资申报转换工具"
# 程序文件名统一用「名字_v版本号.exe」
EXE_STEM = "员工工资申报转换工具"


def exe_filename(version: str | None = None) -> str:
    """带版本号的程序文件名，如 员工工资申报转换工具_v1.1.0.exe。"""
    return f"{EXE_STEM}_v{version or __version__}.exe"


def exe_glob_pattern() -> str:
    """匹配所有版本的 exe（给 bat / 脚本找文件用）。"""
    return f"{EXE_STEM}*.exe"


def parse_version(v) -> tuple:
    """把 '1.2.3' / 'v1.2.3' / '员工工资申报转换工具_v1.2.3.exe' 转成可比较的元组。"""
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(x) for x in nums) if nums else (0,)


def is_newer(remote, local) -> bool:
    """远端版本是否比本地新。"""
    return parse_version(remote) > parse_version(local)
