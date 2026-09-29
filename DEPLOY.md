# pan-resource-hunt 部署指南

三种部署路径 + FAQ。**零第三方依赖、无硬编码路径。**

---

## 前置条件

| 项 | 要求 | 检查 |
|---|---|---|
| Python | ≥ 3.8（推荐 3.11+） | `python --version` |
| git | 任意（走 clone 方式时需要） | `git --version` |
| 网络 | 可访问 `pan.baidu.com` / PanSou 实例 / 贴吧静态页 | `curl -sI https://pan.baidu.com` |
| WorkBuddy | 目标机已安装 | 打开 → 左侧技能列表 |

**不需要 `pip install` 任何东西**（脚本仅用 `urllib`/`ssl`/`json`/`threading`/`concurrent.futures`），也不需要虚拟环境。

---

## 路径 A：git clone（推荐）

```bash
# macOS / Linux
git clone <REPO_URL> ~/.workbuddy/skills/pan-resource-hunt

# Windows PowerShell
git clone <REPO_URL> "$env:USERPROFILE\.workbuddy\skills\pan-resource-hunt"
```

**更新**：`cd ~/.workbuddy/skills/pan-resource-hunt && git pull` —— 不用重装，技能立即生效。

> 仓库根即 skill 根，`SKILL.md` 直接在根目录，因此 clone 到位即可被识别。

---

## 路径 B：克隆 + install.py

适合想保留一份独立源码、或目标位置已有旧版的场景：

```bash
git clone <REPO_URL> ~/src/pan-resource-hunt
python ~/src/pan-resource-hunt/install.py --dry-run   # 先预览
python ~/src/pan-resource-hunt/install.py             # 安装（旧版自动备份）
```

参数：

| 参数 | 作用 |
|---|---|
| `--target DIR` | 装到指定目录（项目级部署） |
| `--force` | 已存在直接覆盖，不备份 |
| `--dry-run` | 只打印将执行的动作 |
| `--prune` | 安装后清理 `__pycache__` |

---

## 路径 C：离线分发包

拷 zip → 解压 → `python install.py`。适合目标机不能访问 GitHub 的情况。

---

## 项目级部署

不想装到用户级、想让技能跟项目走：

```bash
git clone <REPO_URL> <项目根>/.workbuddy/skills/pan-resource-hunt
```

团队其他人 clone 项目后即自动拥有同一技能版本。
**同名时建议只保留一处**（用户级或项目级），避免加载歧义。

---

## 验证部署

```bash
python ~/.workbuddy/skills/pan-resource-hunt/scripts/hunt_fast.py --help
python ~/.workbuddy/skills/pan-resource-hunt/scripts/hunt_sources.py --help
```

两条都输出 `usage:` 即成功。再打开 WorkBuddy 确认技能列表里出现 `pan-resource-hunt`。

---

## 部署后首次使用

skill 装好只代表"会用"，任务数据按工作区约定落盘：

```bash
D="网盘资源核验_$(date +%Y%m%d)/<片名>_<年份>"
mkdir -p "$D"/{00_docs,01_assets,02_work,03_output,04_logs}
cp ~/.workbuddy/skills/pan-resource-hunt/scripts/{hunt_sources.py,hunt_fast.py} "$D/02_work/"
```

Windows PowerShell：

```powershell
$d = "网盘资源核验_$(Get-Date -Format yyyyMMdd)\片名_2026"
New-Item -ItemType Directory -Force -Path "$d\00_docs","$d\01_assets","$d\02_work","$d\03_output","$d\04_logs"
Copy-Item "$env:USERPROFILE\.workbuddy\skills\pan-resource-hunt\scripts\hunt_*.py" "$d\02_work\"
```

---

## FAQ

| 现象 | 原因 | 处理 |
|---|---|---|
| WorkBuddy 技能列表看不到 | 目录层级多套一层 / 缺 `SKILL.md` | 确认路径是 `skills/pan-resource-hunt/SKILL.md`，重启 WorkBuddy |
| `python: command not found` | 无 Python 或未进 PATH | 装 3.11+，勾选 Add to PATH；或试 `py -3` |
| `UnicodeEncodeError` / 中文乱码 | Windows 控制台 GBK | `chcp 65001`，或 `set PYTHONUTF8=1` |
| clone 超时 / 连接失败 | 网络 | 配 git 代理：`git config --global http.proxy http://127.0.0.1:端口` |
| 渠道全挂、结果很少 | 渠道波动（非部署问题） | `hunt_sources.py --probe-sites` 看健康度；PanSou 单轮失败要手动补抓 |
| 中文片名匹配不准 | `film_score` 对首字母缩写型避讳失分 | `--alias` 显式补别名，弱匹配人工判断 |
| 想回滚 | — | 备份目录 `pan-resource-hunt.bak-<时间戳>`，改名回去即可 |

---

## 部署自检清单

- [ ] Python ≥ 3.8 可用
- [ ] `~/.workbuddy/skills/pan-resource-hunt/SKILL.md` 存在且 frontmatter 含 `name: pan-resource-hunt`
- [ ] `scripts/hunt_fast.py` + `scripts/hunt_sources.py` 存在
- [ ] 两个脚本 `--help` 均正常输出
- [ ] `hunt_sources.py --probe-sites` 能跑出渠道状态
- [ ] WorkBuddy 技能列表中可见 `pan-resource-hunt`
