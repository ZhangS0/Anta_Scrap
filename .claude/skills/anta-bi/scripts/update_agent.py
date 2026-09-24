"""使用端工具更新器：检查上游版本并安全更新已安装的 agent 工具（仅标准库 + git）。

适用对象：按 INIT_PROMPT.md 完成配置的 AI agent 项目（工具装在 <项目根>/.magic/skills/）。
使用端没有 git 仓库（配置后临时克隆已删除），本脚本用「临时浅克隆」通道对比与更新——
这与 INIT_PROMPT 第 1 步是同一条已验证通道。

用法（在 agent 项目根目录下运行）：
  python .magic/skills/anta-bi/scripts/update_agent.py check [--json]  # 只读：本地版本 vs 上游
  python .magic/skills/anta-bi/scripts/update_agent.py apply [--yes]   # 覆盖式更新工具文件

更新范围（白名单，逐文件覆盖）：
  .magic/skills/{anta-bi, hamilton-report, bi-report-build, bi-report-rerun, anta-bi-onboard}
  项目根 AGENTS.md、USAGE.md、版本标记 .magic/skills/anta-bi/VERSION

永不触碰：workspace/（报告任务与已生成产物）、out/、feedback-pending.jsonl、
.mcp.json、凭证；skill 目录里上游已不存在的**你自行添加的文件**（如 onboard
产出的自加报表指引）——保留并列出，是否删除由你决定。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

DEFAULT_REPO = "https://github.com/ZhangS0/Anta_Scrap.git"
SKILL_DIR = Path(__file__).resolve().parents[1]          # .../.magic/skills/anta-bi
VERSION_MARK = SKILL_DIR / "VERSION"
SKILL_NAMES = ("anta-bi", "hamilton-report", "bi-report-build", "bi-report-rerun", "anta-bi-onboard")
ROOT_FILES = ("AGENTS.md", "USAGE.md")


def _git(*args: str, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    # -c http.version=HTTP/1.1：部分网络下 git 默认 HTTP/2 握手会失败（Empty reply），1.1 稳定
    r = subprocess.run(
        ["git", "-c", "http.version=HTTP/1.1", *args], cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {(r.stderr or r.stdout).strip()[:200]}")
    return r


def find_install_root() -> Optional[Path]:
    """从当前目录向上找 agent 项目根（含 .magic/skills/anta-bi 的最近祖先）。"""
    for d in [Path.cwd().resolve(), *Path.cwd().resolve().parents]:
        if (d / ".magic" / "skills" / "anta-bi").is_dir():
            return d
    return None


def local_version() -> str:
    return VERSION_MARK.read_text(encoding="utf-8").strip() if VERSION_MARK.exists() else "unknown"


def _ver_tuple(v: str):
    try:
        return tuple(int(x) for x in v.strip().strip("v").split("."))
    except ValueError:
        return (0,)


def changelog_new_sections(text: str, cur: str) -> str:
    lines = text.splitlines()
    heads = [i for i, ln in enumerate(lines) if re.match(r"^##\s*\[", ln)]
    out: list[str] = []
    for idx, start in enumerate(heads):
        end = heads[idx + 1] if idx + 1 < len(heads) else len(lines)
        m = re.match(r"^##\s*\[([^\]]+)\]", lines[start])
        if m and _ver_tuple(m.group(1)) > _ver_tuple(cur):
            out.extend(lines[start:end])
    return "\n".join(out).strip()


def fetch_upstream(repo: str) -> Path:
    """临时浅克隆上游，返回克隆目录（调用方负责清理）。"""
    tmp = Path(tempfile.mkdtemp(prefix="anta_update_"))
    _git("clone", "--depth", "1", "--quiet", repo, str(tmp / "upstream"))
    return tmp / "upstream"


_IGNORE_PARTS = {"__pycache__"}
_IGNORE_SUFFIX = {".pyc", ".pyo"}


def _ignored(rel: Path) -> bool:
    return any(part in _IGNORE_PARTS for part in rel.parts) or rel.suffix in _IGNORE_SUFFIX


def sync_tree(src: Path, dst: Path) -> tuple[list[str], list[str]]:
    """逐文件覆盖 src→dst（不先删目录）；返回 (覆盖清单, 上游已不存在的保留文件清单)。"""
    copied, kept = [], []
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if _ignored(rel):
            continue
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            shutil.copy2(p, target)
            copied.append(rel.as_posix())
    for p in sorted(dst.rglob("*")):
        rel = p.relative_to(dst)
        if _ignored(rel) or rel.as_posix() == "VERSION":  # VERSION=版本标记，非自加文件
            continue
        if p.is_file() and not (src / rel).exists():
            kept.append(rel.as_posix())
    return copied, kept


def do_check(repo: str, as_json: bool) -> int:
    result: dict = {"local_version": local_version(), "repo": repo}
    tmp_root: Optional[Path] = None
    try:
        tmp_root = fetch_upstream(repo)
        result["remote_version"] = (tmp_root / "VERSION").read_text(encoding="utf-8").strip()
        rc = tmp_root / "CHANGELOG.md"
        if rc.exists():
            result["changelog_excerpt"] = changelog_new_sections(
                rc.read_text(encoding="utf-8"), result["local_version"]
            )
    except RuntimeError as e:
        result["error"] = str(e)
    finally:
        if tmp_root and tmp_root.exists():
            shutil.rmtree(tmp_root.parent, ignore_errors=True)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if "error" in result else 0

    print(f"本地工具版本: {result['local_version']}")
    if "error" in result:
        print(f"⚠ 无法检查上游：{result['error']}")
        return 1
    rv = result["remote_version"]
    print(f"上游最新版本: {rv}")
    if _ver_tuple(rv) <= _ver_tuple(result["local_version"]) and result["local_version"] != "unknown":
        print("✓ 已是最新")
        return 0
    if result["local_version"] == "unknown":
        print("⚠ 未找到本地版本标记（.magic/skills/anta-bi/VERSION）——直接跑一次 apply 建立标记并更新")
    excerpt = result.get("changelog_excerpt", "")
    if excerpt:
        print(f"\n—— CHANGELOG 更新说明 ——\n{excerpt}")
    print("\n确认后执行更新：python .magic/skills/anta-bi/scripts/update_agent.py apply")
    print("（workspace/、out/、你自行添加的 skill 与报表指引不会被触碰）")
    return 0


def do_apply(repo: str, assume_yes: bool) -> int:
    root = find_install_root()
    if not root:
        print("✗ 未找到安装根（向上未发现 .magic/skills/anta-bi）——请在 agent 项目根目录下运行")
        return 1
    tmp_root: Optional[Path] = None
    try:
        tmp_root = fetch_upstream(repo)
    except RuntimeError as e:
        print(f"✗ 无法获取上游：{e}")
        return 1

    try:
        src = tmp_root
        new_version = (src / "VERSION").read_text(encoding="utf-8").strip()
        old_version = local_version()
        if not assume_yes and old_version != "unknown" and _ver_tuple(new_version) <= _ver_tuple(old_version):
            print(f"✓ 本地已是 {old_version}，上游 {new_version}，无需更新")
            return 0

        print(f"更新 {old_version} → {new_version}")
        total_kept: list[str] = []
        for name in SKILL_NAMES:
            _, kept = sync_tree(src / ".claude" / "skills" / name, root / ".magic" / "skills" / name)
            total_kept.extend(f".magic/skills/{name}/{k}" for k in kept)
        for f in ROOT_FILES:
            shutil.copy2(src / "agent_setup" / f, root / f)

        VERSION_MARK.write_text(new_version + "\n", encoding="utf-8")
        print(f"✓ 五个 skill 已更新，AGENTS.md / USAGE.md 已同步，版本标记写入 {new_version}")
        if total_kept:
            print("\n✓ 以下是你自行添加/上游已不存在的文件，已保留（是否删除自行决定）：")
            for f in total_kept:
                print(f"    {f}")
        print("\n✓ 未触碰：workspace/（报告与产物）、out/、feedback-pending.jsonl、.mcp.json、凭证")
        print("  提示：重新加载 skills 后新版本生效（skill 内容为 🟢 无感变更，无需重启任何服务）")
        return 0
    finally:
        shutil.rmtree(tmp_root.parent, ignore_errors=True)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="update_agent", description="使用端 agent 工具版本检查与更新")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="只读：本地版本 vs 上游（可定时跑）")
    c.add_argument("--json", action="store_true")
    c.add_argument("--repo", default=DEFAULT_REPO)
    a = sub.add_parser("apply", help="更新五个 skill + AGENTS.md + USAGE.md（保护性覆盖）")
    a.add_argument("--yes", action="store_true", help="跳过同版本检查直接执行")
    a.add_argument("--repo", default=DEFAULT_REPO)
    args = p.parse_args(argv)
    try:
        return do_check(args.repo, args.json) if args.cmd == "check" else do_apply(args.repo, args.yes)
    except RuntimeError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"✗ 上游缺少预期文件: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
