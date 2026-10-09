# -*- coding: utf-8 -*-
"""主窗口。"""
from __future__ import annotations

import os
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFontComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import Settings, __version__, parse_sample, parse_source
from core.converter import INSERT_POSITIONS, convert
from core.exporter import CellFormat, export
from core.rules import Rule, auto_detect
from core import updater
from .rule_dialog import RuleDialog
from .update_dialog import CheckThread, UpdateDialog

EXCEL_FILTER = "Excel 文件 (*.xlsx *.xlsm *.xls);;所有文件 (*.*)"
FONT_CHOICES = ["微软雅黑", "宋体", "等线", "黑体", "楷体", "仿宋", "Calibri", "Arial"]
ALIGN_CHOICES = [("（不改对齐）", ""), ("左对齐", "left"), ("居中", "center"), ("右对齐", "right")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.setWindowTitle(f"员工工资申报转换工具  v{__version__}")
        self.resize(1220, 840)
        self.setMinimumSize(1000, 680)

        self.source = None
        self.sample = None
        self.rules: list[Rule] = []
        self.rows: list = []
        self._loading = False
        self._sample_file = ""
        self._last_columns: tuple = ()
        self._auto_advanced = False
        self._checker = None

        self._build_ui()
        self._apply_style()
        self._restore_settings()

        # 上次用哪种网络出口通的（直连 / 系统代理），先用它，省一次尝试
        updater.set_preferred_mode(self.settings.get_str("update.proxy_mode"))

        self._log(f"就绪（v{__version__}）。请先「添加初始表」，再「添加样表」。")
        self._log(f"设置文件：{self.settings.path}")

        if self.settings.get_bool("update.check_on_start"):
            QTimer.singleShot(1500, self.silent_update_check)

    # ==================================================================
    # 界面
    # ==================================================================
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # 顶部：标题 + 版本 + 检查更新
        head = QHBoxLayout()
        ttl = QLabel(f"员工工资申报转换工具　v{__version__}")
        ttl.setStyleSheet("font-size:14px; font-weight:600; color:#1f7a45;")
        head.addWidget(ttl)
        head.addStretch(1)
        self.btn_update = QPushButton("检查更新")
        self.btn_update.clicked.connect(self.open_update_dialog)
        head.addWidget(self.btn_update)
        outer.addLayout(head)

        # 分页显示：一页只放一块内容，避免挤在一个窗口里看不全
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(self.tabs, 1)

        # ================= 第 1 页：数据源 =================
        page1 = QWidget()
        page1_l = QVBoxLayout(page1)
        page1_l.setContentsMargins(10, 10, 10, 10)
        page1_l.setSpacing(10)

        top = QWidget()
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(0, 0, 0, 0)
        top_l.setSpacing(10)

        # 初始表
        g1 = QGroupBox("初始表（申报汇总表）")
        l1 = QVBoxLayout(g1)
        h1 = QHBoxLayout()
        self.btn_source = QPushButton("添加初始表")
        self.btn_source.clicked.connect(self.choose_source)
        self.lbl_source = QLabel("未选择")
        self.lbl_source.setStyleSheet("color:#8a8a8a;")
        h1.addWidget(self.btn_source)
        h1.addWidget(self.lbl_source, 1)
        l1.addLayout(h1)
        self.lbl_source_info = QLabel("—")
        self.lbl_source_info.setStyleSheet("color:#0a6b3d;")
        l1.addWidget(self.lbl_source_info)
        l1.addWidget(QLabel("识别到的字段："))
        self.list_source_fields = QListWidget()
        l1.addWidget(self.list_source_fields, 1)
        top_l.addWidget(g1, 1)

        # 样表
        g2 = QGroupBox("样表（目标格式）")
        l2 = QVBoxLayout(g2)
        h2 = QHBoxLayout()
        self.btn_sample = QPushButton("添加样表")
        self.btn_sample.clicked.connect(self.choose_sample)
        self.lbl_sample = QLabel("未选择")
        self.lbl_sample.setStyleSheet("color:#8a8a8a;")
        h2.addWidget(self.btn_sample)
        h2.addWidget(self.lbl_sample, 1)
        l2.addLayout(h2)

        self.cmb_sheet = QComboBox()
        self.cmb_sheet.currentIndexChanged.connect(self._resample)
        self.spin_header = QSpinBox()
        self.spin_header.setRange(1, 50)
        self.spin_header.setValue(1)
        self.spin_header.valueChanged.connect(self._resample)
        self.spin_start = QSpinBox()
        self.spin_start.setRange(2, 100000)
        self.spin_start.setValue(4)
        self.spin_start.valueChanged.connect(self._resample)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("工作表"))
        r2.addWidget(self.cmb_sheet, 1)
        r2.addWidget(QLabel("表头行"))
        r2.addWidget(self.spin_header)
        r2.addWidget(QLabel("数据起始行"))
        r2.addWidget(self.spin_start)
        l2.addLayout(r2)

        self.lbl_rename_rule = QLabel("重名规则：—")
        self.lbl_rename_rule.setWordWrap(True)
        self.lbl_rename_rule.setStyleSheet(
            "color:#8a4b00;background:#fff8e6;border:1px solid #f0dca8;"
            "padding:6px;border-radius:6px;"
        )
        l2.addWidget(self.lbl_rename_rule)
        l2.addWidget(QLabel("识别到的字段："))
        self.list_sample_fields = QListWidget()
        l2.addWidget(self.list_sample_fields, 1)
        top_l.addWidget(g2, 1)
        page1_l.addWidget(top, 1)
        self.tabs.addTab(page1, "① 数据源")

        # ================= 第 2 页：转换规则 =================
        page2 = QWidget()
        page2_l = QVBoxLayout(page2)
        page2_l.setContentsMargins(10, 10, 10, 10)
        page2_l.setSpacing(8)

        g3 = QGroupBox("样表每个字段 ← 初始表字段（可多选相加，也能设筛选条件）")
        l3 = QVBoxLayout(g3)
        bar = QHBoxLayout()
        self.btn_auto = QPushButton("自动识别字段")
        self.btn_auto.clicked.connect(self.do_auto_detect)
        self.btn_add = QPushButton("添加规则")
        self.btn_add.clicked.connect(self.add_rule)
        self.btn_edit = QPushButton("编辑规则")
        self.btn_edit.clicked.connect(self.edit_rule)
        self.btn_del = QPushButton("删除规则")
        self.btn_del.clicked.connect(self.del_rule)
        self.btn_up = QPushButton("上移")
        self.btn_up.clicked.connect(lambda: self.move_rule(-1))
        self.btn_down = QPushButton("下移")
        self.btn_down.clicked.connect(lambda: self.move_rule(1))
        self.btn_confirm = QPushButton("全部确认")
        self.btn_confirm.clicked.connect(self.confirm_all)
        for b in (self.btn_auto, self.btn_add, self.btn_edit, self.btn_del,
                  self.btn_up, self.btn_down, self.btn_confirm):
            bar.addWidget(b)
        bar.addStretch(1)
        self.lbl_rule_tip = QLabel("双击某一行可直接编辑规则")
        self.lbl_rule_tip.setStyleSheet("color:#8a8a8a;")
        bar.addWidget(self.lbl_rule_tip)
        l3.addLayout(bar)

        self.tbl_rules = QTableWidget(0, 6)
        self.tbl_rules.setHorizontalHeaderLabels(
            ["启用", "样表字段", "规则类型", "初始表字段（相加）", "筛选条件", "状态"]
        )
        self.tbl_rules.verticalHeader().setVisible(False)
        self.tbl_rules.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_rules.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_rules.doubleClicked.connect(lambda _i: self.edit_rule())
        self.tbl_rules.itemChanged.connect(self._on_rule_item_changed)
        hh = self.tbl_rules.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        l3.addWidget(self.tbl_rules, 1)
        page2_l.addWidget(g3, 1)
        self.tabs.addTab(page2, "② 转换规则")

        # ================= 第 3 页：输出设置 =================
        page3 = QWidget()
        page3_l = QVBoxLayout(page3)
        page3_l.setContentsMargins(10, 10, 10, 10)
        page3_l.setSpacing(10)

        g4 = QGroupBox("输出选项（这些勾选会被记住，下次打开还是上次的设置）")
        l4 = QVBoxLayout(g4)

        row1 = QHBoxLayout()
        self.chk_rename = QCheckBox("启用重名规则")
        self.chk_rename.setChecked(True)
        self.chk_rename.setToolTip("同名的人自动改成 张1三、张2三（数字放在名字中间）")
        row1.addWidget(self.chk_rename)

        self.cmb_pos = QComboBox()
        for k, v in INSERT_POSITIONS.items():
            self.cmb_pos.addItem(v, k)
        row1.addWidget(self.cmb_pos)
        row1.addStretch(1)
        l4.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_period = QCheckBox("期间文本（2023年12月）自动转成日期")
        self.chk_period.setChecked(True)
        row2.addWidget(self.chk_period)
        self.chk_clear = QCheckBox("清空样表第 2 行示例数据")
        self.chk_clear.setChecked(True)
        row2.addWidget(self.chk_clear)
        row2.addStretch(1)
        l4.addLayout(row2)
        page3_l.addWidget(g4)

        # ---------- 输出格式 ----------
        g6 = QGroupBox("输出格式（默认完全跟随样表；想改字体/颜色就勾上下面这项）")
        l6 = QVBoxLayout(g6)
        self.chk_fmt = QCheckBox("应用自定义字体 / 字号 / 颜色")
        self.chk_fmt.setToolTip("不勾：数据沿用样表里那一行的格式，什么都不动")
        l6.addWidget(self.chk_fmt)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("字体"))
        self.cmb_font = QFontComboBox()
        fmt_row.addWidget(self.cmb_font, 2)

        fmt_row.addWidget(QLabel("字号"))
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(6, 72)
        self.spin_font_size.setValue(11)
        fmt_row.addWidget(self.spin_font_size)

        self.btn_color = QPushButton("字体颜色")
        self.btn_color.setMinimumWidth(110)
        self.btn_color.clicked.connect(self.pick_color)
        fmt_row.addWidget(self.btn_color)

        self.chk_bold = QCheckBox("加粗")
        fmt_row.addWidget(self.chk_bold)

        fmt_row.addWidget(QLabel("对齐"))
        self.cmb_align = QComboBox()
        for label, val in ALIGN_CHOICES:
            self.cmb_align.addItem(label, val)
        fmt_row.addWidget(self.cmb_align)

        self.chk_fmt_header = QCheckBox("表头行一起改")
        fmt_row.addWidget(self.chk_fmt_header)
        fmt_row.addStretch(1)
        l6.addLayout(fmt_row)

        self.lbl_fmt_preview = QLabel("格式预览：应发工资  65000.00  张三")
        self.lbl_fmt_preview.setStyleSheet(
            "background:#ffffff;border:1px solid #e0e4e8;border-radius:6px;padding:10px;"
        )
        l6.addWidget(self.lbl_fmt_preview)
        page3_l.addWidget(g6)

        act = QHBoxLayout()
        act.addStretch(1)
        self.btn_preview = QPushButton("预览转换结果")
        self.btn_preview.clicked.connect(self.do_preview)
        self.btn_export = QPushButton("输出完成表")
        self.btn_export.clicked.connect(self.do_export)
        self.btn_export.setObjectName("primary")
        act.addWidget(self.btn_preview)
        act.addWidget(self.btn_export)
        page3_l.addLayout(act)
        page3_l.addStretch(1)
        self.tabs.addTab(page3, "③ 输出设置")

        # ================= 第 4 页：结果预览 =================
        page4 = QWidget()
        page4_l = QVBoxLayout(page4)
        page4_l.setContentsMargins(10, 10, 10, 10)
        self.tbl_preview = QTableWidget(0, 0)
        self.tbl_preview.verticalHeader().setVisible(False)
        self.tbl_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        page4_l.addWidget(self.tbl_preview)
        self.tabs.addTab(page4, "④ 结果预览")

        # ================= 第 5 页：日志 =================
        page5 = QWidget()
        page5_l = QVBoxLayout(page5)
        page5_l.setContentsMargins(10, 10, 10, 10)
        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("Consolas", 9))
        page5_l.addWidget(self.txt_log)
        self.tabs.addTab(page5, "⑤ 日志")

        # ================= 底部导航 =================
        nav = QHBoxLayout()
        self.lbl_hint = QLabel()
        self.lbl_hint.setStyleSheet("color:#666;")
        nav.addWidget(self.lbl_hint, 1)

        self.btn_prev = QPushButton("← 上一步")
        self.btn_prev.clicked.connect(lambda: self._go_page(-1))
        self.btn_next = QPushButton("下一步 →")
        self.btn_next.clicked.connect(lambda: self._go_page(1))
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_next)
        outer.addLayout(nav)

        self.tabs.currentChanged.connect(self._on_page_changed)
        self._on_page_changed(0)

        # 状态栏右侧常驻显示版本号
        self.lbl_version = QLabel(f"  版本 v{__version__}  ")
        self.lbl_version.setStyleSheet("color:#666;")
        self.lbl_version.setToolTip("程序版本号。发新版本时会自动更新。")
        self.statusBar().addPermanentWidget(self.lbl_version)
        self.statusBar().showMessage("就绪")

    # ------------------------------------------------------------------
    PAGE_HINTS = [
        "第 1 步：分别添加初始表和样表，字段会自动识别出来",
        "第 2 步：逐行核对规则，双击任意一行可编辑；确认后进入下一步",
        "第 3 步：设置输出选项和字体格式（会自动记住）",
        "第 4 步：这里看转换出来的结果，确认没问题再回上一页输出",
        "这里记录每一步的操作和结果",
    ]

    def _on_page_changed(self, index: int):
        self.btn_prev.setEnabled(index > 0)
        self.btn_next.setEnabled(index < self.tabs.count() - 1)
        self.lbl_hint.setText(f"{self.PAGE_HINTS[index]}　（{index + 1}/{self.tabs.count()}）")

    def _go_page(self, delta: int):
        i = self.tabs.currentIndex() + delta
        if 0 <= i < self.tabs.count():
            self.tabs.setCurrentIndex(i)

    # ==================================================================
    # 配置持久化：记住上次用过的设置
    # ==================================================================
    def _restore_settings(self):
        s = self.settings
        self._loading = True

        self.chk_rename.setChecked(s.get_bool("out.rename_enabled"))
        idx = self.cmb_pos.findData(s.get_str("out.rename_position"))
        if idx >= 0:
            self.cmb_pos.setCurrentIndex(idx)
        self.chk_period.setChecked(s.get_bool("out.period_to_date"))
        self.chk_clear.setChecked(s.get_bool("out.clear_example_row"))

        self.chk_fmt.setChecked(s.get_bool("fmt.enabled"))
        fam = s.get_str("fmt.family") or "微软雅黑"
        if self.cmb_font.findText(fam) < 0:
            self.cmb_font.setEditable(True)
        self.cmb_font.setCurrentText(fam)
        self.spin_font_size.setValue(s.get_int("fmt.size") or 11)
        self.chk_bold.setChecked(s.get_bool("fmt.bold"))
        ai = self.cmb_align.findData(s.get_str("fmt.align"))
        self.cmb_align.setCurrentIndex(ai if ai >= 0 else 0)
        self.chk_fmt_header.setChecked(s.get_bool("fmt.apply_header"))
        self._fmt_color = s.get_str("fmt.color") or "#000000"
        self._paint_color_button()
        self._update_fmt_preview()

        geo = s.get_str("ui.geometry")
        if geo:
            try:
                from PySide6.QtCore import QByteArray

                self.restoreGeometry(QByteArray.fromHex(geo.encode("ascii")))
            except Exception:
                pass

        self._loading = False
        self._wire_persistence()
        self._on_fmt_changed()

    def _wire_persistence(self):
        """每个控件改动就立刻存盘，不用点保存。"""
        self.chk_rename.toggled.connect(self.save_settings)
        self.cmb_pos.currentIndexChanged.connect(self.save_settings)
        self.chk_period.toggled.connect(self.save_settings)
        self.chk_clear.toggled.connect(self.save_settings)
        self.chk_fmt.toggled.connect(self._on_fmt_changed)
        self.cmb_font.currentTextChanged.connect(self._on_fmt_changed)
        self.spin_font_size.valueChanged.connect(self._on_fmt_changed)
        self.chk_bold.toggled.connect(self._on_fmt_changed)
        self.cmb_align.currentIndexChanged.connect(self._on_fmt_changed)
        self.chk_fmt_header.toggled.connect(self._on_fmt_changed)

    def save_settings(self, *_):
        if self._loading:
            return
        s = self.settings
        s.set("out.rename_enabled", self.chk_rename.isChecked())
        s.set("out.rename_position", self.cmb_pos.currentData() or "after_first")
        s.set("out.period_to_date", self.chk_period.isChecked())
        s.set("out.clear_example_row", self.chk_clear.isChecked())
        s.set("fmt.enabled", self.chk_fmt.isChecked())
        s.set("fmt.family", self.cmb_font.currentText())
        s.set("fmt.size", self.spin_font_size.value())
        s.set("fmt.color", getattr(self, "_fmt_color", "#000000"))
        s.set("fmt.bold", self.chk_bold.isChecked())
        s.set("fmt.align", self.cmb_align.currentData() or "")
        s.set("fmt.apply_header", self.chk_fmt_header.isChecked())
        try:
            s.set("ui.geometry", bytes(self.saveGeometry().toHex()).decode("ascii"))
        except Exception:
            pass
        s.save()

    # ------------------------------------------------------------------
    def current_format(self) -> CellFormat:
        return CellFormat(
            enabled=self.chk_fmt.isChecked(),
            family=self.cmb_font.currentText() or "微软雅黑",
            size=float(self.spin_font_size.value()),
            color=getattr(self, "_fmt_color", "#000000"),
            bold=self.chk_bold.isChecked(),
            align=self.cmb_align.currentData() or "",
            apply_header=self.chk_fmt_header.isChecked(),
        )

    def _on_fmt_changed(self, *_):
        on = self.chk_fmt.isChecked()
        for w in (self.cmb_font, self.spin_font_size, self.btn_color,
                  self.chk_bold, self.cmb_align, self.chk_fmt_header):
            w.setEnabled(on)
        self._update_fmt_preview()
        self.save_settings()

    def _paint_color_button(self):
        c = QColor(getattr(self, "_fmt_color", "#000000"))
        fg = "#ffffff" if c.lightness() < 128 else "#000000"
        self.btn_color.setText(self._fmt_color.upper())
        self.btn_color.setStyleSheet(
            f"background:{self._fmt_color}; color:{fg}; border:1px solid #c8c8c8;"
            "border-radius:6px; padding:6px 12px;"
        )

    def pick_color(self):
        cur = QColor(getattr(self, "_fmt_color", "#000000"))
        c = QColorDialog.getColor(cur, self, "选择字体颜色")
        if c.isValid():
            self._fmt_color = c.name()
            self._paint_color_button()
            self._update_fmt_preview()
            self.save_settings()

    def _update_fmt_preview(self):
        fmt = self.current_format()
        if fmt.enabled:
            self.lbl_fmt_preview.setText(
                f"格式预览（只影响数据行{'+表头行' if fmt.apply_header else ''}）："
                "应发工资  65000.00  张三"
            )
            hint = ""
        else:
            self.lbl_fmt_preview.setText("格式预览：数据行完全沿用样表里那一行的格式，不做任何改动")
            hint = "color:#777;"
        self.lbl_fmt_preview.setStyleSheet(
            f"background:#ffffff;border:1px solid #e0e4e8;border-radius:6px;padding:10px;{hint}"
            f"font-family:'{fmt.family}';font-size:{int(fmt.size)}pt;"
            f"color:{fmt.color};font-weight:{'bold' if fmt.bold else 'normal'};"
            + (f"text-align:{ {'left':'left','center':'center','right':'right'}.get(fmt.align,'left') };"
               if fmt.enabled and fmt.align else "")
        )

    def _apply_style(self):
        self.setStyleSheet(
            """
            QGroupBox { font-weight:600; border:1px solid #dcdcdc; border-radius:8px;
                        margin-top:12px; padding:10px 8px 8px 8px; background:#ffffff; }
            QGroupBox::title { subcontrol-origin: margin; left:10px; padding:0 4px; color:#333; }
            QPushButton { padding:6px 12px; border:1px solid #c8c8c8; border-radius:6px;
                          background:#f7f7f7; }
            QPushButton:hover { background:#ededed; }
            QPushButton:disabled { color:#b4b4b4; background:#fafafa; }
            QPushButton#primary { background:#2f7d4f; color:white; border:1px solid #276b43;
                                  font-weight:600; padding:6px 16px; }
            QPushButton#primary:hover { background:#286b44; }
            QTableWidget { gridline-color:#ececec; }
            QHeaderView::section { background:#f2f2f2; border:0; padding:5px;
                                   border-right:1px solid #e2e2e2; border-bottom:1px solid #e2e2e2; }
            QTabWidget::pane { border:1px solid #dcdcdc; border-radius:8px; top:-1px;
                               background:#fbfbfb; }
            QTabBar::tab { padding:8px 22px; margin-right:4px; border:1px solid #dcdcdc;
                           border-bottom:0; border-top-left-radius:8px; border-top-right-radius:8px;
                           background:#f0f0f0; color:#555; }
            QTabBar::tab:selected { background:#ffffff; color:#1f7a45; font-weight:600; }
            QTabBar::tab:hover { background:#e8f3ec; }
            """
        )

    # ==================================================================
    # 日志 / 状态
    # ==================================================================
    def _log(self, msg: str):
        self.txt_log.appendPlainText(msg)
        self.statusBar().showMessage(msg.splitlines()[0][:120])

    def _err(self, title: str, msg: str):
        self._log(f"[错误] {title}: {msg}")
        QMessageBox.critical(self, title, msg)

    # ==================================================================
    # ① 初始表
    # ==================================================================
    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择初始表", self._default_dir(), EXCEL_FILTER)
        if not path:
            return
        try:
            st = parse_source(path)
        except Exception as e:
            self._err("读取初始表失败", f"{e}\n\n{traceback.format_exc()}")
            return
        self.source = st
        self.lbl_source.setText(os.path.basename(path))
        self.lbl_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_source.setStyleSheet("color:#333;")
        mode_txt = "按人分块结构" if st.mode == "block" else "流水表结构"
        self.lbl_source_info.setText(
            f"工作表：{st.sheet}　|　结构：{mode_txt}　|　"
            f"记录 {len(st.records)} 条　|　字段 {len(st.fields)} 个"
        )
        self.list_source_fields.clear()
        self.list_source_fields.addItems(st.fields)
        self.settings.set("last.source", path)
        self.settings.save()
        self._log(f"已载入初始表：{os.path.basename(path)}（{mode_txt}，字段 {len(st.fields)} 个）")
        self._after_load()

    # ==================================================================
    # ② 样表
    # ==================================================================
    def choose_sample(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择样表", self._default_dir(), EXCEL_FILTER)
        if not path:
            return
        try:
            from core.excel_reader import read_workbook_rows

            names, _, _ = read_workbook_rows(path)
        except Exception as e:
            self._err("读取样表失败", str(e))
            return
        self._loading = True
        self.cmb_sheet.clear()
        self.cmb_sheet.addItems(names)
        self._loading = False
        self._sample_file = path
        self.lbl_sample.setText(os.path.basename(path))
        self.lbl_sample.setStyleSheet("color:#333;")
        self.settings.set("last.sample", path)
        self.settings.save()
        self._resample()

    def _resample(self):
        if self._loading or not self._sample_file:
            return
        path = self._sample_file
        if not os.path.exists(path):
            return
        sheet = self.cmb_sheet.currentText() or None
        try:
            spec = parse_sample(
                path,
                sheet,
                header_row=self.spin_header.value(),
                data_start_row=self.spin_start.value(),
            )
        except Exception as e:
            self._err("解析样表失败", str(e))
            return
        self.sample = spec
        self.list_sample_fields.clear()
        self.list_sample_fields.addItems(spec.columns)
        self.lbl_rename_rule.setText("重名规则：" + (spec.rename_rule_text or "样表中未找到重名规则说明"))
        self._log(
            f"已载入样表：{os.path.basename(path)}　工作表 {spec.sheet}　"
            f"表头第 {spec.header_row} 行　数据从第 {spec.data_start_row} 行开始　"
            f"字段 {len(spec.columns)} 个"
        )
        self._after_load()

    def _default_dir(self) -> str:
        for p in (
            self._sample_file,
            getattr(self.source, "path", ""),
            self.settings.get_str("last.sample"),
            self.settings.get_str("last.source"),
        ):
            if p and os.path.exists(p):
                return os.path.dirname(p)
        return os.path.expanduser("~")

    def _after_load(self):
        """两张表都就绪时，自动识别一次字段（样表列发生变化时重新识别）。"""
        if not (self.source and self.sample):
            return
        cols = tuple(self.sample.columns)
        if not self.rules or cols != self._last_columns:
            self.do_auto_detect()
        # 两张表刚凑齐时，自动带用户到「转换规则」页
        if self.tabs.currentIndex() == 0 and not self._auto_advanced:
            self._auto_advanced = True
            self.tabs.setCurrentIndex(1)

    # ==================================================================
    # ③ 规则
    # ==================================================================
    def do_auto_detect(self):
        if not self.source or not self.sample:
            QMessageBox.information(self, "提示", "请先添加初始表和样表。")
            return
        detected = auto_detect(self.sample.columns, self.source.fields)
        # 保留已有规则的确认状态
        old = {r.target: r for r in self.rules}
        for r in detected:
            if r.target in old:
                r.enabled = old[r.target].enabled
                r.confirmed = old[r.target].confirmed
        self.rules = detected
        self._last_columns = tuple(self.sample.columns)
        self.refresh_rules()
        ok = sum(1 for r in self.rules if r.mode != "skip")
        self._log(f"自动识别完成：{len(self.rules)} 个样表字段，其中 {ok} 个已匹配到初始表字段，请逐条核对后确认。")

    def refresh_rules(self):
        self._loading = True
        self.tbl_rules.setRowCount(len(self.rules))
        for i, r in enumerate(self.rules):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if r.enabled else Qt.Unchecked)
            self.tbl_rules.setItem(i, 0, chk)

            vals = [r.target, r.mode_label(), r.source_label(), r.filter_label(), r.status_label()]
            for j, v in enumerate(vals, start=1):
                it = QTableWidgetItem(str(v))
                if j == 1:
                    it.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
                self.tbl_rules.setItem(i, j, it)

            if r.mode == "skip":
                color = QColor("#b0b0b0")
            elif not r.confirmed:
                color = QColor("#c07a00")
            else:
                color = QColor("#1f7a45")
            self.tbl_rules.item(i, 5).setForeground(color)
        self._loading = False

    def _on_rule_item_changed(self, item: QTableWidgetItem):
        if self._loading:
            return
        if item.column() == 0:
            self.rules[item.row()].enabled = item.checkState() == Qt.Checked

    def _current_row(self) -> int:
        sel = self.tbl_rules.selectionModel().selectedRows()
        return sel[0].row() if sel else -1

    def add_rule(self):
        if not self.source or not self.sample:
            QMessageBox.information(self, "提示", "请先添加初始表和样表。")
            return
        used = {r.target for r in self.rules}
        rule = Rule(target="")
        for c in self.sample.columns:
            if c not in used:
                rule.target = c
                break
        self._edit_rule_dialog(rule, insert=True)

    def edit_rule(self):
        i = self._current_row()
        if i < 0:
            QMessageBox.information(self, "提示", "请先选中一行规则。")
            return
        self._edit_rule_dialog(self.rules[i], insert=False, index=i)

    def _edit_rule_dialog(self, rule: Rule, insert: bool, index: int = -1):
        dlg = RuleDialog(self.source, self.sample.columns, rule, self)
        if dlg.exec():
            new_rule = dlg.result_rule
            if insert:
                self.rules.append(new_rule)
            else:
                self.rules[index] = new_rule
            self.refresh_rules()
            self._log(f"规则已保存：{new_rule.target} ← {new_rule.source_label() or new_rule.mode_label()}")

    def del_rule(self):
        i = self._current_row()
        if i < 0:
            QMessageBox.information(self, "提示", "请先选中一行规则。")
            return
        target = self.rules[i].target
        del self.rules[i]
        self.refresh_rules()
        self._log(f"已删除规则：{target}")

    def move_rule(self, delta: int):
        i = self._current_row()
        j = i + delta
        if i < 0 or j < 0 or j >= len(self.rules):
            return
        self.rules[i], self.rules[j] = self.rules[j], self.rules[i]
        self.refresh_rules()
        self.tbl_rules.selectRow(j)

    def confirm_all(self):
        for r in self.rules:
            if r.mode != "skip":
                r.confirmed = True
        self.refresh_rules()
        self._log("已将全部规则标记为「已确认」。")
        QMessageBox.information(self, "完成", "全部规则已确认。")

    # ==================================================================
    # ④ 转换 / 输出
    # ==================================================================
    def _run_convert(self):
        if not self.source or not self.sample:
            QMessageBox.information(self, "提示", "请先添加初始表和样表。")
            return None
        if not self.rules:
            QMessageBox.information(self, "提示", "还没有规则，请先点「自动识别字段」。")
            return None
        return convert(
            self.source,
            self.sample,
            self.rules,
            rename_enabled=self.chk_rename.isChecked(),
            rename_position=self.cmb_pos.currentData(),
            period_to_date_enabled=self.chk_period.isChecked(),
        )

    def do_preview(self):
        res = self._run_convert()
        if res is None:
            return
        rows, stats = res
        self.rows = rows
        cols = self.sample.columns
        self.tbl_preview.clear()
        self.tbl_preview.setColumnCount(len(cols))
        self.tbl_preview.setHorizontalHeaderLabels(cols)
        show = rows[:200]
        self.tbl_preview.setRowCount(len(show))
        for i, row in enumerate(show):
            for j, c in enumerate(cols):
                v = row.get(c)
                if hasattr(v, "strftime"):
                    txt = v.strftime("%Y-%m-%d")
                elif v is None:
                    txt = ""
                elif isinstance(v, float) and v.is_integer():
                    txt = str(int(v))
                else:
                    txt = str(v)
                self.tbl_preview.setItem(i, j, QTableWidgetItem(txt))
        self.tbl_preview.resizeColumnsToContents()
        self._log(
            f"预览完成：初始表 {stats['初始表人数']} 人 → 输出 {stats['输出行数']} 行"
            + (f"，重名改名 {stats['重命名人数']} 人" if stats["重命名人数"] else "")
        )
        if len(rows) > 200:
            self._log(f"（预览仅显示前 200 行，共 {len(rows)} 行）")

    def do_export(self):
        res = self._run_convert()
        if res is None:
            return
        rows, stats = res

        unconfirmed = [r.target for r in self.rules if r.enabled and r.mode != "skip" and not r.confirmed]
        if unconfirmed:
            ans = QMessageBox.question(
                self,
                "还有规则未确认",
                "以下规则尚未「确认」：\n\n" + "、".join(unconfirmed) +
                "\n\n是否仍要继续输出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return

        base = os.path.splitext(os.path.basename(self.sample.path))[0]
        default = os.path.join(self._default_dir(), f"{base}_完成表.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "保存完成表", default, "Excel 文件 (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            info = export(
                self.sample.path,
                path,
                self.sample.sheet,
                self.sample,
                rows,
                clear_example_rows=self.chk_clear.isChecked(),
                fmt=self.current_format(),
            )
        except Exception as e:
            self._err("输出失败", f"{e}\n\n{traceback.format_exc()}")
            return

        self.rows = rows
        self._log(
            f"输出成功：{info['输出文件']}（工作表 {info['工作表']}，"
            f"从第 {info['起始行']} 行写入 {info['写入行数']} 行 × {info['列数']} 列，"
            f"格式 {info['自定义格式']}）"
        )
        if stats["重命名人数"]:
            self._log(f"重名处理：{stats['重命名人数']} 人的姓名已按规则加序号。")
        QMessageBox.information(
            self,
            "输出完成",
            f"已生成完成表：\n{path}\n\n"
            f"· 从第 {info['起始行']} 行开始写入 {info['写入行数']} 行数据\n"
            f"· 样表原有表头与说明文字已保留\n"
            f"· 字体格式：{info['自定义格式']}\n"
            + (f"· 重名改名 {stats['重命名人数']} 人\n" if stats["重命名人数"] else ""),
        )

    # ==================================================================
    # 检查更新
    # ==================================================================
    def open_update_dialog(self):
        dlg = UpdateDialog(self.settings, self, auto_check=True)
        dlg.updated.connect(self._on_updated)
        dlg.exec()

    def silent_update_check(self):
        """启动时后台悄悄查一下，有新版就在按钮上提示，不弹窗打扰。"""
        url = self.settings.get_str("update.url")
        if not url:
            return
        self._checker = CheckThread(url, self)
        self._checker.ok.connect(self._on_silent_result)
        self._checker.failed.connect(lambda _m: None)   # 静默失败，不打扰
        self._checker.start()

    def _on_silent_result(self, info: dict):
        self.settings.set("update.proxy_mode", updater.get_preferred_mode())
        self.settings.set("update.last_check", info.get("latest", ""))
        self.settings.save()

        if not info.get("has_update"):
            self._log(f"检查更新：已是最新版本（v{info['current']}）。")
            return

        self._log(f"检查更新：发现新版本 v{info['latest']}（当前 v{info['current']}）。")
        ans = QMessageBox.question(
            self,
            "发现新版本",
            f"发现新版本 v{info['latest']}，是否现在更新？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ans == QMessageBox.Yes:
            dlg = UpdateDialog(self.settings, self, preset_info=info)
            dlg.updated.connect(self._on_updated)
            dlg.exec()
        else:
            # 这次不更新，就在按钮上留个提示，下次点还能升
            self.btn_update.setText(f"有新版本 v{info['latest']}")
            self.btn_update.setStyleSheet(
                "background:#fff3cd;border:1px solid #e0b64a;border-radius:6px;"
                "padding:6px 12px;font-weight:600;color:#7a5300;"
            )

    def _on_updated(self, new_exe: str):
        self.save_settings()
        self._log(f"程序已更新，正在启动新版本：{new_exe}")
        QTimer.singleShot(300, self.close)

    # ==================================================================
    # 关闭时保存
    # ==================================================================
    def closeEvent(self, event):
        self.save_settings()
        try:
            from core import updater

            updater.cleanup_old_versions()
        except Exception:
            pass
        super().closeEvent(event)
