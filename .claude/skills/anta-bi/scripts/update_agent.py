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

数据保护（三层）：
1. **永不触碰**：workspace/（报告任务与已生成产物）、out/、feedback-pending.jsonl、
   .mcp.json、凭证；skill 目录里上游已不存在的**你自行添加的文件**（如 onboard
   产出的自加报表指引）——保留并列出，是否删除由你决定。
2. **本地修改过的分发文件，覆盖前自动备份**（需要基线，见下）：备份到
   .magic/update-backup/<旧版本>_<时间戳>/，并在输出中列出，供你把改动合并回新文件。
3. **基线快照** .magic/update-baseline.json：每次 apply 后记录全部安装文件的 sha256；
   下次 apply 时本地 hash ≠ 基线 = 你改过该文件 → 触发备份。
   首次跑 apply（无基线）不做修改检测，只建立基线——存量实例的第一次更新前，
   请自行确认没改过 SKILL.md 等分发文件（自加报表指引是新增文件，不受影响）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
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

BASELINE_FILE_NAME = ".magic/update-baseline.json"
BACKUP_DIR_NAME = ".magic/update-backup"

_IGNORE_PARTS = {"__pycache__"}
_IGNORE_SUFFIX = {".pyc", ".pyo"}


def _git(*args: str, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    # -c http.version=HTTP/1.1：部分网络下 git 默认 HTTP/2 握手会失败（Empty reply），1.1 稳定
    r = subprocess.run(
        ["git", "-c", "http.version=HTTP/1.1", *args], cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {(r.stderr or r.stdout).strip()[:200]}")
    return r


def _ignored(rel: Path) -> bool:
    return any(part in _IGNORE_PARTS for part in rel.parts) or rel.suffix in _IGNORE_SUFFIX


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


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


def _target_pairs(src: Path, root: Path) -> list[tuple[Path, Path]]:
    """(上游源文件 → 安装目标文件) 全量对；含五 skill 树与两个根文件。"""
    pairs: list[tuple[Path, Path]] = []
    for name in SKILL_NAMES:
        sdir = src / ".claude" / "skills" / name
        for p in sorted(sdir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(sdir)
            if _ignored(rel):
                continue
            pairs.append((p, root / ".magic" / "skills" / name / rel))
    for f in ROOT_FILES:
        pairs.append((src / "agent_setup" / f, root / f))
    return pairs


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
    print("（workspace/、out/、你自行添加的 skill 与报表指引不会被触碰；")
    print("  你修改过的分发文件会在覆盖前自动备份到 .magic/update-backup/）")
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
        new_version = (tmp_root / "VERSION").read_text(encoding="utf-8").strip()
        old_version = local_version()
        if not assume_yes and old_version != "unknown" and _ver_tuple(new_version) <= _ver_tuple(old_version):
            print(f"✓ 本地已是 {old_version}，上游 {new_version}，无需更新")
            return 0

        print(f"更新 {old_version} → {new_version}")
        baseline_path = root / BASELINE_FILE_NAME
        baseline: Optional[dict] = None
        if baseline_path.exists():
            try:
                baseline = json.loads(baseline_path.read_text(encoding="utf-8")).get("files")
                if not isinstance(baseline, dict):
                    baseline = None
            except json.JSONDecodeError:
                baseline = None
        backup_dir: Optional[Path] = None
        if baseline is not None:
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_dir = root / BACKUP_DIR_NAME / f"{old_version}_{stamp}"

        pairs = _target_pairs(tmp_root, root)
        backed_up: list[str] = []
        for s, d in pairs:
            if baseline is not None and backup_dir is not None:
                key = d.relative_to(root).as_posix()
                recorded = baseline.get(key)
                if recorded and d.exists() and _sha256(d) != recorded:
                    bdest = backup_dir / key
                    bdest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(d, bdest)
                    backed_up.append(key)
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)

        # kept：skill 目录里上游已不存在的自加文件（不含版本标记/缓存）
        total_kept: list[str] = []
        for name in SKILL_NAMES:
            src_skill = tmp_root / ".claude" / "skills" / name
            dst_skill = root / ".magic" / "skills" / name
            for p in sorted(dst_skill.rglob("*")):
                rel = p.relative_to(dst_skill)
                if not p.is_file() or _ignored(rel) or rel.as_posix() == "VERSION":
                    continue
                if not (src_skill / rel).exists():
                    total_kept.append(f".magic/skills/{name}/{rel.as_posix()}")

        VERSION_MARK.write_text(new_version + "\n", encoding="utf-8")

        # 写新基线：本次安装后的全量 hash（下次 apply 据此识别用户本地改动）
        baseline_files = {d.relative_to(root).as_posix(): _sha256(d) for _, d in pairs}
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps({"version": new_version, "files": baseline_files}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

        print(f"✓ 五个 skill 已更新，AGENTS.md / USAGE.md 已同步，版本标记写入 {new_version}")
        if backed_up:
            print(f"\n⚠ 以下 {len(backed_up)} 个文件你本地修改过，已被上游新版覆盖；")
            print(f"  原副本已备份，请把你的改动手动合并回新文件：")
            for k in backed_up:
                print(f"    {k}  →  {backup_dir.relative_to(root).as_posix()}/{k}")
        if baseline is None:
            print("\nℹ 已建立基线快照（.magic/update-baseline.json）：此后你对工具文件的本地修改")
            print("  会在更新前自动备份（本次之前已做的本地修改无法区分，未备份）")
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
    a = sub.add_parser("apply", help="更新五个 skill + AGENTS.md + USAGE.md（保护性覆盖 + 修改备份）")
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
