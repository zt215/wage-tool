# -*- coding: utf-8 -*-
"""生成要上传到服务器的更新包。

做三件事：
  1. 把 dist 里带版本号的 exe 复制到输出目录
  2. 算出 sha256、文件大小，连同版本号一起写成 version.json
  3. 生成一份上传说明

用法：
    python tools/make_package.py                       # 默认输出到桌面「工资工具更新包」
    python tools/make_package.py D:\\out --notes "修复xx"
    python tools/make_package.py --port 8090 --path /update
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

from core.version import APP_NAME, __version__, exe_filename  # noqa: E402


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_exe(explicit: str = "") -> str:
    """找要打包的 exe：优先当前版本那个，其次 dist 里最新的。"""
    if explicit:
        return explicit
    dist = os.path.join(PROJECT, "dist")
    exact = os.path.join(dist, exe_filename(__version__))
    if os.path.exists(exact):
        return exact
    cands = [p for p in glob.glob(os.path.join(dist, f"{APP_NAME}*.exe"))
             if ".old." not in p]
    if not cands:
        return ""
    return max(cands, key=os.path.getmtime)


def main():
    p = argparse.ArgumentParser(description="生成服务器更新包")
    p.add_argument("out", nargs="?", default=os.path.join(os.path.expanduser("~"), "Desktop", "工资工具更新包"),
                   help="输出目录，默认 桌面/工资工具更新包")
    p.add_argument("--exe", default="", help="要打包的 exe（默认自动找 dist 里当前版本的）")
    p.add_argument("--host", default="81.70.149.13", help="服务器地址")
    p.add_argument("--port", default="8090", help="服务器端口")
    p.add_argument("--path", default="/update", help="服务器上的目录")
    p.add_argument("--notes", default="", help="更新说明，用 \\n 分行")
    p.add_argument("--forces", action="store_true", help="标记为强制更新")
    args = p.parse_args()

    src = find_exe(args.exe)
    if not src or not os.path.exists(src):
        print("[错误] 找不到要打包的程序。")
        print("       请先双击「打包exe.bat」生成，或看下 dist 目录里有没有 exe。")
        return 1

    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    # 1) 复制 exe（文件名带版本号）
    name = exe_filename(__version__)
    dest_exe = os.path.join(out, name)
    shutil.copy2(src, dest_exe)

    # 2) 写 version.json
    size = os.path.getsize(dest_exe)
    digest = sha256_of(dest_exe)
    notes = (args.notes or "版本更新").replace("\\n", "\n")
    manifest = {
        "version": __version__,
        "url": name,          # 服务器上放的文件名（和本地同名，带版本号）
        "filename": name,     # 更新到本机后要用的文件名
        "size": size,
        "sha256": digest,
        "notes": notes,
        "force": bool(args.forces),
        "released": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    with open(os.path.join(out, "version.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 3) 上传说明
    base = f"http://{args.host}:{args.port}{args.path.rstrip('/')}"
    readme = f"""上传到服务器的说明
========================================

本地目录：{out}

要上传的文件（两个都要传，放在同一个目录）：
    1. {name}
       （新版本程序，{size / 1024 / 1024:.1f} MB，文件名带版本号）
    2. version.json
       （版本清单，软件靠它判断有没有新版）

服务器上放到这个目录（没有就新建）：
    {args.path}

上传后，软件里「检查更新」的地址填：
    {base}/version.json

（软件里默认已经填好这个地址；IP、端口或目录变了就改一下）

----------------------------------------
关于文件名
----------------------------------------
更新包和更新后的程序都用「{name}」这个名字。
用户更新完，程序会自己换成新版本号的文件名，老的
程序会在下次启动时自动删掉，不用手动清理。

注意：如果用户桌面上有指向旧版本文件的快捷方式，
更新后要重新建一个（指向新版本号那个文件）。

----------------------------------------
version.json 内容
----------------------------------------
{json.dumps(manifest, ensure_ascii=False, indent=2)}

----------------------------------------
下次发新版本怎么做
----------------------------------------
1. 打开 core/version.py，把 __version__ 改成新版本号（比如 {__version__} -> 1.2.0）
2. 双击「打包exe.bat」重新打包（会自动生成带新版本号的 exe）
3. 双击「生成更新包.bat」重新生成本目录的文件
4. 把新的两个文件传到服务器（旧版本的文件可以删掉）
"""
    with open(os.path.join(out, "上传说明.txt"), "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"打包完成：{APP_NAME} v{__version__}")
    print(f"  来源    : {src}")
    print(f"  目录    : {out}")
    print(f"  程序    : {name}  ({size / 1024 / 1024:.1f} MB)")
    print(f"  sha256  : {digest}")
    print(f"  清单    : version.json")
    print(f"  上传到  : {args.path}")
    print(f"  更新地址: {base}/version.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
