# -*- coding: utf-8 -*-
"""员工工资申报转换工具 —— 程序入口。"""
from __future__ import annotations

import os
import sys

# 允许直接双击运行（打包成 exe 后也适用）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _resource(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def cli_check_update(argv) -> int:
    """命令行检查更新。主要用于验证「打包后的程序能不能正常访问更新源」。

    用法：工具.exe --check-update [--url <地址>]
    结果同时打印并写到同目录的「检查更新结果.txt」。
    """
    import argparse
    import traceback

    from core import Settings, updater
    from core.version import __version__

    p = argparse.ArgumentParser(prog="检查更新")
    p.add_argument("--url", default="", help="更新地址，不填就用设置里保存的")
    p.add_argument("--download", action="store_true",
                   help="顺便把文件下载下来并校验 sha256（排查下载问题用）")
    args = p.parse_args(argv)

    s = Settings()
    updater.set_preferred_mode(s.get_str("update.proxy_mode"))
    text = args.url or s.get_str("update.url")

    lines = [f"当前版本：{__version__}", f"更新地址：{text}", ""]
    code = 0
    try:
        info = updater.check(text)
        lines += [
            f"网络出口：{'直连' if updater.get_preferred_mode() == 'direct' else '系统代理'}",
            f"最新版本：{info['latest']}",
            f"是否有更新：{'是' if info['has_update'] else '否（已是最新）'}",
            f"文件：{info['filename']}（{info['size'] / 1024 / 1024:.1f} MB）",
            f"下载地址：{info['url']}",
            f"备用地址：{info.get('url_alt') or '（无）'}",
            f"sha256：{info['sha256'] or '（对方未提供）'}",
            f"来源：{info.get('source_kind')}",
            "",
        ]
        if args.download:
            import time

            t0 = time.time()
            tmp = updater.download_temp_path()
            updater.download(info["url"], tmp, alt=info.get("url_alt") or "")
            dt = max(time.time() - t0, 0.001)
            got = os.path.getsize(tmp)
            mine = updater.sha256_of(tmp)
            lines += [
                f"实测下载：{got / 1024 / 1024:.1f} MB，用时 {dt:.1f}s"
                f"（{got / dt / 1024:.0f} KB/s）",
                f"下载后 sha256：{mine}",
                f"校验结果：{'一致 ✔' if (not info['sha256'] or mine == info['sha256']) else '不一致 ✘'}",
                "",
            ]
            try:
                os.remove(tmp)
            except Exception:
                pass
        lines += ["结果：成功 ✔"]
        # 记下这次用哪种出口通的
        s.set("update.proxy_mode", updater.get_preferred_mode())
        s.save()
    except Exception as e:
        lines += [traceback.format_exc(), f"结果：失败 ✘ {e}"]
        code = 1

    out = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "检查更新结果.txt")
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass
    try:
        print("\n".join(lines))
    except Exception:
        pass
    return code


def selftest() -> int:
    """打包后的自检：离屏建窗口，确认依赖与界面都正常。结果写到「自检结果.txt」。"""
    import tempfile
    import traceback

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    lines: list[str] = []
    code = 0
    try:
        from PySide6 import QtCore

        lines.append(f"PySide6/Qt 版本: {QtCore.qVersion()}")
        app = QApplication.instance() or QApplication([])  # noqa: F841
        win = MainWindow()
        lines.append(f"主窗口创建成功，规则表列数: {win.tbl_rules.columnCount()}")
        tabs = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        lines.append(f"页签数: {win.tabs.count()} {' | '.join(tabs)}")
        same_page = win.tbl_preview.parentWidget().parentWidget() is win.tabs.widget(2)
        lines.append(f"预览表与输出设置同页: {same_page}")

        import openpyxl

        tmp = tempfile.mktemp(suffix=".xlsx")
        openpyxl.Workbook().save(tmp)
        openpyxl.load_workbook(tmp).close()
        os.remove(tmp)
        lines.append("openpyxl 读写正常")
        lines.append("自检通过 ✔")
    except Exception:
        lines.append(traceback.format_exc())
        lines.append("自检失败 ✘")
        code = 1

    out = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "自检结果.txt")
    try:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass
    return code


