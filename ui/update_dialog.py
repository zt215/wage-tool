# -*- coding: utf-8 -*-
"""检查更新对话框。"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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
            digest = updater.sha256_of(self.dest)
            self.ok.emit(self.dest, digest)
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


class UpdateDialog(QDialog):
    """检查更新 + 下载 + 自动替换。"""

    updated = Signal(str)   # 替换完成，参数是新程序路径

    def __init__(self, settings, parent=None, auto_check: bool = True):
        super().__init__(parent)
        self.setWindowTitle("检查更新")
        self.resize(560, 460)
        self.settings = settings
        self.info: dict | None = None
        self._checker = None
        self._downloader = None

        lay = QVBoxLayout(self)

        lay.addWidget(QLabel("更新地址（可以写多行，按顺序依次尝试；GitHub 仓库地址或 version.json 都认）："))
        self.ed_url = QPlainTextEdit(settings.get_str("update.url"))
        self.ed_url.setPlaceholderText(
            "https://github.com/zt215/wage-tool\n"
            "https://你的服务器/update/version.json"
        )
        self.ed_url.setFixedHeight(62)
        lay.addWidget(self.ed_url)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_check = QPushButton("检查更新")
        self.btn_check.clicked.connect(self.start_check)
        row.addWidget(self.btn_check)
        lay.addLayout(row)

        self.lbl_state = QLabel(f"当前版本：{__version__}")
        self.lbl_state.setStyleSheet("font-weight:600;")
        lay.addWidget(self.lbl_state)

        self.lbl_detail = QLabel("点「检查更新」看看服务器上有没有新版本。")
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setStyleSheet(
            "background:#f5f7f9;border:1px solid #e0e4e8;border-radius:6px;padding:8px;"
        )
        lay.addWidget(self.lbl_detail)

        lay.addWidget(QLabel("更新说明："))
        self.txt_notes = QTextEdit()
        self.txt_notes.setReadOnly(True)
        self.txt_notes.setPlaceholderText("（服务器清单里的 notes 会显示在这里）")
        lay.addWidget(self.txt_notes, 1)

        self.bar = QProgressBar()
        self.bar.setVisible(False)
        self.bar.setTextVisible(True)
        lay.addWidget(self.bar)

        btns = QDialogButtonBox()
        self.btn_do = QPushButton("立即更新")
        self.btn_do.setObjectName("primary")
        self.btn_do.setEnabled(False)
        self.btn_do.clicked.connect(self.do_update)
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.reject)
        btns.addButton(self.btn_do, QDialogButtonBox.AcceptRole)
        btns.addButton(self.btn_close, QDialogButtonBox.RejectRole)
        lay.addWidget(btns)

        if auto_check:
            self.start_check()

    # ------------------------------------------------------------------
    def start_check(self):
        url = self.ed_url.toPlainText().strip()
        if not url:
            QMessageBox.information(self, "提示", "请先填写更新地址。")
            return
        self.settings.set("update.url", url)
        self.settings.save()

        self.btn_check.setEnabled(False)
        self.btn_check.setText("检查中…")
        self.btn_do.setEnabled(False)
        self.lbl_detail.setText("正在连接服务器…")

        self._checker = CheckThread(url, self)
        self._checker.ok.connect(self.on_check_ok)
        self._checker.failed.connect(self.on_check_failed)
        self._checker.finished.connect(lambda: (self.btn_check.setEnabled(True),
                                                self.btn_check.setText("检查更新")))
        self._checker.start()

    def on_check_ok(self, info: dict):
        self.info = info
        # 记住这次用哪种网络出口通的（直连 / 系统代理）
        self.settings.set("update.proxy_mode", updater.get_preferred_mode())
        self.settings.save()

        where = info.get("source_kind") or "更新源"
        self.lbl_state.setText(
            f"当前版本：{info['current']}　→　最新版本：{info['latest']}　（来源：{where}）"
        )
        if info.get("has_update"):
            self.lbl_detail.setText(
                f"发现新版本 {info['latest']}（大小 {human_size(info.get('size', 0))}）\n"
                "点「立即更新」会自动下载并替换，替换完程序会自己重启。"
            )
            self.lbl_detail.setStyleSheet(
                "background:#fff8e6;border:1px solid #f0dca8;border-radius:6px;padding:8px;"
            )
            self.btn_do.setEnabled(True)
        else:
            self.lbl_detail.setText(
                f"已经是最新版本（{info['current']}），不用更新。"
            )
            self.lbl_detail.setStyleSheet(
                "background:#eefaf2;border:1px solid #bfe6cf;border-radius:6px;padding:8px;"
            )
            self.btn_do.setEnabled(False)
        self.txt_notes.setPlainText(info.get("notes") or "（发布时没写更新说明）")

    def on_check_failed(self, msg: str):
        lines = str(msg).splitlines()
        head = lines[0] if lines else "检查失败"
        self.lbl_detail.setText(f"检查失败：{head}")
        self.lbl_detail.setStyleSheet(
            "background:#fdeeee;border:1px solid #f2c0c0;border-radius:6px;padding:8px;"
        )
        self.lbl_detail.setToolTip(msg)
        self.txt_notes.setPlainText(str(msg))

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
                "如果是 GitHub：确认这个 Release 里已经上传了 exe 文件。\n"
                "如果是静态清单：确认 version.json 里的 url 字段填了。",
            )
            return

        dest = updater.download_temp_path()
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.btn_do.setEnabled(False)
        self.btn_check.setEnabled(False)
        self.lbl_detail.setText("正在下载新版本…")

        self._downloader = DownloadThread(url, dest, self)
        self._downloader.progress.connect(self.on_progress)
        self._downloader.ok.connect(self.on_downloaded)
        self._downloader.failed.connect(self.on_download_failed)
        self._downloader.start()

    def on_progress(self, got: int, total: int):
        if total > 0:
            self.bar.setRange(0, total)
            self.bar.setValue(got)
            self.bar.setFormat(f"下载中 %p%  ({human_size(got)} / {human_size(total)})")
        else:
            self.bar.setRange(0, 0)
            self.bar.setFormat(f"下载中 {human_size(got)}")

    def on_download_failed(self, msg: str):
        self.bar.setVisible(False)
        self.btn_do.setEnabled(True)
        self.btn_check.setEnabled(True)
        self.lbl_detail.setText(f"下载失败：{msg}")
        self.lbl_detail.setStyleSheet(
            "background:#fdeeee;border:1px solid #f2c0c0;border-radius:6px;padding:8px;"
        )

    def on_downloaded(self, path: str, digest: str):
        self.bar.setVisible(False)
        expect = (self.info or {}).get("sha256") or ""
        if expect and expect.lower() != (digest or "").lower():
            self.btn_do.setEnabled(True)
            self.btn_check.setEnabled(True)
            QMessageBox.critical(
                self, "文件校验失败",
                "下载到的文件和服务器记录的校验值不一致，可能没传完，已放弃更新。",
            )
            self.lbl_detail.setText("文件校验失败，已放弃更新。")
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
            f"已更新到 {self.info['latest']}，程序正在重新启动。\n\n"
            f"新程序位置：\n{new_path}\n\n"
            "（文件名带版本号，桌面如果有旧版本的快捷方式，删掉重新建一个就行）",
        )
        self.accept()
