# -*- coding: utf-8 -*-
"""一键把当前版本发布到 GitHub Releases。

做了这些事：
  1. 找到 dist 里当前版本的 exe
  2. 在 GitHub 仓库上创建（或复用）tag 为 v<版本号> 的 Release
  3. 把 exe 作为 Release 附件上传
  4. 回读校验，确认软件端能看到

软件端不需要 version.json —— 它直接调 GitHub Releases API 读最新 release，
所以以后发新版只要跑这个脚本就行。

用法：
    python tools/publish_github.py                        # 用默认仓库
    python tools/publish_github.py --notes "修复了xx"
    python tools/publish_github.py --token ghp_xxx        # 临时指定 token
    python tools/publish_github.py --clear-token          # 忘掉本机保存的 token
    python tools/publish_github.py --repo zt215/wage-tool

Token 从哪儿来（按顺序找）：
    1. 命令行 --token
    2. 环境变量 GITHUB_TOKEN
    3. tools/github_token.txt（第一次运行会提示你粘贴并保存）

Token 需要什么权限：fine-grained token 勾 Contents: Read and write；
或者 classic token 勾 repo。只存在本机，不会上传（已在 .gitignore 里）。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

from core import updater                                    # noqa: E402
from core.version import APP_NAME, __version__, exe_filename  # noqa: E402

TOKEN_FILE = os.path.join(HERE, "github_token.txt")
API = "https://api.github.com"
UPLOAD = "https://uploads.github.com"
DEFAULT_REPO = "zt215/wage-tool"
UA = f"WageToolPublisher/{__version__}"

TOKEN_PREFIXES = ("ghp_", "github_pat_", "gho_", "ghs_", "ghu_")


class AuthError(Exception):
    """token 无效 / 权限不够。"""


class PublishError(Exception):
    """其它发布错误。"""


# --------------------------------------------------------------------------
# Token 处理
# --------------------------------------------------------------------------
def check_token_shape(tok: str):
    """先做本地体检，明显不像 token 的直接打回，别存进去。"""
    t = (tok or "").strip()
    if not t:
        return False, "没有输入内容"
    if "://" in t or "github.com/" in t.lower() or t.lower().startswith("www."):
        return False, "这看起来是**仓库网址**，不是 Token。Token 是软件用来登录 GitHub 的钥匙。"
    if any(ch.isspace() for ch in t):
        return False, "Token 里不能有空格或换行，可能粘贴时多带了字符"
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", t):
        return False, "Token 只由字母、数字、下划线组成，可能粘贴错了"
    if len(t) < 20:
        return False, f"长度只有 {len(t)}，太短了，不像 Token（一般是 40 或 90 多位）"
    return True, ""


def prompt_token() -> str:
    print()
    print("=" * 62)
    print(" 需要一个 GitHub Token —— 注意：不是仓库网址！")
    print("=" * 62)
    print()
    print(" Token 长这样（一长串乱码）：")
    print("   ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789      <- 经典版")
    print("   github_pat_11ABCDEFG0abcdefg_xxxxxx...        <- 细粒度版")
    print()
    print(" 仓库网址长这样（填这个会被拒绝）：")
    print("   https://github.com/zt215/wage-tool")
    print()
    print("-" * 62)
    print(" 【方法一】经典 Token，3 步搞定（推荐）")
    print("-" * 62)
    print("   1. 浏览器打开： https://github.com/settings/tokens/new")
    print("   2. Note 随便填个名字，比如  wage-tool")
    print("      Expiration 选个有效期（建议 90 天；嫌麻烦可以选 No expiration）")
    print("      下面权限列表里，勾上第一项  repo  （勾上后子项会自动全选）")
    print("   3. 拉到页面最底下，点绿色的  Generate token")
    print("      页面上会出现一串 ghp_ 开头的字符 —— 复制它")
    print()
    print("   ⚠ 这串字符只在生成时显示一次，关掉页面就再也看不到了，")
    print("     所以务必立刻复制。丢了就重新生成一个。")
    print()
    print("-" * 62)
    print(" 【方法二】细粒度 Token（更安全，步骤多一点）")
    print("-" * 62)
    print("   1. 浏览器打开： https://github.com/settings/personal-access-tokens/new")
    print("   2. Token name 填  wage-tool，Expiration 选个有效期")
    print("   3. Repository access 选  Only select repositories")
    print("      然后在下面勾上  wage-tool")
    print("   4. Repository permissions 里找到  Contents ，改成  Read and write")
    print("   5. 点  Generate token ，复制那串 github_pat_ 开头的字符")
    print()
    print("-" * 62)
    print(" 拿到的 Token 只保存在本机 tools\\github_token.txt，不会上传到任何地方。")
    print(" 想换一个：双击「发布到GitHub.bat clear-token」先清掉旧的。")
    print("-" * 62)
    for attempt in range(3):
        try:
            raw = input("请粘贴 Token（直接回车取消）：").strip()
        except (EOFError, KeyboardInterrupt):
            return ""
        if not raw:
            return ""
        ok, why = check_token_shape(raw)
        if ok:
            return raw
        print(f"  ✗ {why}")
        print("    再试一次，或直接回车取消。")
    return ""


def read_saved_token() -> str:
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def save_token(tok: str):
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(tok)
        print(f"  （已保存到 {TOKEN_FILE}，下次不用再输）")
    except Exception:
        pass


def clear_token_file():
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
            print(f"  （已删除本机保存的 Token：{TOKEN_FILE}）")
    except Exception:
        pass


def get_token(arg_token: str = "") -> str:
    """拿到一个本地体检合格的 token。"""
    tok = (arg_token or os.environ.get("GITHUB_TOKEN") or "").strip()
    if tok:
        ok, why = check_token_shape(tok)
        if not ok:
            raise PublishError(f"传入的 token 不对：{why}")
        return tok

    saved = read_saved_token()
    if saved:
        ok, why = check_token_shape(saved)
        if ok:
            return saved
        print(f"[提示] 本机保存的 Token 有问题：{why}")
        print(f"       内容开头是：{saved[:20]}…")
        clear_token_file()

    tok = prompt_token()
    if not tok:
        return ""
    save_token(tok)
    return tok


# --------------------------------------------------------------------------
# GitHub API
# --------------------------------------------------------------------------
def api_request(method: str, url: str, token: str, body=None, timeout: int = 60):
    data = None
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with updater.http_open(req, timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
        except Exception:
            pass
        if e.code == 401:
            raise AuthError(f"Token 无效或已过期（401 {detail}）")
        if e.code == 403:
            raise AuthError(
                f"权限不够或访问超限（403 {detail}）\n"
                "      Token 需要 Contents = Read and write（fine-grained）"
                "或 repo（classic）"
            )
        if e.code == 404:
            raise PublishError(
                "仓库读不到（404）。检查仓库名对不对，"
                "以及 Token 有没有勾选这个仓库的访问权限。"
            )
        raise PublishError(f"GitHub 返回 {e.code}：{detail or '未知错误'}")
    except urllib.error.URLError as e:
        raise PublishError(f"连不上 GitHub：{e.reason}")
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise PublishError(f"GitHub 返回的内容看不懂：{e}")


def verify_token(token: str) -> str:
    """验证 token 本身是否有效，返回用户名。"""
    me = api_request("GET", f"{API}/user", token, timeout=20)
    return me.get("login") or "?"


def upload_asset(owner: str, repo: str, release_id: int, path: str, token: str):
    name = os.path.basename(path)
    size = os.path.getsize(path)
    url = (f"{UPLOAD}/repos/{owner}/{repo}/releases/{release_id}"
           f"/assets?name={urllib.parse.quote(name)}")
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(size),
    }
    print(f"  正在上传 {name}（{size / 1024 / 1024:.1f} MB），大文件要等一会儿…")
    with open(path, "rb") as f:
        req = urllib.request.Request(url, data=f, headers=headers, method="POST")
        try:
            with updater.http_open(req, 900) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8", "replace")).get("message", "")
            except Exception:
                pass
            raise PublishError(f"上传附件出错：{e.code} {detail}")


def find_exe() -> str:
    dist = os.path.join(PROJECT, "dist")
    exact = os.path.join(dist, exe_filename())
    if os.path.exists(exact):
        return exact
    cands = [p for p in glob.glob(os.path.join(dist, f"{APP_NAME}*.exe"))
             if ".old." not in p and not p.endswith(".new")]
    if not cands:
        return ""
    return max(cands, key=os.path.getmtime)


# --------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="发布到 GitHub Releases")
    p.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/仓库名，默认 {DEFAULT_REPO}")
    p.add_argument("--exe", default="", help="要发布的 exe（默认找 dist 里当前版本的）")
    p.add_argument("--token", default="", help="GitHub token（不填则从环境变量或本地文件读）")
    p.add_argument("--notes", default="", help="更新说明，用 \\n 分行")
    p.add_argument("--notes-file", default="", help="从文件读更新说明")
    p.add_argument("--draft", action="store_true", help="发成草稿（不对外可见）")
    p.add_argument("--prerelease", action="store_true", help="标记为预发布")
    p.add_argument("--clear-token", action="store_true", help="删掉本机保存的 token 后退出")
    args = p.parse_args()

    if args.clear_token:
        clear_token_file()
        return 0

    if "/" not in args.repo:
        raise SystemExit("[失败] --repo 要写成 owner/仓库名，例如 zt215/wage-tool")
    owner, repo = (x.strip() for x in args.repo.split("/", 1))

    exe = args.exe or find_exe()
    if not exe or not os.path.exists(exe):
        raise SystemExit(
            "[失败] 没找到要发布的 exe。\n"
            "       先双击「打包exe.bat」生成，或用 --exe 指定路径。"
        )

    notes = args.notes.replace("\\n", "\n")
    if args.notes_file and os.path.exists(args.notes_file):
        with open(args.notes_file, "r", encoding="utf-8") as f:
            notes = f.read().strip()
    if not notes:
        notes = f"{APP_NAME} v{__version__}"

    token = get_token(args.token)
    if not token:
        raise SystemExit("[已取消] 没有 Token。")

    tag = f"v{__version__}"
    print()
    print(f"仓库    : {owner}/{repo}")
    print(f"版本    : {__version__}（tag {tag}）")
    print(f"程序    : {os.path.basename(exe)}")
    print()

    # 1) 验证 token（失效就现场换一个）
    print("[1/4] 验证 Token…")
    for attempt in range(3):
        try:
            login = verify_token(token)
            print(f"      OK：已登录为 {login}")
            break
        except AuthError as e:
            print(f"      ✗ {e}")
            clear_token_file()
            if attempt == 2:
                raise SystemExit("[失败] Token 连续验证不通过，先确认 Token 有没有复制错。")
            token = prompt_token()
            if not token:
                raise SystemExit("[已取消] 没有有效 Token。")
            save_token(token)
    else:
        raise SystemExit("[失败] 无法验证 Token。")

    # 2) 确认仓库可写
    print("[2/4] 检查仓库权限…")
    repo_info = api_request("GET", f"{API}/repos/{owner}/{repo}", token)
    if repo_info.get("private"):
        print("      ⚠ 这个仓库是私有的。软件端不带 Token 读不到 Release，"
              "请到仓库 Settings 把可见性改成 Public。")
    else:
        print(f"      OK：{repo_info.get('full_name')}（公开）")

    # 3) 建 release（已存在就复用）
    print(f"[3/4] 创建/复用 Release {tag} …")
    release = None
    try:
        release = api_request(
            "GET", f"{API}/repos/{owner}/{repo}/releases/tags/{tag}", token)
        print(f"      已存在，直接往里面传附件")
    except PublishError as e:
        if "404" not in str(e):
            raise
    if not release:
        release = api_request("POST", f"{API}/repos/{owner}/{repo}/releases", token, body={
            "tag_name": tag,
            "name": f"{APP_NAME} v{__version__}",
            "body": notes,
            "draft": bool(args.draft),
            "prerelease": bool(args.prerelease),
        })
        print(f"      已创建：{release.get('html_url')}")
    release_id = release["id"]

    # 4) 传附件（同名的先删掉，保证覆盖）
    print("[4/4] 上传并校验…")
    for a in (release.get("assets") or []):
        if a.get("name") == os.path.basename(exe):
            print(f"      同名附件已存在，先删除旧的（{a['name']}）")
            api_request("DELETE",
                        f"{API}/repos/{owner}/{repo}/releases/assets/{a['id']}", token)
    asset = upload_asset(owner, repo, release_id, exe, token)
    print(f"      上传完成：{asset.get('name')}"
          f"（{asset.get('size', 0) / 1024 / 1024:.1f} MB）")

    # GitHub 网页上传历史上会把中文附件名截断（员工..._v1.2.0.exe -> _v1.2.0.exe），
    # 上传完检查一下，被改了就用 API 改回来。
    want = os.path.basename(exe)
    got = str(asset.get("name") or "")
    if got != want:
        print(f"      ⚠ 附件名被截断成了 {got!r}，正在改回 {want!r} …")
        try:
            asset = api_request(
                "PATCH",
                f"{API}/repos/{owner}/{repo}/releases/assets/{asset['id']}",
                token, body={"name": want},
            )
            print(f"      已修正为：{asset.get('name')}")
        except Exception as e:
            print(f"      ⚠ 改名失败（不影响软件更新，软件只看 tag）：{e}")

    try:
        info = updater.check(f"https://github.com/{owner}/{repo}", current="0.0.0")
        same = info["latest"] == __version__
        print(f"      软件端看到：{info['latest']}　文件：{info['filename']}")
        print(f"      {'✔ 一致，可以用了' if same else '⚠ 版本对不上，检查一下 tag'}")
    except Exception as e:
        print(f"      ⚠ 回读校验失败（刚发布可能要等几秒）：{e}")

    print()
    print("=" * 60)
    print(f"发布完成：{release.get('html_url')}")
    print(f"软件端更新地址：https://github.com/{owner}/{repo}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (PublishError, AuthError) as e:
        print(f"\n[失败] {e}")
        sys.exit(1)
