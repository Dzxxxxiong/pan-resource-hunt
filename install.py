#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pan-resource-hunt skill 跨平台一键安装器（零依赖，纯标准库）。

自动识别两种源码布局：
  A) 仓库根即 skill     →  <dir>/SKILL.md        （git clone 场景）
  B) 包内 skill/ 子目录 →  <dir>/skill/SKILL.md  （zip 分发场景）

用法：
    python install.py                 # 装到 ~/.workbuddy/skills/pan-resource-hunt
    python install.py --force         # 已存在则直接覆盖（默认先备份）
    python install.py --dry-run       # 只打印将执行的动作
    python install.py --target DIR    # 装到指定目录（项目级部署）
    python install.py --prune         # 顺带清掉目标目录里的 __pycache__
"""
from __future__ import annotations

import argparse
import py_compile
import shutil
import sys
import time
from pathlib import Path

SKILL_NAME = "pan-resource-hunt"
HERE = Path(__file__).resolve().parent

# 这些是"仓库/分发包"层面的文件，不进 skill 目录
EXCLUDE_TOP = {
    "install.py", "build_package.py", "push_to_github.py",
    "DEPLOY.md", "AI_DEPLOY.md",
    "README.md", "LICENSE", ".gitignore", ".gitattributes", ".git",
    ".github", "MANIFEST.txt", "skill",
    "dist", "build", ".venv", "venv",
}
EXCLUDE_ANY = {"__pycache__", ".DS_Store", "Thumbs.db", ".pytest_cache"}


def locate_source() -> Path | None:
    if (HERE / "SKILL.md").is_file():
        return HERE
    if (HERE / "skill" / "SKILL.md").is_file():
        return HERE / "skill"
    return None


def collect(src: Path) -> list[Path]:
    out = []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if rel.parts and rel.parts[0] in EXCLUDE_TOP:
            continue
        if any(part in EXCLUDE_ANY for part in rel.parts):
            continue
        if p.suffix in {".pyc", ".pyo"}:
            continue
        out.append(p)
    return out


def human(p: Path) -> str:
    try:
        return str(p.relative_to(Path.home()))
    except ValueError:
        return str(p)


def run(dst: Path, force: bool, prune: bool) -> int:
    src = locate_source()
    if src is None:
        print(f"[ERROR] 找不到 SKILL.md。已查：\n        {HERE / 'SKILL.md'}\n        {HERE / 'skill' / 'SKILL.md'}")
        print("        请确认克隆/解压完整。")
        return 2

    files = collect(src)
    rels = [f.relative_to(src).as_posix() for f in files]

    required = ["SKILL.md", "scripts/hunt_fast.py", "scripts/hunt_sources.py"]
    missing = [r for r in required if r not in rels]

    print(f"源码布局  : {'仓库根即 skill' if src == HERE else '包内 skill/ 子目录'}")
    print(f"源        : {src}")
    print(f"目标      : {dst}")
    print(f"待装文件  : {len(files)}")
    if missing:
        print(f"[WARN] 缺少关键文件：{', '.join(missing)}（技能可能不完整）")

    if dst.exists() and not force:
        print(f"目标已存在: 将先备份为 {human(dst.with_name(dst.name + '.bak-<时间戳>'))}")

    if dst.exists():
        if force:
            shutil.rmtree(dst)
        else:
            bak = dst.with_name(f"{dst.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            shutil.move(str(dst), str(bak))
            print(f"[OK] 旧版本已备份 → {human(bak)}")

    dst.mkdir(parents=True, exist_ok=True)
    for f in files:
        tgt = dst / f.relative_to(src)
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, tgt)
    print(f"[OK] 已安装 → {dst}")

    if prune:
        for d in dst.rglob("__pycache__"):
            shutil.rmtree(d, ignore_errors=True)
        print("[OK] 已清理 __pycache__")

    bad = []
    pys = sorted(dst.glob("scripts/*.py"))
    for py in pys:
        try:
            py_compile.compile(str(py), doraise=True, cfile=str(py) + ".pyc")
            Path(str(py) + ".pyc").unlink(missing_ok=True)
        except py_compile.PyCompileError as e:
            bad.append((py.name, str(e).strip().splitlines()[-1]))
    if bad:
        print("[WARN] 语法检查未通过：")
        for n, err in bad:
            print(f"       {n}: {err}")
    else:
        print(f"[OK] 脚本语法自检通过（{len(pys)} 个）")

    print("\n[OK] 安装完成。验证：")
    print(f'     python "{dst / "scripts" / "hunt_fast.py"}" --help')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="pan-resource-hunt skill 安装器")
    ap.add_argument("--target", help="目标 skill 目录（默认 ~/.workbuddy/skills/pan-resource-hunt）")
    ap.add_argument("--force", action="store_true", help="已存在时直接覆盖，不备份")
    ap.add_argument("--dry-run", action="store_true", help="只展示将执行的动作")
    ap.add_argument("--prune", action="store_true", help="安装后清理 __pycache__")
    a = ap.parse_args()

    dst = Path(a.target).expanduser().resolve() if a.target else (
        Path.home() / ".workbuddy" / "skills" / SKILL_NAME
    )

    if a.dry_run:
        src = locate_source()
        if src is None:
            print("[ERROR] 找不到 SKILL.md，无法预览。")
            return 2
        files = collect(src)
        print(f"源        : {src}")
        print(f"目标      : {dst}")
        print(f"待装文件  : {len(files)}")
        for f in files:
            print("  " + f.relative_to(src).as_posix())
        return 0

    return run(dst, a.force, a.prune)


if __name__ == "__main__":
    sys.exit(main())
