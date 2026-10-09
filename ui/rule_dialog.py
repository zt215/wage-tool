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

from core.converter import apply_rule, group_by_person
from core.rules import MODE_KEYS, MODE_LABELS, Rule, detect_filter_field

NO_FILTER = "（不筛选）"


class RuleDialog(QDialog):
    def __init__(self, source, sample_columns, rule: Rule, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑转换规则")
        self.resize(560, 620)
        self.source = source
        self.sample_columns = list(sample_columns)
        self.result_rule: Rule | None = None
        self._values_cache: dict | None = None

        layout = QVBoxLayout(self)

        # ---------- 基本设置 ----------
        form = QFormLayout()
        self.cmb_target = QComboBox()
        self.cmb_target.setEditable(True)
        self.cmb_target.addItems(self.sample_columns)
        if rule.target:
            self.cmb_target.setCurrentText(rule.target)
        form.addRow("样表字段：", self.cmb_target)

        self.cmb_mode = QComboBox()
        for k in MODE_KEYS:
            self.cmb_mode.addItem(MODE_LABELS[k], k)
        if rule.mode in MODE_KEYS:
            self.cmb_mode.setCurrentIndex(MODE_KEYS.index(rule.mode))
        form.addRow("规则类型：", self.cmb_mode)
        layout.addLayout(form)

        # ---------- 初始表字段（可多选） ----------
        self.box_src = QGroupBox("初始表字段（可勾选多个，求和；单选就是直接对应）")
        src_layout = QVBoxLayout(self.box_src)
        self.list_src = QListWidget()
        self.list_src.setMinimumHeight(200)
        for f in source.fields:
            it = QListWidgetItem(f)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if f in (rule.sources or []) else Qt.Unchecked)
            self.list_src.addItem(it)
        src_layout.addWidget(self.list_src)

        row = QHBoxLayout()
        row.addWidget(QLabel("快捷："))
        for text, picker in (
            ("全选", lambda: self._set_all(Qt.Checked)),
            ("全不选", lambda: self._set_all(Qt.Unchecked)),
        ):
            from PySide6.QtWidgets import QPushButton

            b = QPushButton(text)
            b.clicked.connect(picker)
            row.addWidget(b)
        row.addStretch(1)
        src_layout.addLayout(row)
        layout.addWidget(self.box_src)

        # ---------- 筛选 ----------
        self.box_filter = QGroupBox("筛选条件（可选：只汇总满足条件的数据行）")
        fl = QFormLayout(self.box_filter)
        self.cmb_ff = QComboBox()
        self.cmb_ff.addItem(NO_FILTER)
        self.cmb_ff.addItems(source.fields)
        if rule.filter_field:
            self.cmb_ff.setCurrentText(rule.filter_field)
        fl.addRow("筛选字段：", self.cmb_ff)

        self.cmb_fv = QComboBox()
        self.cmb_fv.setEditable(True)
        if rule.filter_value:
            self.cmb_fv.setCurrentText(rule.filter_value)
        fl.addRow("筛选值：", self.cmb_fv)
        layout.addWidget(self.box_filter)

        # ---------- 固定值 ----------
        self.box_const = QGroupBox("固定值")
        cl = QFormLayout(self.box_const)
        self.ed_const = QLineEdit(rule.const_value)
        cl.addRow("固定值：", self.ed_const)
        layout.addWidget(self.box_const)

        # ---------- 预览 ----------
        self.lbl_preview = QLabel()
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setStyleSheet("color:#0a6b3d;background:#eefaf2;border:1px solid #bfe6cf;padding:8px;border-radius:6px;")
        layout.addWidget(self.lbl_preview)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
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

        self._on_mode_changed()
        self._on_filter_field_changed(self.cmb_ff.currentText())

    # ------------------------------------------------------------------
    def _set_all(self, state):
        for i in range(self.list_src.count()):
            self.list_src.item(i).setCheckState(state)

    def checked_sources(self) -> list:
        return [
            self.list_src.item(i).text()
            for i in range(self.list_src.count())
            if self.list_src.item(i).checkState() == Qt.Checked
        ]

    def _on_mode_changed(self):
        mode = self.cmb_mode.currentData()
        need_src = mode in ("sum", "first", "last")
        self.box_src.setEnabled(need_src)
        self.box_filter.setEnabled(need_src)
        self.box_const.setEnabled(mode == "const")
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

    def _refresh_preview(self):
        rule = self.current_rule()
        if not rule.target:
            self.lbl_preview.setText("请先选择样表字段。")
            return
        if rule.mode in ("sum", "first", "last") and not rule.sources:
            self.lbl_preview.setText("请至少勾选一个初始表字段。")
            return
        groups, _, _ = group_by_person(self.source.records, self.source.fields)
        if not groups:
            self.lbl_preview.setText("初始表里没有读到数据。")
            return
        lines = []
        for g in groups[:3]:
            v = apply_rule(rule, g.records)
            disp = "（空）" if v is None or v == "" else v
            lines.append(f"{g.name} → {disp}")
        self.lbl_preview.setText("预览（前 3 人）\n" + "\n".join(lines))

    def accept(self):
        rule = self.current_rule()
        if not rule.target:
            self.lbl_preview.setText("请先选择样表字段。")
            return
        if rule.mode in ("sum", "first", "last") and not rule.sources:
            self.lbl_preview.setText("请至少勾选一个初始表字段。")
            return
        self.result_rule = rule
        super().accept()
