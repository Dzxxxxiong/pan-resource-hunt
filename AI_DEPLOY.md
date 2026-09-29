# AI_DEPLOY.md — 给 AI 助手的执行契约

> 本文件面向**自动化助手**。人类请读 [DEPLOY.md](DEPLOY.md)。
> 目标电脑上的 AI 读到本文件后，应按下列步骤**自行完成部署并验证**，无需逐条征求确认。

## 任务目标

把本仓库安装为 WorkBuddy / Claude Code 用户级 Skill，使其技能列表中出现在 `pan-resource-hunt`。

## 前置检查（并行执行）

| 检查 | 命令 | 通过条件 |
|---|---|---|
| Python 可用 | `python --version` 或 `py -3 --version` | ≥ 3.8 |
| git 可用 | `git --version` | 任意版本 |
| 目标目录 | 见步骤 2 | — |

**无 pip 依赖**：脚本只用标准库，**不要**执行 `pip install`，**不要**建虚拟环境。

## 执行步骤

### 1. 确定 skill 根目录

| 平台 | 路径 |
|---|---|
| Windows | `%USERPROFILE%\.workbuddy\skills\pan-resource-hunt` |
| macOS / Linux | `~/.workbuddy/skills/pan-resource-hunt` |

若用户要求项目级部署，改为 `<项目根>/.workbuddy/skills/pan-resource-hunt`。

### 2. 安装（三选一，按当前仓库形态）

**A. 已有本地仓库副本** → 直接安装：

```bash
python install.py --prune
```

**B. 远程仓库，目标位置就绪** → clone 直用：

```bash
git clone <REPO_URL> "<skill根目录>"
```

**C. 远程仓库，目标位置已有旧版** → 克隆到临时目录再安装（会先备份）：

```bash
git clone <REPO_URL> /tmp/prh && python /tmp/prh/install.py --prune
```

**D. 离线分发包（zip）** → 解压后 `python install.py`。

> `install.py` 自动识别两种布局：仓库根即 skill（`SKILL.md`）或包内 `skill/` 子目录。
> 默认先备份旧版本；需覆盖加 `--force`；先看不做加 `--dry-run`。

### 3. 验证（必须全过）

```bash
python "<skill根目录>/scripts/hunt_fast.py" --help
python "<skill根目录>/scripts/hunt_sources.py" --help
```

通过条件：两条命令均输出 `usage:` 且退出码 0，无 `Traceback`。

`hunt_fast.py --help` 应包含这些参数：
`--seeds` `--title` `--outdir` `--jobs` `--probe-then-verify` `--expect` `--alias`

`hunt_sources.py --help` 应包含：
`--kw` `--probe-sites` `--page` `--merge` `--include-backup`

### 4. 结构自检

必须存在（缺一视为部署失败）：

```
<skill根目录>/SKILL.md
<skill根目录>/scripts/hunt_fast.py
<skill根目录>/scripts/hunt_sources.py
<skill根目录>/references/sources.md
```

`SKILL.md` 首部 frontmatter 必须含 `name: pan-resource-hunt`。
**若目录层级变成 `.../pan-resource-hunt/pan-resource-hunt/SKILL.md`，属错误，需上移一层。**

### 5. 汇报格式

```
[部署结果] 成功 / 失败
[skill 路径] <绝对路径>
[Python] <版本>
[语法自检] N/N 通过
[验证] hunt_fast.py --help ✅ / hunt_sources.py --help ✅
[备注] <渠道网络可达性 / 遇到的问题>
```

## 失败处理（换路继续，不要停在报错上）

| 现象 | 处理 |
|---|---|
| `python` 不存在 | 试 `py -3`；Windows 装 Python 3.11+ 并勾选 Add to PATH |
| 目录层级多套一层 | 把内层内容上移，再重新验证 |
| `SKILL.md` 缺失 | 确认 clone 完整；检查 `.gitignore` 是否误排除 |
| `UnicodeEncodeError`（Windows） | `set PYTHONUTF8=1` 或 `chcp 65001` 后重试 |
| 语法自检失败 | 报告具体文件名与错误行，不要静默跳过 |
| git clone 超时 | 设代理或改用镜像；已下载的 zip 可直接走方式 D |
| 存在旧版本目录 | 走方式 C，`install.py` 会自动备份 |

## 边界（不要做的事）

- 不要改 `scripts/` 下的判定逻辑来"让它跑起来" —— 判活只看 `share_page_type` + `errno`，改文案匹配会引入误杀 bug。
- 不要把并发调高到 16 以上（触发百度风控）。
- 不要在本机执行渠道探测以外的大规模请求来"验证部署"；部署验证只到 `--help` 为止。
