#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把本仓库推送到 GitHub（零依赖，纯标准库）。

它做三件事：
  1. 把文档里的 {{REPO_URL}} 占位符替换成真实仓库地址（幂等，可重复跑）
  2. 设置/更新 git remote origin
  3. commit + push 当前分支

用法：
    # 已有远程仓库（网页上先建好空仓库）
    python push_to_github.py --repo-url https://github.com/<你>/pan-resource-hunt.git

    # 用 gh CLI 直接创建（需先 gh auth login）
    python push_to_github.py --gh-create --name pan-resource-hunt

    # SSH 方式
    python push_to_github.py --repo-url git@github.com:<你>/pan-resource-hunt.git

    # 只看会做什么
    python push_to_github.py --repo-url <url> --dry-run

可选：
    --dir PATH     仓库目录（默认 = 本脚本所在目录）
    --branch NAME  分支名（默认 main）
    --private      --gh-create 时建私有仓库（默认）
    --public       --gh-create 时建公开仓库
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACEHOLDER = "{{REPO_URL}}"
DOC_FILES = ["README.md", "DEPLOY.md", "AI_DEPLOY.md"]


def run(cmd: list[str], cwd: Path, dry: bool, check: bool = True) -> tuple[int, str]:
    printable = " ".join(cmd)
    if dry:
        print(f"  [dry-run] {printable}")
        return 0, ""
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    if out.strip():
        for line in out.strip().splitlines():
            print(f"  | {line}")
    if check and p.returncode != 0:
        print(f"  [ERROR] 命令失败（exit {p.returncode}）：{printable}")
    return p.returncode, out


def swap_placeholder(repo: Path, url: str, dry: bool) -> int:
    hits = 0
    for name in DOC_FILES:
        f = repo / name
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        if PLACEHOLDER not in text:
            continue
        n = text.count(PLACEHOLDER)
        hits += n
        if dry:
            print(f"  [dry-run] {name}: 替换 {n} 处 {PLACEHOLDER} → {url}")
        else:
            f.write_text(text.replace(PLACEHOLDER, url), encoding="utf-8", newline="\n")
            print(f"  [OK] {name}: 替换 {n} 处")
    if hits == 0:
        print(f"  [i] 未发现 {PLACEHOLDER}（已替换过或文档无占位符）")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="推送 pan-resource-hunt 到 GitHub")
    ap.add_argument("--dir", default=str(HERE), help="仓库目录")
    ap.add_argument("--repo-url", help="远程仓库地址（https 或 ssh）")
    ap.add_argument("--gh-create", action="store_true", help="用 gh CLI 创建远程仓库")
    ap.add_argument("--name", default="pan-resource-hunt", help="--gh-create 时的仓库名")
    ap.add_argument("--public", action="store_true", help="--gh-create 时建公开仓库（默认私有）")
    ap.add_argument("--branch", default="main", help="分支名（默认 main）")
    ap.add_argument("--message", default="chore: 替换仓库地址占位符", help="占位符替换的提交信息")
    ap.add_argument("--dry-run", action="store_true", help="只展示动作")
    a = ap.parse_args()

    repo = Path(a.dir).expanduser().resolve()
    dry = a.dry_run

    if not (repo / ".git").exists():
        print(f"[ERROR] {repo} 不是 git 仓库。请先 git init 或确认 --dir。")
        return 2

    print(f"仓库目录 : {repo}")

    # ---- 1. 决定 remote URL ----
    url = a.repo_url
    if a.gh_create and not url:
        vis = "--public" if a.public else "--private"
        print(f"\n[1] 用 gh 创建远程仓库 {a.name}（{vis}）")
        cmd = ["gh", "repo", "create", a.name, vis, "--source=.", "--remote=origin", "--push"]
        rc, _ = run(cmd, repo, dry)
        if rc != 0:
            print("  [HINT] gh 未登录？先执行：gh auth login")
            return rc
        # 创建后从 remote 取真实 URL（不硬编码用户名），继续走后续收尾步骤
        if dry:
            url = f"https://github.com/<user>/{a.name}.git"
        else:
            rc2, out2 = run(["git", "remote", "get-url", "origin"], repo, dry, check=False)
            url = out2.strip().splitlines()[-1].strip() if rc2 == 0 and out2.strip() else ""
            if not url:
                print("[ERROR] 无法从 origin 读取 URL。")
                return 2
        print(f"[OK] 仓库已建：{url}")
        print("     续做：占位符替换 + 分支统一 + 推送\n")

    print(f"远程地址 : {url}")

    # ---- 2. 替换占位符 ----
    print("\n[1] 替换文档占位符")
    changed = swap_placeholder(repo, url, dry)

    # ---- 3. remote ----
    print("\n[2] 配置 remote origin")
    rc, out = run(["git", "remote", "get-url", "origin"], repo, dry, check=False)
    if not dry and rc == 0 and "origin" in out.lower():
        run(["git", "remote", "set-url", "origin", url], repo, dry)
    else:
        run(["git", "remote", "add", "origin", url], repo, dry)

    # ---- 4. commit ----
    print("\n[3] 提交")
    if changed and not dry:
        run(["git", "add", "-A"], repo, dry)
        run(["git", "commit", "-m", a.message], repo, dry, check=False)
    elif dry:
        print(f"  [dry-run] git add -A && git commit -m \"{a.message}\"")
    else:
        print("  [i] 无文档改动，跳过提交")

    # ---- 5. branch + push ----
    print(f"\n[4] 确保分支 {a.branch} 并推送")
    run(["git", "branch", "-M", a.branch], repo, dry, check=False)
    rc, _ = run(["git", "push", "-u", "origin", a.branch], repo, dry)

    if not dry and rc == 0:
        print("\n[OK] 推送完成。")
        print(f"     仓库地址：{url.removesuffix('.git')}")
        print("\n另一台电脑部署（把整段发给那台电脑的 AI）：")
        print(f"     请克隆 {url} 到 ~/.workbuddy/skills/pan-resource-hunt/，")
        print("     运行 python install.py 完成安装，然后用 hunt_fast.py --help 验证并汇报结果。")
    elif not dry:
        print("\n[HINT] push 失败常见原因：")
        print("  - 远程仓库尚未创建 → 先在 GitHub 网页建空仓库，或用 --gh-create")
        print("  - 网络不通 → git config --global http.proxy http://127.0.0.1:端口")
        print("  - HTTPS 需凭证 → 用 Personal Access Token 作密码，或改用 SSH 地址")
    return 0 if dry else rc


if __name__ == "__main__":
    sys.exit(main())
