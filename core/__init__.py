# -*- coding: utf-8 -*-
"""员工工资申报转换工具 —— 核心逻辑包。"""
from .version import __version__, APP_NAME, is_newer, parse_version
from .excel_reader import SourceTable, SampleSpec, parse_source, parse_sample
from .rules import Rule, MODE_LABELS, auto_detect
from .converter import convert
from .exporter import CellFormat, export
from .settings import Settings

__all__ = [
    "SourceTable",
    "SampleSpec",
    "parse_source",
    "parse_sample",
    "Rule",
    "MODE_LABELS",
    "auto_detect",
    "convert",
    "CellFormat",
    "export",
    "Settings",
    "__version__",
    "APP_NAME",
    "is_newer",
    "parse_version",
]
