"""项目自更新机制：对比 GitHub 上游版本并安全快进更新。

用法：
  python scripts/update.py check [--json]     # 只读检查（可定时跑，不碰工作区）
  python scripts/update.py apply [--yes] [--stash] [--force-diverged]

安全模型：
- check 只做 git fetch（更新远程跟踪引用），不修改工作区任何文件
- apply 仅快进（git merge --ff-only），绝不合流；工作区脏、本地有未推送定制
  提交时默认拒绝并逐项列出
- 用户本地状态不在 git 管理内，任何更新都不触碰：已生成报表（workspace/**/history/）、
  feedback/、.mcp.json、.env、agent_setup/INIT_PROMPT.md、~/.anta_scrap 凭证、
  untracked 的自加 skill/报表指引/模板

仅标准库 + git 子进程。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "VERSION"

# 托管区内允许用户自行添加内容的位置（untracked 扫描用，只为了「列出来让你放心」）
MANAGED_UNTRACKED_DIRS = (".claude/skills", "templates", "docs")

FETCH_REF = "origin/main"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {(r.stderr or r.stdout).strip()}")
    return r


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def local_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "unknown"


def remote_version() -> Optional[str]:
    """上游 VERSION 内容；上游尚未上线版本机制时返回 None。"""
    r = _git("show", f"{FETCH_REF}:VERSION", check=False)
    return r.stdout.strip() if r.returncode == 0 else None


def _ver_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().strip("v").split("."))
    except ValueError:
        return (0,)


def _is_newer(a: str, b: str) -> bool:
    """a > b（宽容解析，非 semver 视为更新）。"""
    try:
        return _ver_tuple(a) > _ver_tuple(b)
    except TypeError:
        return True


def ahead_commits() -> list[str]:
    return _lines(_git("log", f"{FETCH_REF}..HEAD", "--oneline").stdout)


def behind_count() -> int:
    return int((_lines(_git("rev-list", "--count", f"HEAD..{FETCH_REF}").stdout) or ["0"])[0])


def _porcelain_paths(extra_args: list[str]) -> list[str]:
    """git status --porcelain 输出取路径列（固定列解析，不能 strip 行首——状态列占位）。"""
    out = _git("-c", "core.quotepath=false", "status", "--porcelain", *extra_args).stdout
    paths = []
    for ln in out.splitlines():
        if len(ln) <= 3:
            continue
        path = ln[3:].strip()
        if " -> " in path:  # 重命名对取新路径
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def dirty_tracked_files() -> list[str]:
    """已修改/已删除的跟踪文件（工作区脏 = 会阻断快进更新）。"""
    return _porcelain_paths(["--untracked-files=no"])


def untracked_managed_files() -> list[str]:
    """托管目录下用户自行添加的 untracked 文件（git 不碰，列出来让用户放心）。"""
    out = _git(
        "-c", "core.quotepath=false", "status",
        "--porcelain", "--untracked-files=all", "--", *MANAGED_UNTRACKED_DIRS,
    ).stdout
    return [ln[3:].strip() for ln in out.splitlines() if ln.startswith("??") and len(ln) > 3]


def changed_files_between(rev_a: str, rev_b: str) -> list[str]:
    return _lines(_git("diff", "--name-only", f"{rev_a}..{rev_b}").stdout)


def bucket(path: str) -> str:
    """影响范围分桶：red=需重启 MCP / yellow=需用户动作 / green=无感。"""
    p = path.replace("\\", "/")
    if p.startswith("anta_scrap/"):
        return "red"
    if p in ("pyproject.toml", "start_anta_mcp.bat") or p.startswith("requirements"):
        return "yellow"
    return "green"


BUCKET_LABEL = {
    "red": "🔴 需重启 MCP 服务端（anta_scrap 服务端代码）",
    "yellow": "🟡 需用户动作（依赖/部署脚本变化，重跑 pip install -e . 或重启时留意）",
    "green": "🟢 无感（skills 指引/文档/模板，更新即生效）",
}


def changelog_new_sections(remote_changelog: str, cur_version: str) -> str:
    """取远程 CHANGELOG 中比 cur_version 新的全部段落。"""
    lines = remote_changelog.splitlines()
    heads = [i for i, ln in enumerate(lines) if re.match(r"^##\s*\[", ln)]
    out: list[str] = []
    for idx, start in enumerate(heads):
        end = heads[idx + 1] if idx + 1 < len(heads) else len(lines)
        m = re.match(r"^##\s*\[([^\]]+)\]", lines[start])
        if not m:
            continue
        if _ver_tuple(m.group(1)) > _ver_tuple(cur_version):
            out.extend(lines[start:end])
    return "\n".join(out).strip()


# ---------- check ----------


def cmd_check(args: argparse.Namespace) -> int:
    result: dict = {"local_version": local_version(), "network_ok": True}

    fetch = _git("fetch", "origin", "main", check=False)
    if fetch.returncode != 0:
        result["network_ok"] = False
        result["error"] = f"无法访问 GitHub 上游（{fetch.stderr.strip()[:120]}）——检查网络后重试"
    else:
        result["remote_version"] = remote_version()
        result["ahead"] = len(ahead_commits())
        result["behind"] = behind_count()
        result["local_commits"] = ahead_commits()
        result["dirty_files"] = dirty_tracked_files()
        result["untracked_managed"] = untracked_managed_files()
        if result["behind"] > 0:
            files = changed_files_between("HEAD", FETCH_REF)
            impact: dict[str, list[str]] = {"red": [], "yellow": [], "green": []}
            for f in files:
                impact[bucket(f)].append(f)
            result["impact"] = impact
            rc = _git("show", f"{FETCH_REF}:CHANGELOG.md", check=False)
            if rc.returncode == 0:
                result["changelog_excerpt"] = changelog_new_sections(rc.stdout, result["local_version"])

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("network_ok") else 1

    lv = result["local_version"]
    print(f"本地版本: {lv}")
    if not result.get("network_ok"):
        print(f"⚠ {result['error']}")
        return 1
    rv = result.get("remote_version")
    print(f"上游版本: {rv if rv else '（上游尚未上线路本机制）'}")
    ahead, behind = result["ahead"], result["behind"]

    if ahead:
        print(f"\n⚠ 本地有 {ahead} 个未推送定制提交（更新机制不会丢弃它们，但 apply 默认拒绝）：")
        for c in result["local_commits"]:
            print(f"    {c}")
        print("    处置：把定制推回上游（git push）合并，或确认保留后用 apply --force-diverged")
    if result["dirty_files"]:
        print("\n⚠ 本地已修改的跟踪文件（会阻断更新，先提交或 apply --stash）：")
        for f in result["dirty_files"]:
            print(f"    {f}")
    if result["untracked_managed"]:
        print("\n✓ 你自行添加的内容（不受更新影响，更新后原样保留）：")
        for f in result["untracked_managed"]:
            print(f"    {f}")
    print("\n✓ 本地数据安全区（更新永不触碰）：已生成报表 workspace/**/history/、feedback/、"
          ".mcp.json、.env、INIT_PROMPT.md、~/.anta_scrap 凭证")

    if behind == 0:
        extra = f"（本地领先 {ahead} 个定制提交，无上游更新）" if ahead else "（与上游一致）"
        print(f"\n✓ 已是最新{extra}")
        return 0

    print(f"\n⬇ 上游有 {behind} 个新提交，影响范围：")
    for key in ("red", "yellow", "green"):
        files = result.get("impact", {}).get(key) or []
        if files:
            print(f"  {BUCKET_LABEL[key]}（{len(files)} 个文件）")
            for f in files[:20]:
                print(f"      {f}")
            if len(files) > 20:
                print(f"      …等共 {len(files)} 个")
    excerpt = result.get("changelog_excerpt")
    if excerpt:
        print(f"\n—— CHANGELOG 更新说明 ——\n{excerpt}")
    print("\n确认后执行更新：python scripts/update.py apply")
    return 0


# ---------- apply ----------


def cmd_apply(args: argparse.Namespace) -> int:
    fetch = _git("fetch", "origin", "main", check=False)
    if fetch.returncode != 0:
        print(f"✗ 无法访问 GitHub 上游（{fetch.stderr.strip()[:120]}），未做任何修改")
        return 1

    behind = behind_count()
    ahead = ahead_commits()
    if behind == 0:
        print(f"✓ 已是最新{f'（本地保留 {len(ahead)} 个定制提交）' if ahead else ''}，无需更新")
        return 0

    # 安全门 1：本地定制提交
    if ahead and not args.force_diverged:
        print(f"✗ 本地有 {len(ahead)} 个未推送定制提交，快进更新会埋掉分叉历史。处置：")
        for c in ahead:
            print(f"    {c}")
        print("  ① 把定制推回上游合并（推荐：git push）后重试；")
        print("  ② 确认放弃分叉历史：apply --force-diverged（提交仍在 reflog，可找回）")
        return 1

    # 安全门 2：工作区脏
    dirty = dirty_tracked_files()
    stashed = False
    if dirty:
        if not args.stash:
            print("✗ 本地以下跟踪文件有未提交修改（会阻断快进更新）：")
            for f in dirty:
                print(f"    {f}")
            print("  处置：自己提交（git commit），或 apply --stash 让机制暂存并在更新后恢复")
            return 1
        _git("stash", "push", "-m", "update.py auto-stash (tracked only)")
        stashed = True
        print(f"… 已暂存 {len(dirty)} 个本地修改文件（更新后自动恢复）")

    pre_head = _git("rev-parse", "HEAD").stdout.strip()
    try:
        _git("merge", "--ff-only", FETCH_REF)
    except RuntimeError as e:
        if stashed:
            _git("stash", "pop", check=False)
        print(f"✗ 快进更新失败，已中止：{e}")
        return 1

    new_v = local_version()
    print(f"✓ 已更新到 {new_v}（HEAD {pre_head[:8]} → {_git('rev-parse', 'HEAD').stdout.strip()[:8]}）")

    if stashed:
        pop = _git("stash", "pop", check=False)
        if pop.returncode != 0:
            print("⚠ 暂存的本地修改恢复冲突：git stash list 查看，手工处理")
        else:
            print("✓ 本地修改已恢复")

    # 后续动作提示（按影响范围）
    pulled = changed_files_between("ORIG_HEAD", "HEAD")
    if any(bucket(f) == "red" for f in pulled):
        print("🔴 本次更新含服务端代码变更：请重启 MCP 服务端（start_anta_mcp.bat / 对应服务管理）后生效")
        key_err = ""
        try:
            from anta_scrap.mcp_server import _api_key_config_error  # noqa: 仅供提示复用
            import os
            key_err = _api_key_config_error(os.environ.get("ANTA_MCP_API_KEY", "").strip()) or ""
        except Exception:
            pass
        if key_err:
            print(f"🔴 重启前先处理 key 配置：{key_err}")
    if any(bucket(f) == "yellow" for f in pulled):
        print("🟡 依赖/部署脚本有变化：建议重跑 pip install -e .（项目 .venv）")
    print("✓ 本地数据安全区未触碰：已生成报表、feedback、.mcp.json、凭证、自行添加的 skill/指引")

    # 冒烟自检：新代码可导入
    smoke = subprocess.run(
        [sys.executable, "-c", "import anta_scrap; import anta_scrap.mcp_server"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if smoke.returncode == 0:
        print("✓ 冒烟自检通过（anta_scrap 可导入）")
    else:
        print(f"⚠ 冒烟自检失败（更新本身已完成）：{(smoke.stderr or '').strip()[:200]}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="update.py", description="项目版本检查与快进更新（GitHub 上游：origin/main）"
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="只读检查：版本对比 + 分叉检测 + 影响范围（可定时跑）")
    c.add_argument("--json", action="store_true", help="机器可读输出（定时任务判 behind 字段）")
    a = sub.add_parser("apply", help="快进更新到 origin/main（本地数据安全区零触碰）")
    a.add_argument("--yes", action="store_true", help="跳过交互确认（脚本化场景用；确认逻辑由调用方负责）")
    a.add_argument("--stash", action="store_true", help="本地脏文件自动 stash 并在更新后恢复（仅跟踪文件）")
    a.add_argument("--force-diverged", action="store_true", help="有本地定制提交时仍强制快进（提交仍在 reflog 可找回）")
    args = p.parse_args(argv)
    try:
        return cmd_check(args) if args.cmd == "check" else cmd_apply(args)
    except RuntimeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
