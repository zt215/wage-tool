# -*- coding: utf-8 -*-
"""按规则把初始表记录转换成样表的一行行数据。"""
from __future__ import annotations

import datetime as _dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .excel_reader import cell_text, PERIOD_RE
from .rules import Rule

NAME_CANDIDATES = ("姓名", "名字", "员工姓名")
ID_CANDIDATES = ("证件号码", "身份证号", "身份证号码", "证件号", "身份证")

# 数字插入位置
INSERT_POSITIONS = {
    "after_first": "第一个字之后（张三 -> 张1三）",
    "middle": "名字正中间",
    "before_last": "最后一个字之前",
}


def to_number(v) -> float:
    """把单元格值转成数字，转不动当 0。"""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("，", "").replace(" ", "").strip()
    if s in ("", "-", "--", "—", "/", "无"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def period_to_date(text: str):
    """把「2023年12月」这类文本转成 datetime，转不了原样返回。"""
    m = PERIOD_RE.match(cell_text(text))
    if not m:
        return text
    y, mo = int(m.group(1)), int(m.group(2))
    if 1 <= mo <= 12:
        return _dt.datetime(y, mo, 1)
    return text


def pick_name_field(fields: list) -> str:
    for c in NAME_CANDIDATES:
        if c in fields:
            return c
    return ""


def pick_id_field(fields: list) -> str:
    for c in ID_CANDIDATES:
        if c in fields:
            return c
    return ""


@dataclass
class PersonGroup:
    name: str = ""
    id_no: str = ""
    records: list = field(default_factory=list)


def group_by_person(records: list, fields: list) -> tuple[list, str, str]:
    """按「姓名 + 证件号码」把记录分组（同名的两个人不会合并）。"""
    name_field = pick_name_field(fields)
    id_field = pick_id_field(fields)

    groups: list[PersonGroup] = []
    index: dict = {}
    for rec in records:
        nm = cell_text(rec.get(name_field)) if name_field else ""
        idn = cell_text(rec.get(id_field)) if id_field else ""
        key = (nm, idn)
        if key not in index:
            index[key] = len(groups)
            groups.append(PersonGroup(name=nm, id_no=idn, records=[]))
        groups[index[key]].records.append(rec)
    return groups, name_field, id_field


def apply_rule(rule: Rule, records: list) -> object:
    """按一条规则，算出某个人的取值。"""
    if not rule.enabled or rule.mode == "skip":
        return None
    if rule.mode == "const":
        return rule.const_value

    selected = records
    if rule.filter_field and rule.filter_value:
        selected = [
            r for r in records
            if cell_text(r.get(rule.filter_field)) == rule.filter_value
        ]

    if rule.mode == "sum":
        total = 0.0
        for r in selected:
            for f in rule.sources:
                total += to_number(r.get(f))
        return round(total, 2)

    if rule.mode == "count":
        return len(selected)

    field_name = rule.sources[0] if rule.sources else ""
    vals = [cell_text(r.get(field_name)) for r in selected]
    vals = [v for v in vals if v != ""]
    if not vals:
        return None
    return vals[0] if rule.mode == "first" else vals[-1]


def _insert_index(name: str, num: int, position: str) -> str:
    """把序号插进名字里（默认第一个字之后，符合「区别数字必须在名字中间」）。"""
    s = str(num)
    chars = list(name)
    if len(chars) <= 1:
        return name + s
    if position == "after_first":
        i = 1
    elif position == "middle":
        i = max(1, (len(chars) + 1) // 2)
    elif position == "before_last":
        i = len(chars) - 1
    else:
        i = 1
    return "".join(chars[:i]) + s + "".join(chars[i:])


def rename_duplicates(rows: list, name_key: str, position: str = "after_first") -> list:
    """重名处理：同名的人自动改成 张1三 / 张2三。"""
    if not name_key:
        return rows
    counter = Counter(cell_text(r.get(name_key)) for r in rows)
    duplicated = {n for n, c in counter.items() if c > 1 and n}
    if not duplicated:
        return rows
    seen: dict = defaultdict(int)
    for r in rows:
        n = cell_text(r.get(name_key))
        if n in duplicated:
            seen[n] += 1
            r[name_key] = _insert_index(n, seen[n], position)
    return rows


def convert(
    source,
    sample,
    rules: list,
    rename_enabled: bool = True,
    rename_position: str = "after_first",
    period_to_date_enabled: bool = True,
) -> tuple[list, dict]:
    """把初始表转换成样表行数据（一人一行）。

    返回 (行列表, 统计信息)。行列表里每个元素是 {样表字段: 值}。
    """
    groups, name_field, id_field = group_by_person(source.records, source.fields)
    active = [r for r in rules if r.enabled and r.mode != "skip" and r.target]

    # 哪一列用来放姓名（重名时只改这一列）
    name_column = ""
    for r in active:
        if name_field and name_field in (r.sources or []) and r.mode in ("first", "last"):
            name_column = r.target
            break
    if not name_column and name_field:
        for r in active:
            if r.target == "姓名":
                name_column = r.target
                break
    if not name_column and "姓名" in sample.columns:
        name_column = "姓名"

    rows: list = []
    for idx, g in enumerate(groups, start=1):
        row: dict = {}
        for r in active:
            if r.mode == "seq":
                row[r.target] = idx
                continue
            val = apply_rule(r, g.records)
            if (
                period_to_date_enabled
                and val is not None
                and isinstance(val, str)
                and PERIOD_RE.match(val)
            ):
                val = period_to_date(val)
            row[r.target] = val
        rows.append(row)

    renamed = 0
    if rename_enabled:
        before = [cell_text(r.get(name_column)) for r in rows] if name_column else []
        rows = rename_duplicates(rows, name_column, rename_position)
        after = [cell_text(r.get(name_column)) for r in rows] if name_column else []
        renamed = sum(1 for a, b in zip(before, after) if a != b)

    stats = {
        "初始表人数": len(groups),
        "输出行数": len(rows),
        "重命名人数": renamed,
        "姓名列": name_column,
        "证件号字段": id_field,
        "生效规则数": len(active),
    }
    return rows, stats