def cli_convert(argv) -> int:
    """命令行批量转换（也用于打包后的端到端验证）。

    用法：
      工具.exe --convert --source 初始表.xlsx --sample 样表.xlsx --out 完成表.xlsx
    结果摘要会写到「<输出文件名>_报告.txt」。
    """
    import argparse
    import traceback

    from core import __version__, auto_detect, convert, parse_sample, parse_source
    from core.exporter import CellFormat, export

    p = argparse.ArgumentParser(prog="员工工资申报转换工具", add_help=True)
    p.add_argument("--source", required=True, help="初始表（申报汇总表）路径")
    p.add_argument("--sample", required=True, help="样表路径")
    p.add_argument("--out", required=True, help="输出的完成表路径")
    p.add_argument("--sheet", default=None, help="样表工作表名（默认第一个）")
    p.add_argument("--header-row", type=int, default=1, help="样表表头行，默认 1")
    p.add_argument("--start-row", type=int, default=4, help="数据写入起始行，默认 4")
    p.add_argument("--no-rename", action="store_true", help="关闭重名规则")
    p.add_argument("--keep-example", action="store_true", help="保留样表示例数据行")
    p.add_argument("--font", default="", help="数据行字体（不填则沿用样表格式）")
    p.add_argument("--font-size", type=float, default=11, help="字号，默认 11")
    p.add_argument("--color", default="#000000", help="字体颜色，如 #C00000")
    p.add_argument("--bold", action="store_true", help="字体加粗")
    p.add_argument("--align", default="", choices=["", "left", "center", "right"],
                   help="水平对齐")
    p.add_argument("--fmt-header", action="store_true", help="表头行也应用上面的字体")
    args = p.parse_args(argv)

    log: list[str] = []
    try:
        st = parse_source(args.source)
        sp = parse_sample(args.sample, args.sheet, args.header_row, args.start_row)
        rules = auto_detect(sp.columns, st.fields)
        for r in rules:
            r.confirmed = True
        rows, stats = convert(
            st, sp, rules,
            rename_enabled=not args.no_rename,
            period_to_date_enabled=True,
        )
        fmt = CellFormat(
            enabled=bool(args.font),
            family=args.font or "微软雅黑",
            size=args.font_size,
            color=args.color,
            bold=args.bold,
            align=args.align,
            apply_header=args.fmt_header,
        )
        info = export(
            sp.path, args.out, sp.sheet, sp, rows,
            clear_example_rows=not args.keep_example,
            fmt=fmt,
        )
        log.append(f"初始表: {args.source}")
        log.append(f"样表  : {args.sample} (工作表 {sp.sheet})")
        log.append(f"结构  : {st.mode}, 字段 {len(st.fields)} 个, 记录 {len(st.records)} 条")
        log.append(f"规则  : {len(rules)} 条（自动识别）")
        log.append(f"统计  : {stats}")
        log.append(f"输出  : {info}")
        log.append(f"版本  : {__version__}")
        log.append("结果  : 成功")
        code = 0
    except Exception:
        log.append(traceback.format_exc())
        log.append("结果  : 失败")
        code = 1

    report = os.path.splitext(args.out)[0] + "_报告.txt"
    try:
        with open(report, "w", encoding="utf-8") as f:
            f.write("\n".join(log))
    except Exception:
        pass
    try:
        print("\n".join(log))
    except Exception:
        pass
    return code


def main():
    # 上次自动更新留下的旧程序备份，启动时先清掉
    try:
        from core import updater

        updater.cleanup_old_versions()
    except Exception:
        pass

    if "--version" in sys.argv:
        from core import __version__

        print(__version__)
        sys.exit(0)
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--check-update" in sys.argv:
        idx = sys.argv.index("--check-update")
        sys.exit(cli_check_update(sys.argv[idx + 1:]))
    if "--convert" in sys.argv:
        idx = sys.argv.index("--convert")
        sys.exit(cli_convert(sys.argv[idx + 1:]))

    app = QApplication(sys.argv)
    app.setApplicationName("员工工资申报转换工具")
    icon_path = _resource("app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Microsoft YaHei")
    font.setPointSize(9)
    app.setFont(font)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
