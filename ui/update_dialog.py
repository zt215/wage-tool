# -*- coding: utf-8 -*-
"""检查更新对话框 —— 只显示必要信息。

打开就自动检查：
  · 有新版本 -> 一行提示 + 更新说明 + 「立即更新」
  · 已是最新 -> 一行绿字，别的都不显示
  · 检查失败 -> 一行红字说明原因
更新地址藏在小链接后面，平时不占地方。
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from core import updater
from core.version import __version__


class CheckThread(QThread):
    ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            self.ok.emit(updater.check(self.url))
        except Exception as e:
            self.failed.emit(str(e))


class DownloadThread(QThread):
    ok = Signal(str, str)          # (本地文件, sha256)
    failed = Signal(str)
    progress = Signal(int, int)    # (已下载, 总量)

    def __init__(self, url: str, dest: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.dest = dest

    def run(self):
        try:
            updater.download(self.url, self.dest, lambda g, t: self.progress.emit(g, t))
            self.ok.emit(self.dest, updater.sha256_of(self.dest))
        except Exception as e:
            self.failed.emit(str(e))


def human_size(n: int) -> str:
    if not n:
        return "未知"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


GREEN = ("background:#eefaf2;border:1px solid #bfe6cf;border-radius:6px;"
         "padding:10px;color:#146c39;font-weight:600;")
YELLOW = ("background:#fff8e6;border:1px solid #f0dca8;border-radius:6px;"
          "padding:10px;color:#8a4b00;font-weight:600;")
RED = ("background:#fdeeee;border:1px solid #f2c0c0;border-radius:6px;"
       "padding:10px;color:#a12b2b;font-weight:600;")
PLAIN = ("background:#f5f7f9;border:1px solid #e0e4e8;border-radius:6px;"
         "padding:10px;color:#444;")


class UpdateDialog(QDialog):
    """检查更新 + 下载 + 自动替换。"""

    updated = Signal(str)      # 替换完成，参数是新程序路径

    def __init__(self, settings, parent=None, auto_check: bool = True,
                 preset_info: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("检查更新")
        self.setMinimumWidth(460)
        self.settings = settings
        self.info: dict | None = None
        self._checker = None
        self._downloader = None

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        self.lbl_current = QLabel(f"当前版本　v{__version__}")
        self.lbl_current.setStyleSheet("font-weight:600;font-size:12pt;")
        lay.addWidget(self.lbl_current)

        self.lbl_state = QLabel("正在检查更新…")
        self.lbl_state.setWordWrap(True)
        self.lbl_state.setStyleSheet(PLAIN)
        lay.addWidget(self.lbl_state)

        self.txt_notes = QTextEdit()
        self.txt_notes.setReadOnly(True)
        self.txt_notes.setVisible(False)
        lay.addWidget(self.txt_notes, 1)

        self.bar = QProgressBar()
        self.bar.setVisible(False)
        lay.addWidget(self.bar)

        # ---- 底部：更新地址（折叠） + 按钮 ----
        btns = QHBoxLayout()
        self.btn_addr = QPushButton("更新地址")
        self.btn_addr.setFlat(True)
        self.btn_addr.setStyleSheet("color:#999;border:0;padding:2px;")
        self.btn_addr.setToolTip("平时不用动。换更新源的时候再点开改。")
        self.btn_addr.clicked.connect(self.toggle_addr)
        btns.addWidget(self.btn_addr)
        btns.addStretch(1)

        self.btn_do = QPushButton("立即更新")
        self.btn_do.setObjectName("primary")
        self.btn_do.clicked.connect(self.do_update)
        self.btn_do.setVisible(False)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.reject)
        btns.addWidget(self.btn_do)
        btns.addWidget(self.btn_close)
        lay.addLayout(btns)

        self.ed_url = QPlainTextEdit(settings.get_str("update.url"))
        self.ed_url.setFixedHeight(56)
        self.ed_url.setVisible(False)
        self.ed_url.setPlaceholderText("https://github.com/zt215/wage-tool")
        lay.addWidget(self.ed_url)

        if preset_info:
            self.on_check_ok(preset_info)
        elif auto_check:
            self.start_check()

    # ------------------------------------------------------------------
    def toggle_addr(self):
        show = not self.ed_url.isVisible()
        self.ed_url.setVisible(show)
        if show:
            self.ed_url.setFocus()
        else:
            text = self.ed_url.toPlainText().strip()
            if text and text != self.settings.get_str("update.url"):
                self.settings.set("update.url", text)
                self.settings.save()
                self.start_check()
        self.adjustSize()

    def start_check(self):
        url = self.ed_url.toPlainText().strip() or self.settings.get_str("update.url")
        if not url:
            self.show_state("还没填更新地址", RED)
            return
        self.settings.set("update.url", url)
        self.settings.save()

        self.btn_do.setVisible(False)
        self.txt_notes.setVisible(False)
        self.bar.setVisible(False)
        self.ed_url.setVisible(False)
        self.show_state("正在检查更新…", PLAIN)
        self.adjustSize()

        self._checker = CheckThread(url, self)
        self._checker.ok.connect(self.on_check_ok)
        self._checker.failed.connect(self.on_check_failed)
        self._checker.start()

    def show_state(self, text: str, style: str):
        self.lbl_state.setText(text)
        self.lbl_state.setStyleSheet(style)

    # ------------------------------------------------------------------
    def on_check_ok(self, info: dict):
        self.info = info
        self.settings.set("update.proxy_mode", updater.get_preferred_mode())

        if info.get("has_update"):
            size = info.get("size") or 0
            tip = f"发现新版本 v{info['latest']}"
            if size:
                tip += f"（{human_size(size)}）"
            self.show_state(f"{tip}，点「立即更新」自动升级", YELLOW)
            self.btn_do.setVisible(True)
            notes = (info.get("notes") or "").strip()
            self.txt_notes.setPlainText(notes or "（本次发布没有填写更新说明）")
            self.txt_notes.setVisible(True)
        else:
            self.show_state(f"已经是最新版本（v{info['current']}），不用更新", GREEN)
            self.btn_do.setVisible(False)
            self.txt_notes.setVisible(False)
        self.settings.save()
        self.adjustSize()

    def on_check_failed(self, msg: str):
        first = str(msg).splitlines()[0] if str(msg).strip() else "检查失败"
        self.show_state(f"检查失败：{first}", RED)
        self.lbl_state.setToolTip(str(msg))
        self.btn_do.setVisible(False)
        self.txt_notes.setPlainText(str(msg))
        self.txt_notes.setVisible(True)
        self.adjustSize()

    # ------------------------------------------------------------------
    def do_update(self):
        if not self.info or not self.info.get("has_update"):
            return
        if not updater.current_exe():
            QMessageBox.information(
                self, "无法自动更新",
                "当前是以源码方式运行的，不能自动替换自己。\n"
                "请把下载到的新程序手动替换一下。",
            )
        url = self.info.get("url")
        if not url:
            QMessageBox.warning(
                self, "无法更新",
                "没拿到下载地址。\n\n"
                "GitHub：确认这个 Release 里已经上传了 exe 文件。\n"
                "静态清单：确认 version.json 里的 url 字段填了。",
            )
            return

        dest = updater.download_temp_path()
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.bar.setFormat("正在下载…")
        self.btn_do.setEnabled(False)
        self.btn_do.setVisible(False)
        self.txt_notes.setVisible(False)

        self._downloader = DownloadThread(url, dest, self)
        self._downloader.progress.connect(self.on_progress)
        self._downloader.ok.connect(self.on_downloaded)
        self._downloader.failed.connect(self.on_download_failed)
        self._downloader.start()

    def on_progress(self, got: int, total: int):
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(got)
            self.bar.setFormat(f"正在下载 %p%（{human_size(got)} / {human_size(total)}）")
        else:
            self.bar.setRange(0, 0)
            self.bar.setFormat(f"正在下载 {human_size(got)}")

    def on_download_failed(self, msg: str):
        self.bar.setVisible(False)
        self.btn_do.setEnabled(True)
        self.btn_do.setVisible(True)
        self.show_state(f"下载失败：{str(msg).splitlines()[0]}", RED)

    def on_downloaded(self, path: str, digest: str):
        self.bar.setVisible(False)
        expect = (self.info or {}).get("sha256") or ""
        if expect and expect.lower() != (digest or "").lower():
            self.btn_do.setEnabled(True)
            self.btn_do.setVisible(True)
            self.show_state("下载的文件校验不通过，已放弃更新", RED)
            return

        target = updater.current_exe()
        if not target:
            QMessageBox.information(self, "已下载", f"新版本已下载到：\n{path}\n\n请手动替换。")
            return

        try:
            new_path = updater.install_update(
                path, target,
                new_name=(self.info or {}).get("filename") or "",
                restart=True,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "更新失败",
                f"{e}\n\n新版本已经下载到：\n{path}\n可以手动替换。",
            )
            return

        self.updated.emit(new_path)
        QMessageBox.information(
            self, "更新完成",
            f"已更新到 v{self.info['latest']}，程序正在重新启动。",
        )
        self.accept()
