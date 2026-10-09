# -*- coding: utf-8 -*-
"""按规则把初始表记录转换成样表的一行行数据。

关键概念：
- 一个人一条  ：把某人的全部记录汇总成一行（早期行为）
- 一个月一条  ：按「税款所属期」再拆一层，一个人一个月一行（工资表要的就是这个）
"""
from __future__ import annotations

import calendar
import datetime as _dt
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .excel_reader import cell_text, PERIOD_RE
from .rules import Rule

NAME_CANDIDATES = ("姓名", "名字", "员工姓名")
ID_CANDIDATES = ("证件号码", "身份证号", "身份证号码", "证件号", "身份证")

# 用来判定「哪个月」的字段（按顺序优先）
PERIOD_FIELDS = ("税款所属期", "所属期", "税款所属月份", "期间", "月份", "会计日期")

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


def period_to_date(text: str, day: str = "first"):
    """把「2023年12月」这类文本转成 datetime，转不了原样返回。

    day="first" → 当月 1 号；day="last" → 当月最后一天。
    """
    m = PERIOD_RE.match(cell_text(text))
    if not m:
        return text
    y, mo = int(m.group(1)), int(m.group(2))
    if 1 <= mo <= 12:
        d = calendar.monthrange(y, mo)[1] if day == "last" else 1
        return _dt.datetime(y, mo, d)
    return text


def period_sort_key(value) -> tuple:
    """把「2023年12月」变成可排序的键：能识别月份的排前面，按年月升序。"""
    t = cell_text(value)
    m = PERIOD_RE.match(t)
    if m:
        return (0, int(m.group(1)), int(m.group(2)))
    return (1, 0, 0, t)


def pick_period_field(fields: list, records: list | None = None) -> str:
    """找出「哪个月」用的字段。先按名字认，认不出来就看哪一列的值长得像「2023年12月」。"""
    for c in PERIOD_FIELDS:
        if c in fields:
            return c
    if records:
        best, best_hit = "", 0
        for f in fields:
            hit = sum(1 for r in records if PERIOD_RE.match(cell_text(r.get(f))))
            if hit > best_hit:
                best, best_hit = f, hit
        return best
    return ""


def split_by_period(records: list, period_field: str) -> list:
    """把一个人的记录按月份拆开，返回 [(月份键, [该月记录...]), ...]，按月份升序。"""
    if not period_field:
        return [(period_sort_key(""), list(records))]
    buckets: list = []
    index: dict = {}
    for rec in records:
        k = period_sort_key(rec.get(period_field))
        if k not in index:
            index[k] = len(buckets)
            buckets.append((k, []))
        buckets[index[k]][1].append(rec)
    buckets.sort(key=lambda kv: kv[0])
    return buckets


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
    """重名处理：同名的人自动改成 张1三 / 张2三。

    注意：这是按「人」去重，不是按「行」。同一个人按月拆成多行时，
    他的每一行都必须是同一个名字，不能给每个月都编一个号。
    """
    if not name_key:
        return rows
    labels, _ = rename_person_labels([cell_text(r.get(name_key)) for r in rows], position)
    for r, lab in zip(rows, labels):
        r[name_key] = lab
    return rows


def rename_person_labels(names: list, position: str = "after_first") -> tuple[list, int]:
    """给一批「人」的姓名做重名编号，返回 (编号后的名单, 被改过的人数)。"""
    counter = Counter(n for n in names if n)
    duplicated = {n for n, c in counter.items() if c > 1}
    if not duplicated:
        return list(names), 0
    seen: dict = defaultdict(int)
    out: list = []
    renamed = 0
    for n in names:
        if n in duplicated:
            seen[n] += 1
            new = _insert_index(n, seen[n], position)
            if new != n:
                renamed += 1
            out.append(new)
        else:
            out.append(n)
    return out, renamed


def convert(
    source,
    sample,
    rules: list,
    rename_enabled: bool = True,
    rename_position: str = "after_first",
    period_to_date_enabled: bool = True,
    monthly: bool = True,
    period_field: str = "",
    period_day: str = "first",
) -> tuple[list, dict]:
    """把初始表转换成样表行数据。

    monthly=True  —— **一个人一个月一行**（工资表的正常形态）：
        先按人分组，再按「税款所属期」拆开，每个月算一行，
        会计日期就是这个月，金额是这个月发生的数（奖金、工资各归各的列）。
    monthly=False —— 一个人一行：把全年所有记录加总到一行。

    返回 (行列表, 统计信息)。行列表里每个元素是 {样表字段: 值}。
    """
    groups, name_field, id_field = group_by_person(source.records, source.fields)
    active = [r for r in rules if r.enabled and r.mode != "skip" and r.target]

    # 按月分行的依据字段（界面可改，默认自动认）
    pf = period_field or pick_period_field(source.fields, source.records)
    do_monthly = bool(monthly and pf)
    stat_months: dict = {}

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

    # 重名只对「人」编号：同一个人不管拆出多少个月，用的都是同一个名字
    labels, renamed = (
        rename_person_labels([g.name for g in groups], rename_position)
        if (rename_enabled and name_field)
        else ([g.name for g in groups], 0)
    )

    rows: list = []
    seq = 0
    for gi, g in enumerate(groups):
        buckets = split_by_period(g.records, pf) if do_monthly else [(period_sort_key(""), g.records)]
        stat_months[g.name or f"#{gi + 1}"] = len(buckets)
        for _key, recs in buckets:
            seq += 1
            row: dict = {}
            for r in active:
                if r.mode == "seq":
                    row[r.target] = seq
                    continue
                val = apply_rule(r, recs)
                if (
                    period_to_date_enabled
                    and val is not None
                    and isinstance(val, str)
                    and PERIOD_RE.match(val)
                ):
                    val = period_to_date(val, period_day)
                row[r.target] = val
            if name_column and name_column in row and gi < len(labels):
                row[name_column] = labels[gi]
            rows.append(row)

    stats = {
        "初始表人数": len(groups),
        "输出行数": len(rows),
        "重命名人数": renamed,
        "姓名列": name_column,
        "证件号字段": id_field,
        "生效规则数": len(active),
        "按月分行": do_monthly,
        "月份字段": pf if do_monthly else "",
        "人均月数": (round(len(rows) / len(groups), 1) if groups else 0),
    }
    return rows, stats
