# pan-resource-hunt

按片名/剧名批量获取并**逐条核验**网盘资源链接的 WorkBuddy / Claude Code Skill。
输入一个片名 → 输出一份带接口级证据的可用链接清单。

**零第三方依赖**（纯 Python 标准库），Windows / macOS / Linux 通用。

> **关于 `{{REPO_URL}}` 占位符**：文档里用它表示"本仓库地址"，不含任何个人账号信息。
> fork 或自建仓库后跑一次 `python push_to_github.py --repo-url <你自己的仓库地址>`，会自动替换成你的地址；
> 若你只是使用者，把它理解成"你 clone 本仓库时用的那个地址"即可。

---

## AI 一键部署（把下面整段发给另一台电脑的 AI）

> 请帮我把这个 skill 部署到本机：克隆 `{{REPO_URL}}` 到
> `~/.workbuddy/skills/pan-resource-hunt/`，然后运行 `python install.py` 完成安装，
> 最后用 `hunt_fast.py --help` 和 `hunt_sources.py --help` 验证，并把结果告诉我。
> 如果目标目录已存在，先备份旧版本。

---

## 安装

### 方式 1：git clone（推荐，可 `git pull` 更新）

```bash
git clone {{REPO_URL}} ~/.workbuddy/skills/pan-resource-hunt
```

Windows PowerShell：

```powershell
git clone {{REPO_URL}} "$env:USERPROFILE\.workbuddy\skills\pan-resource-hunt"
```

### 方式 2：克隆到任意位置再安装

```bash
git clone {{REPO_URL}} ~/src/pan-resource-hunt
python ~/src/pan-resource-hunt/install.py            # 装到 ~/.workbuddy/skills/
python ~/src/pan-resource-hunt/install.py --dry-run  # 先预览
python ~/src/pan-resource-hunt/install.py --force    # 覆盖不备份
```

### 方式 3：项目级（只对某个项目生效）

```bash
python install.py --target "<项目根>/.workbuddy/skills/pan-resource-hunt"
```

> **目录层级必须是** `skills/pan-resource-hunt/SKILL.md`。
> 多套一层会导致技能不被识别。

---

## 更新

```bash
cd ~/.workbuddy/skills/pan-resource-hunt && git pull
```

---

## 用法

```bash
cd <片名>_<年份>

# 0. 渠道健康度（先跑，别把「渠道挂了」当「没资源」）
python ~/.workbuddy/skills/pan-resource-hunt/scripts/hunt_sources.py --probe-sites

# 1. 挖源
python .../hunt_sources.py --kw "片名" --alias 变体 --year 2026 --out 02_work/seeds_src.json
python .../hunt_sources.py --merge 02_work/seeds.json --add 02_work/seeds_src.json

# 2. 核验（探活秒筛 + 只对存活条细验 + 自动筛「实为其它影片」）
python .../hunt_fast.py --seeds 02_work/seeds.json --title "片名(年份)" \
    --outdir 03_output --jobs 8 --probe-then-verify \
    --expect "片名" --alias "避讳写法" --alias "pinyin"
```

**交付口径：只交付 `pan.baidu.com` 可用链接**，不收夸克/迅雷/阿里等备用线索。

实测：48 条候选原版 132.4s → 加速版 10.2s（**13x**），缓存复跑 0.12s。

---

## 目录结构

```
pan-resource-hunt/
├── SKILL.md                 技能定义（frontmatter: name / description）
├── scripts/
│   ├── hunt_fast.py         ★ 核验首选：并发 + 单请求短路 + 缓存 + 探活串联 + 变体匹配
│   ├── hunt_sources.py      ★ 挖源半自动：PanSou 打源 / 页面抽链接 / 渠道探针 / 合并去重
│   ├── hunt.py              遗留串行版（保留参考）
│   └── verify_pan.py        已废弃（早期原型）
├── references/
│   ├── sources.md           渠道清单 / 关键词变体规律 / PanSou 实例状态
│   └── templates.md         四套文档模板
├── install.py               跨平台安装器
├── DEPLOY.md                详细部署指南 + FAQ
└── AI_DEPLOY.md             给 AI 的执行契约（机器可读）
```

---

## 判定规则（核心，别改坏）

- 判活**只看** `share_page_type` + 业务 `errno`，**不看页面文案**。
  百度新版分享页正文预置「链接不存在」模板串，按文案判会把有效链接全部误杀。
- 提取码正确：`POST /share/verify` → `errno == 0`；错误 → `-9`。
- 分享列表：`GET /share/list` → `0` 正常 / `-21` 已取消 / `-22` 不存在。
- 并发上限 **≤12**（≥16 触发百度风控）；默认 `--jobs 8`。

## 已知边界

- 匿名**无法递归分享子目录**：`root=1` 模式下 `dir` 参数被服务端忽略 → 只能拿到分享根目录名，验不了真实分辨率/体积。
- 发布方自称的「4K」未经内容级验证，写入清单时必须标注「自称」。
- 链接会被随时和谐，核验结果有时效性，需要时复跑。
- `film_score` 对首字母缩写型避讳（如 `SMP3`）失分，需用 `--alias` 显式补别名。

## License

MIT
