# -*- coding: utf-8 -*-
"""单条转换规则的编辑对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from core.converter import (
    apply_rule,
    group_by_person,
    period_to_date,
    pick_period_field,
    split_by_period,
)
from core.rules import MODE_KEYS, MODE_LABELS, Rule, detect_filter_field

NO_FILTER = "（不筛选）"


class RuleDialog(QDialog):
    def __init__(self, source, sample_columns, rule: Rule, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"「{rule.target or '新字段'}」这个格子，数据从哪儿来？")
        self.resize(620, 640)
        self.source = source
        self.sample_columns = list(sample_columns)
        self.result_rule: Rule | None = None
        self._values_cache: dict | None = None

        layout = QVBoxLayout(self)

        head = QLabel(
            "三个问题，从上往下答一遍就行：\n"
            "① 是这个格子吗？　② 这些数怎么来的？　③ 从初始表哪一列拿？"
        )
        head.setWordWrap(True)
        head.setStyleSheet("color:#5a6570;background:#f2f6fa;border:1px solid #dde6ef;"
                           "border-radius:6px;padding:8px;")
        layout.addWidget(head)

        # ---------- ① 样表字段 ----------
        form = QFormLayout()
        self.cmb_target = QComboBox()
        self.cmb_target.setEditable(True)
        self.cmb_target.addItems(self.sample_columns)
        if rule.target:
            self.cmb_target.setCurrentText(rule.target)
        form.addRow("① 填到样表的哪一列：", self.cmb_target)

        self.cmb_mode = QComboBox()
        for k in MODE_KEYS:
            self.cmb_mode.addItem(MODE_LABELS[k], k)
        if rule.mode in MODE_KEYS:
            self.cmb_mode.setCurrentIndex(MODE_KEYS.index(rule.mode))
        form.addRow("② 这些数怎么来的：", self.cmb_mode)
        layout.addLayout(form)

        # ---------- ③ 初始表字段（可多选） ----------
        self.box_src = QGroupBox("③ 从初始表哪一列拿（勾一个就是直接对应；勾多个就是相加）")
        src_layout = QVBoxLayout(self.box_src)
        pick_row = QHBoxLayout()
        pick_row.addWidget(QLabel("只拿一列就点它 →"))
        self.cmb_single = QComboBox()
        self.cmb_single.addItem("（从下面勾选）")
        self.cmb_single.addItems(source.fields)
        self.cmb_single.currentTextChanged.connect(self._on_single_picked)
        pick_row.addWidget(self.cmb_single, 1)
        src_layout.addLayout(pick_row)

        self.list_src = QListWidget()
        self.list_src.setMinimumHeight(190)
        for f in source.fields:
            it = QListWidgetItem(f)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if f in (rule.sources or []) else Qt.Unchecked)
            self.list_src.addItem(it)
        src_layout.addWidget(self.list_src)

        row = QHBoxLayout()
        row.addStretch(1)
        for text, picker in (
            ("全选", lambda: self._set_all(Qt.Checked)),
            ("全不选", lambda: self._set_all(Qt.Unchecked)),
        ):
            from PySide6.QtWidgets import QPushButton

            b = QPushButton(text)
            b.clicked.connect(picker)
            row.addWidget(b)
        src_layout.addLayout(row)
        layout.addWidget(self.box_src)

        # ---------- 只算某一类（折叠，默认收起） ----------
        self.chk_filter = QCheckBox("只算某一类数据（例如只算「正常工资薪金」，一般不用改）")
        self.chk_filter.toggled.connect(self._on_filter_toggled)
        layout.addWidget(self.chk_filter)

        self.box_filter = QGroupBox("挑数据条件")
        fl = QFormLayout(self.box_filter)
        self.cmb_ff = QComboBox()
        self.cmb_ff.addItem(NO_FILTER)
        self.cmb_ff.addItems(source.fields)
        if rule.filter_field:
            self.cmb_ff.setCurrentText(rule.filter_field)
        fl.addRow("看哪一列：", self.cmb_ff)

        self.cmb_fv = QComboBox()
        self.cmb_fv.setEditable(True)
        if rule.filter_value:
            self.cmb_fv.setCurrentText(rule.filter_value)
        fl.addRow("这一列等于：", self.cmb_fv)
        layout.addWidget(self.box_filter)

        # ---------- 固定值 ----------
        self.box_const = QGroupBox("固定值")
        cl = QFormLayout(self.box_const)
        self.ed_const = QLineEdit(rule.const_value)
        cl.addRow("每一行都填：", self.ed_const)
        layout.addWidget(self.box_const)

        # ---------- 预览 ----------
        self.lbl_preview = QLabel()
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet("color:#0a6b3d;background:#eefaf2;border:1px solid #bfe6cf;padding:8px;border-radius:6px;")
        layout.addWidget(self.lbl_preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("就按这个来")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # ---------- 信号 ----------
        self.cmb_mode.currentIndexChanged.connect(self._on_mode_changed)
        self.cmb_ff.currentTextChanged.connect(self._on_filter_field_changed)
        self.list_src.itemChanged.connect(self._refresh_preview)
        self.cmb_fv.currentTextChanged.connect(self._refresh_preview)
        self.ed_const.textChanged.connect(self._refresh_preview)

        # 打开时先把「只算某一类」按已有规则摆好
        self.chk_filter.setChecked(bool(rule.filter_field and rule.filter_value))
        self._on_mode_changed()
        self._on_filter_field_changed(self.cmb_ff.currentText())

    # ------------------------------------------------------------------
    def showEvent(self, event):
        """打开时滚到正在用的那一列，省得在一长串字段里翻。"""
        super().showEvent(event)
        for i in range(self.list_src.count()):
            if self.list_src.item(i).checkState() == Qt.Checked:
                self.list_src.scrollToItem(
                    self.list_src.item(i), QListWidget.PositionAtCenter)
                break

    def _set_all(self, state):
        for i in range(self.list_src.count()):
            self.list_src.item(i).setCheckState(state)

    def checked_sources(self) -> list:
        return [
            self.list_src.item(i).text()
            for i in range(self.list_src.count())
            if self.list_src.item(i).checkState() == Qt.Checked
        ]

    def _check_only(self, field: str):
        """只勾选某个字段，其余取消。"""
        self.list_src.blockSignals(True)
        for i in range(self.list_src.count()):
            it = self.list_src.item(i)
            it.setCheckState(Qt.Checked if it.text() == field else Qt.Unchecked)
        self.list_src.blockSignals(False)
        self._refresh_preview()

    def _on_single_picked(self, text):
        """「只拿一列」下拉：选了就直接勾上那一列，省得在长列表里翻。"""
        if not text or text.startswith("（"):
            return
        self._check_only(text)

    def _on_mode_changed(self):
        mode = self.cmb_mode.currentData()
        need_src = mode in ("sum", "first", "last")
        self.box_src.setEnabled(need_src)
        self.box_src.setVisible(need_src)          # 「不输出」时就别摆一堆用不上的东西
        self.chk_filter.setEnabled(need_src)
        self.chk_filter.setVisible(need_src)
        self.box_filter.setVisible(need_src and self.chk_filter.isChecked())
        self.box_const.setEnabled(mode == "const")
        self.box_const.setVisible(mode == "const")
        self._refresh_preview()

    def _on_filter_toggled(self, on):
        mode = self.cmb_mode.currentData()
        self.box_filter.setVisible(bool(on) and mode in ("sum", "first", "last"))
        self._refresh_preview()

    def _on_filter_field_changed(self, text):
        field = "" if text == NO_FILTER else text
        self.cmb_fv.setEnabled(bool(field))
        if field:
            if self._values_cache is None:
                self._values_cache = self.source.field_values
            vals = self._values_cache.get(field, [])
            cur = self.cmb_fv.currentText()
            self.cmb_fv.clear()
            self.cmb_fv.addItems(vals)
            if cur:
                self.cmb_fv.setCurrentText(cur)
            # 若是「所得项目」这类分类型字段，给出候选提示
            if not cur and field == detect_filter_field(self.source.fields) and vals:
                pass
        self._refresh_preview()

    def current_rule(self) -> Rule:
        mode = self.cmb_mode.currentData()
        ff = "" if self.cmb_ff.currentText() == NO_FILTER else self.cmb_ff.currentText()
        if not self.chk_filter.isChecked():
            ff = ""          # 没勾「只算某一类」就当没条件
        r = Rule(
            target=self.cmb_target.currentText().strip(),
            mode=mode,
            sources=self.checked_sources() if mode in ("sum", "first", "last") else [],
            filter_field=ff if mode in ("sum", "first", "last") else "",
            filter_value=self.cmb_fv.currentText().strip() if mode in ("sum", "first", "last") else "",
            const_value=self.ed_const.text(),
            enabled=True,
            confirmed=True,
        )
        if mode in ("count", "seq"):
            r.filter_field, r.filter_value = ff, self.cmb_fv.currentText().strip()
        return r

    def _fmt_val(self, v) -> str:
        from core.excel_reader import PERIOD_RE, cell_text

        if v is None or v == "":
            return "（空）"
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        if isinstance(v, str) and PERIOD_RE.match(cell_text(v)):
            d = period_to_date(v)
            if hasattr(d, "strftime"):
                return d.strftime("%Y-%m-%d")
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        if isinstance(v, (int, float)):
            return f"{v:,.2f}"
        return str(v)

    def _refresh_preview(self):
        rule = self.current_rule()
        if not rule.target:
            self.lbl_preview.setText("先回答第 ① 个问题：这个数要填到样表的哪一列。")
            return
        if rule.mode in ("sum", "first", "last") and not rule.sources:
            self.lbl_preview.setText("再回答第 ③ 个问题：从初始表哪一列拿（在下面列表里勾一个）。")
            return
        groups, _, _ = group_by_person(self.source.records, self.source.fields)
        if not groups:
            self.lbl_preview.setText("初始表里没有读到数据。")
            return

        from core.excel_reader import cell_text

        pf = pick_period_field(self.source.fields, self.source.records)
        lines = []
        for g in groups[:2]:
            buckets = split_by_period(g.records, pf) if pf else [(None, g.records)]
            for _key, recs in buckets[:3]:
                month = f"{cell_text(recs[0].get(pf))}　" if pf else ""
                lines.append(f"{g.name}　{month}→ {self._fmt_val(apply_rule(rule, recs))}")
        head = "这样填出来长这样："
        if pf:
            head += "（按人按月，这里挑前 2 个人、每人前 3 个月）"
        else:
            head += "（前 2 个人的样子）"
        self.lbl_preview.setText(head + "\n" + "\n".join(lines))

    def accept(self):
        rule = self.current_rule()
        if not rule.target:
            self.lbl_preview.setText("先回答第 ① 个问题：这个数要填到样表的哪一列。")
            return
        if rule.mode in ("sum", "first", "last") and not rule.sources:
            self.lbl_preview.setText("再回答第 ③ 个问题：从初始表哪一列拿（在下面列表里勾一个）。")
            return
        self.result_rule = rule
        super().accept()
