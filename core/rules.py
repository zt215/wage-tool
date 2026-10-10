# -*- coding: utf-8 -*-
"""转换规则模型 + 自动字段识别。

一条规则描述：样表的某个字段，由初始表的哪些字段、按什么方式算出来。
支持「一个初始表字段 -> 一个样表字段」以及
「多个初始表字段相加 -> 一个样表字段」，并可按某字段的取值筛选后再汇总。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .excel_reader import cell_text

# 规则类型：键 -> 界面显示名（用大白话，别用「求和/取首个」这种词）
MODE_LABELS = {
    "sum": "把金额加起来（工资、社保用这个）",
    "first": "直接照抄（姓名、日期这种文字用这个）",
    "last": "取最后一个（很少用）",
    "count": "数一数有几条（很少用）",
    "const": "每一行都固定填同一个值",
    "seq": "自动编号 1、2、3…",
    "skip": "不输出（样表这一列留空）",
}
MODE_KEYS = list(MODE_LABELS.keys())


def _quote(names) -> str:
    return "、".join(f"「{n}」" for n in names if n)


@dataclass
class Rule:
    """一条「样表字段 <- 初始表字段」的转换规则。"""

    target: str = ""                 # 样表字段名
    mode: str = "sum"                # 见 MODE_LABELS
    sources: list = field(default_factory=list)   # 初始表字段（可多个，求和）
    filter_field: str = ""           # 筛选字段（可空）
    filter_value: str = ""           # 筛选值（可空）
    const_value: str = ""            # 固定值
    enabled: bool = True
    confirmed: bool = False

    # ---------- 展示辅助 ----------
    def mode_label(self) -> str:
        return MODE_LABELS.get(self.mode, self.mode)

    def filter_label(self) -> str:
        if self.filter_field and self.filter_value:
            return f"{self.filter_field} = {self.filter_value}"
        return ""

    def source_label(self) -> str:
        if self.mode == "const":
            return self.const_value
        if self.mode == "seq":
            return "（自动编号）"
        return " + ".join(self.sources) if self.sources else ""

    def status_label(self) -> str:
        if self.mode == "skip":
            return "不输出"
        if not self.enabled:
            return "已停用"
        return "已确认" if self.confirmed else "待核对"

    def plain_label(self) -> str:
        """把这条规则写成一句大白话，界面上直接显示这句（不需要用户懂「规则类型」）。"""
        if self.mode == "skip":
            return "样表这一列留空，不填数据"
        if self.mode == "const":
            if self.const_value:
                return f"每一行都固定填「{self.const_value}」"
            return "固定填一个值（还没填）"
        if self.mode == "seq":
            return "自动编号：1、2、3…按行一直排下去"
        if self.mode == "count":
            return "数一数有几条记录，把条数填进来"

        srcs = _quote(self.sources)
        if not srcs:
            return "还没选数据来源（点右边的「修改」挑一个）"
        cond = ""
        if self.filter_field and self.filter_value:
            cond = f"只挑「{self.filter_field} = {self.filter_value}」的"
        if self.mode == "sum":
            return f"把初始表里{cond}{srcs}加起来"
        if self.mode == "first":
            return f"照抄初始表{cond}{srcs}的值"
        return f"取初始表{cond}{srcs}的最后一个值"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Rule":
        r = Rule()
        for k, v in (d or {}).items():
            if hasattr(r, k):
                setattr(r, k, v)
        if not isinstance(r.sources, list):
            r.sources = [r.sources] if r.sources else []
        return r


# --------------------------------------------------------------------------
# 自动识别
# --------------------------------------------------------------------------

# 常见工资/社保字段的推荐映射：样表字段 -> (初始表字段, 规则类型, 筛选字段, 筛选值)
PREFERRED = {
    "会计日期": ("税款所属期", "first", "", ""),
    "工号": None,
    "姓名": ("姓名", "first", "", ""),
    "应发工资": ("收入", "sum", "所得项目", "正常工资薪金"),
    "养老保险": ("基本养老保险费", "sum", "", ""),
    "医疗保险": ("基本医疗保险费", "sum", "", ""),
    "失业保险": ("失业保险费", "sum", "", ""),
    "工伤保险": ("工伤保险费", "sum", "", ""),
    "生育保险": ("生育保险费", "sum", "", ""),
    "养老": ("基本养老保险费", "sum", "", ""),
    "医疗": ("基本医疗保险费", "sum", "", ""),
    "失业": ("失业保险费", "sum", "", ""),
    "工伤": ("工伤保险费", "sum", "", ""),
    "生育": ("生育保险费", "sum", "", ""),
    "公积金": ("住房公积金", "sum", "", ""),
    "住房公积金": ("住房公积金", "sum", "", ""),
    "年金": ("企业(职业）年金", "sum", "", ""),
    "奖金": ("收入", "sum", "所得项目", "全年一次性奖金收入"),
    "全年一次性奖金": ("收入", "sum", "所得项目", "全年一次性奖金收入"),
    "股权激励": ("收入", "sum", "所得项目", "股权激励"),
    "外聘": ("收入", "sum", "所得项目", "劳务报酬"),
    "劳务报酬": ("收入", "sum", "所得项目", "其他非连续劳务报酬"),
    "其他": ("收入", "sum", "所得项目", "其他非连续劳务报酬"),
}

# 初始表可能出现的字段别名（用于模糊兜底）
FIELD_ALIASES = {
    "基本养老保险费": ["养老保险", "养老"],
    "基本医疗保险费": ["医疗保险", "医疗"],
    "失业保险费": ["失业保险", "失业"],
    "工伤保险费": ["工伤保险", "工伤"],
    "生育保险费": ["生育保险", "生育"],
    "住房公积金": ["公积金"],
    "企业(职业）年金": ["年金"],
    "收入": ["应发工资", "工资", "应发"],
    "税款所属期": ["会计日期", "所属期", "期间"],
}

MULTI_FILTER_FIELDS = ("所得项目", "项目", "类型", "所得项目类型")


def _norm(s: str) -> str:
    return "".join(ch for ch in cell_text(s) if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _score(target: str, field_name: str) -> float:
    """两个字段名的相似度，0~1。"""
    t, f = _norm(target), _norm(field_name)
    if not t or not f:
        return 0.0
    if t == f:
        return 1.0
    if t in f or f in t:
        return 0.85
    common = sum(1 for ch in set(t) if ch in f)
    return min(0.8, common / max(len(set(t)), 1))


def find_field(fields: list, name: str) -> str:
    """在初始表字段里找与 name 最接近的字段名，找不到返回空串。"""
    if not fields:
        return ""
    if name in fields:
        return name
    # 别名优先
    for canon, aliases in FIELD_ALIASES.items():
        if name in aliases or name == canon:
            if canon in fields:
                return canon
            for a in aliases:
                if a in fields:
                    return a
    best, best_score = "", 0.0
    for f in fields:
        s = _score(name, f)
        if s > best_score:
            best, best_score = f, s
    # 阈值收紧到 0.7：避免「工伤保险」被错配到「基本养老保险费」这类误判
    return best if best_score >= 0.7 else ""


def detect_filter_field(fields: list) -> str:
    """找到用于区分类别的字段名（如「所得项目」）。"""
    for cand in MULTI_FILTER_FIELDS:
        if cand in fields:
            return cand
    return ""


def auto_detect(sample_columns: list, source_fields: list) -> list[Rule]:
    """根据样表字段与初始表字段，自动生成一份建议规则（按样表列顺序）。"""
    rules: list[Rule] = []
    for col in sample_columns:
        rules.append(_detect_one(col, source_fields))
    return rules


def _detect_one(target: str, source_fields: list) -> Rule:
    rule = Rule(target=target)

    known = target in PREFERRED
    pref = PREFERRED.get(target)

    if not known:
        # 按别名表反查（如样表写「养老」，初始表写「基本养老保险费」）
        for canon, aliases in FIELD_ALIASES.items():
            if target in aliases:
                known, pref = True, (canon, "sum", "", "")
                break

    if known:
        # 这是已知的工资/社保字段：要么精确映射，要么明确留空，绝不乱猜
        if pref is None:
            rule.mode = "skip"
            return rule
        src_name, mode, ff, fv = pref
        src = find_field(source_fields, src_name)
        if not src:
            rule.mode = "skip"
            return rule
        rule.mode = mode
        rule.sources = [src]
        rule.filter_field = ff if (ff and ff in source_fields) else ""
        rule.filter_value = fv if rule.filter_field else ""
        return rule

    # 未知字段：才用模糊匹配兜底
    guess = find_field(source_fields, target)
    if guess:
        rule.mode = "sum"
        rule.sources = [guess]
        return rule

    rule.mode = "skip"
    rule.sources = []
    return rule
