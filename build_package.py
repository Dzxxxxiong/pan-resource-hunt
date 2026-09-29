#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从本仓库打包一个离线分发 zip（零依赖，纯标准库）。

用途：目标机不能访问 GitHub 时，拷 zip 过去解压 → `python install.py`。

用法：
    python build_package.py
    python build_package.py --out dist/pan-resource-hunt-skill.zip

产物结构：
    pan-resource-hunt-skill.zip
      ├── install.py
      ├── DEPLOY.md
      ├── README.md
      ├── LICENSE
      ├── MANIFEST.txt     文件清单 + SHA256
      └── skill/           skill 本体（SKILL.md + scripts/ + references/）
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def collect_skill(src: Path) -> list[Path]:
    """复用 install.py 的排除规则，保证 zip 内容与安装结果一致。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_prh_install", src / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.collect(src)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build(src: Path, out: Path) -> int:
    if not (src / "SKILL.md").is_file():
        print(f"[ERROR] 不是 skill 仓库根（缺 SKILL.md）：{src}")
        return 2

    files = collect_skill(src)
    if not files:
        print("[ERROR] 未收集到任何 skill 文件。")
        return 2

    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "package      : pan-resource-hunt skill",
        f"built_at_utc : {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}",
        f"source       : {src}",
        f"file_count   : {len(files)}",
        "",
        f"{'SHA256':<64}  SIZE  PATH",
    ]
    for p in files:
        lines.append(f"{sha256(p):<64}  {p.stat().st_size:>5}  {p.relative_to(src).as_posix()}")
    manifest = "\n".join(lines) + "\n"

    extras = [f for f in ("install.py", "DEPLOY.md", "README.md", "LICENSE") if (src / f).is_file()]

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in extras:
            z.write(src / f, f)
        z.writestr("MANIFEST.txt", manifest)
        for p in files:
            z.write(p, (Path("skill") / p.relative_to(src)).as_posix())

    total = sum(p.stat().st_size for p in files)
    print(f"[OK] 已打包 → {out}")
    print(f"     skill {len(files)} 文件 / 原始 {total/1024:.1f} KB / 压缩 {out.stat().st_size/1024:.1f} KB")
    print(f"     附带：{', '.join(extras)}" if extras else "     附带：无")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="打包 pan-resource-hunt 离线分发包")
    ap.add_argument("--src", default=str(HERE), help="仓库根目录")
    ap.add_argument("--out", default=str(HERE / "dist" / "pan-resource-hunt-skill.zip"), help="输出 zip")
    a = ap.parse_args()
    return build(Path(a.src).expanduser().resolve(), Path(a.out).expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
