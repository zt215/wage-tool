# -*- coding: utf-8 -*-
"""检查更新 / 下载新版本 / 自动替换并重启。

只用标准库 urllib，不依赖第三方 HTTP 库。

支持两种更新源，地址栏里怎么写都能认：
  1. GitHub 仓库      https://github.com/zt215/wage-tool
     → 走 GitHub Releases API 取最新 release 和里面的 exe，不用维护 version.json
  2. 静态清单          http://你的服务器/update/version.json  （或 GitHub raw / Pages / CDN）
     → 读清单里的 version / url / sha256

地址栏可以写多行，按顺序依次尝试，前面连不上自动试下一个。
网络出口分「直连」和「走系统代理」两种，自动试，哪个通用哪个并记住。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from .version import APP_NAME, __version__, exe_filename, is_newer, parse_version

UA = f"WageToolUpdater/{__version__}"
TIMEOUT_CHECK = 10
TIMEOUT_DOWNLOAD = 120

# 这些状态码通常说明是"代理/网关"的问题，值得换一种方式再试
RETRY_CODES = (407, 502, 503, 504)

_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 不走代理（内网服务器）
_SYSTEM = urllib.request.build_opener()                                  # 走系统代理（公司网络常见）

# 先试哪种；连上后记下来，下次优先用
_MODE_ORDER = ["direct", "system"]


class UpdateError(Exception):
    pass


# --------------------------------------------------------------------------
# 网络出口：直连 / 系统代理，自动切换
# --------------------------------------------------------------------------
def set_preferred_mode(mode: str):
    global _MODE_ORDER
    mode = (mode or "").strip()
    order = [mode] if mode in ("direct", "system") else []
    order += [m for m in ("direct", "system") if m not in order]
    _MODE_ORDER = order


def get_preferred_mode() -> str:
    return _MODE_ORDER[0]


def _open(req, timeout):
    last = None
    for mode in _MODE_ORDER:
        opener = _DIRECT if mode == "direct" else _SYSTEM
        try:
            resp = opener.open(req, timeout=timeout)
            set_preferred_mode(mode)      # 这次通了，记下来
            return resp
        except urllib.error.HTTPError as e:
            if e.code in RETRY_CODES:
                last = e
                continue
            raise                          # 404/403 之类是服务器的事，换方式也没用
        except urllib.error.URLError as e:
            last = e
            continue
    raise last if last else UpdateError("连不上服务器")


def http_open(req, timeout: int = 30):
    """给发布脚本用的统一出口（自动处理直连/代理）。"""
    return _open(req, timeout)


# --------------------------------------------------------------------------
# 地址解析
# --------------------------------------------------------------------------
def split_sources(text: str) -> list:
    """把多行/分号/逗号分隔的地址拆成列表。"""
    if not text:
        return []
    parts = re.split(r"[\s;,、]+", str(text).strip())
    return [p.strip() for p in parts if p.strip()]


_GITHUB_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/"
    r"([^/\s]+)/([^/\s]+?)(?:\.git)?"
    r"(?:/releases(?:/latest)?|/releases/download/[^/\s]+/[^/\s]+)?/?$",
    re.IGNORECASE,
)
_NOT_OWNER = {"orgs", "users", "topics", "search", "features", "about", "pricing",
              "marketplace", "sponsors", "collections", "trending"}


def github_repo(url: str):
    """是 GitHub 仓库地址就返回 (owner, repo)，否则 None。"""
    m = _GITHUB_RE.match((url or "").strip())
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if owner.lower() in _NOT_OWNER or repo.lower() in ("releases", "tags"):
        return None
    return owner, repo


def _quote_url(url: str) -> str:
    """把 URL 里的中文等非 ASCII 字符转成 %XX，否则 urllib 会报编码错误。"""
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, urllib.parse.quote(parts.path),
         parts.query, parts.fragment)
    )


def manifest_url(base_url: str) -> str:
    """把静态清单地址规范成 version.json 的完整地址。"""
    u = (base_url or "").strip()
    if not u:
        raise UpdateError("还没填更新地址")
    if not u.lower().startswith(("http://", "https://")):
        u = "http://" + u
    if u.lower().endswith(".json"):
        return _quote_url(u)
    if not u.endswith("/"):
        u += "/"
    return _quote_url(u + "version.json")


def join_url(base: str, name: str) -> str:
    """相对地址按清单所在目录补全。"""
    if not name:
        return ""
    if name.lower().startswith(("http://", "https://")):
        return _quote_url(name)
    return _quote_url(urllib.parse.urljoin(manifest_url(base), name))


def describe_source(src: str) -> str:
    """给界面看的地址说明。"""
    repo = github_repo(src)
    if repo:
        return f"GitHub Releases（{repo[0]}/{repo[1]}）"
    return "静态清单"


# --------------------------------------------------------------------------
# 取清单
# --------------------------------------------------------------------------
def fetch_json(url: str, timeout: int, what: str = "更新清单") -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with _open(req, timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError(f"{what}不存在（404）\n地址：{url}") from e
        if e.code == 403:
            raise UpdateError(
                f"被拒绝（403），可能是 GitHub 访问次数超限或需要授权\n地址：{url}"
            ) from e
        raise UpdateError(f"服务器返回 {e.code}\n地址：{url}") from e
    except urllib.error.URLError as e:
        raise UpdateError(f"连不上（{e.reason}）") from e
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"读取失败：{e}") from e

    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:
        raise UpdateError(f"返回的不是合法 JSON：{e}") from e
    if not isinstance(data, dict):
        raise UpdateError(f"{what}格式不对，应该是一个 JSON 对象")
    return data


def fetch_manifest(base_url: str, timeout: int = TIMEOUT_CHECK) -> dict:
    """静态清单（version.json）。"""
    url = manifest_url(base_url)
    data = fetch_json(url, timeout, "更新清单")
    if not data.get("version"):
        raise UpdateError("更新清单里缺少 version 字段")
    return data


def fetch_github_release(owner: str, repo: str, timeout: int = TIMEOUT_CHECK) -> dict:
    """GitHub Releases：直接取最新 release，不用维护 version.json。"""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    try:
        data = fetch_json(url, timeout, "GitHub Release")
    except UpdateError as e:
        msg = str(e)
        if "404" in msg:
            raise UpdateError(
                f"仓库 {owner}/{repo} 没有找到已发布的 Release（或仓库是私有的）\n"
                "如果你还没发过版本，请先在 GitHub 上创建 Release 并上传 exe。"
            ) from e
        raise

    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag:
        raise UpdateError("这个 Release 没有 tag 名，无法判断版本")

    assets = data.get("assets") or []
    if not assets:
        raise UpdateError(f"Release {tag} 里没有上传任何文件")

    asset = next(
        (a for a in assets if str(a.get("name", "")).lower().endswith(".exe")),
        assets[0],
    )
    digest = str(asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        digest = digest.split(":", 1)[1]

    return {
        "version": tag.lstrip("vV"),
        "url": asset.get("browser_download_url") or "",
        "filename": asset.get("name") or exe_filename(tag.lstrip("vV")),
        "size": int(asset.get("size") or 0),
        "sha256": digest,
        "notes": str(data.get("body") or ""),
        "force": False,
        "source_kind": "github",
    }


def _fetch_any(src: str, timeout: int) -> dict:
    repo = github_repo(src)
    if repo:
        return fetch_github_release(repo[0], repo[1], timeout)
    return fetch_manifest(src, timeout)


# --------------------------------------------------------------------------
# 检查更新
# --------------------------------------------------------------------------
def check(text: str, current: str = __version__, timeout: int = TIMEOUT_CHECK) -> dict:
    """检查是否有新版。text 可以是一行或多行地址，按顺序试。

    返回 {ok, has_update, current, latest, notes, size, url, filename, sha256, source}
    """
    sources = split_sources(text)
    if not sources:
        raise UpdateError("还没填更新地址")

    problems = []          # [(地址, 原因)]
    for src in sources:
        try:
            data = _fetch_any(src, timeout)
        except UpdateError as e:
            problems.append((src, str(e)))
            continue

        latest = str(data.get("version"))
        if not latest:
            problems.append((src, "清单里没有 version 字段"))
            continue

        url = str(data.get("url") or "")
        if url and not url.lower().startswith(("http://", "https://")):
            url = join_url(src, url)

        return {
            "ok": True,
            "has_update": is_newer(latest, current),
            "current": current,
            "latest": latest,
            "notes": str(data.get("notes") or ""),
            "force": bool(data.get("force")),
            "size": int(data.get("size") or 0),
            "sha256": str(data.get("sha256") or ""),
            "url": url,
            "filename": str(data.get("filename") or exe_filename(latest)),
            "source": src,
            "source_kind": str(data.get("source_kind") or describe_source(src)),
        }

    # 只有一个地址时直接把原因抛出去，别套一层「所有地址都连不上」
    if len(problems) == 1:
        raise UpdateError(problems[0][1])
    raise UpdateError(
        "所有更新地址都连不上：\n\n"
        + "\n\n".join(f"【{src}】\n{e}" for src, e in problems)
    )


# --------------------------------------------------------------------------
# 下载
# --------------------------------------------------------------------------
def download(url: str, dest: str, on_progress=None) -> str:
    """下载到 dest，on_progress(已下载字节, 总字节)。"""
    if not url:
        raise UpdateError("没有拿到下载地址（Release 里没放 exe？）")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/octet-stream",
    })
    try:
        with _open(req, TIMEOUT_DOWNLOAD) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if on_progress:
                    on_progress(got, total)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"下载失败，服务器返回 {e.code}") from e
    except urllib.error.URLError as e:
        raise UpdateError(f"下载失败，连不上（{e.reason}）") from e
    if os.path.getsize(dest) == 0:
        raise UpdateError("下载到的文件是空的")
    return dest


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------
# 替换自身
# --------------------------------------------------------------------------
def current_exe() -> str:
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    return ""


def install_update(new_exe: str, target_exe: str, new_name: str = "", restart: bool = True) -> str:
    """用新下载的 exe 替换正在运行的自己。

    Windows 上运行中的 exe 不能覆盖，但**可以改名**，
    所以：旧的改名成 .old.exe -> 新的挪到位 -> 启动新的。
    下次启动时老的 .old.exe 会被自动清掉。

    new_name 传了新版本的文件名（带版本号）时，程序会以新文件名落地。

    返回新程序的实际路径。
    """
    if not target_exe or not os.path.exists(target_exe):
        raise UpdateError("拿不到当前程序的位置，无法自动替换")
    if not os.path.exists(new_exe):
        raise UpdateError("下载的新版本文件不见了")

    target_dir = os.path.dirname(os.path.abspath(target_exe))
    target_exe = os.path.abspath(target_exe)

    if new_name:
        new_name = os.path.basename(new_name.strip())
        new_path = os.path.join(target_dir, new_name) if new_name else target_exe
    else:
        new_path = target_exe

    old_path = target_exe + ".old.exe"
    try:
        if os.path.exists(old_path):
            os.remove(old_path)
    except Exception:
        pass

    # 1) 运行中的旧程序先改名（这一步 Windows 允许）
    try:
        os.replace(target_exe, old_path)
    except Exception as e:
        raise UpdateError(f"无法替换正在运行的程序（{e}）。请手动替换。") from e

    # 2) 新程序挪到目标名字
    try:
        if os.path.exists(new_path):
            try:
                os.remove(new_path)
            except Exception:
                pass
        shutil.move(new_exe, new_path)
    except Exception as e:
        try:
            os.replace(old_path, target_exe)   # 换回去，别把程序搞没了
        except Exception:
            pass
        raise UpdateError(f"写入新程序失败（{e}）") from e

    if restart:
        start_new(new_path)
    return new_path


def start_new(exe_path: str):
    """把新程序拉起来（脱离当前进程）。"""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | \
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen([exe_path], close_fds=True, **kwargs)
    except Exception:
        try:
            os.startfile(exe_path)  # type: ignore[attr-defined]
        except Exception:
            pass


def cleanup_old_versions():
    """启动时清理上次自动更新剩下的 .old.exe 备份。"""
    exe = current_exe()
    if not exe:
        return
    exe = os.path.abspath(exe)
    folder = os.path.dirname(exe)
    import glob

    targets = {exe + ".old.exe"}
    targets.update(glob.glob(os.path.join(folder, APP_NAME + "*.old.exe")))
    for p in targets:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def download_temp_path() -> str:
    return os.path.join(tempfile.gettempdir(), f"{APP_NAME}_new.exe")
