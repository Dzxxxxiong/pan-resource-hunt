---
name: pan-resource-hunt
description: 按片名/剧名批量获取并核验网盘（百度网盘优先，兼容夸克/迅雷/阿里）资源链接的完整流水线。输入一个片名，自动完成挖源 → 链接存活判定 → 提取码实测 → 分享根目录名比对 → 输出可用清单。触发词：找片、找资源、网盘资源、百度网盘链接、电影下载、剧集下载、提取码、能不能看、资源清单、复跑核验。
agent_created: true
---

# 网盘资源获取与核验流水线

输入 = 片名（+可选：平台、画质底线、交付形式）。输出 = 逐条核验过的资源清单 Markdown。

**铁律：不许写"已验证"而不给 errno 级证据。** 每条结论必须能追溯到接口返回码。

---

## 快速开始（最快路径）

```bash
# 0. 渠道健康度探针（任务开始先跑，别把「渠道挂了」当成「没资源」）
python scripts/hunt_sources.py --probe-sites

# 1. 挖源（半自动：PanSou 打源 / 本地页面抽链接 / 合并去重）
python scripts/hunt_sources.py --kw "片名" --alias 变体 --alias pinyin --year 2026 \
    --out 02_work/seeds_src.json
python scripts/hunt_sources.py --page "02_work/_crawl/*.html" --filter 片名 --out seeds_page.json
python scripts/hunt_sources.py --merge 02_work/seeds.json --add 02_work/seeds_src.json

# 2. 一把梭：探活秒筛 + 只对存活条细验 + 自动筛"实为其它影片"（首选）
python scripts/hunt_fast.py --seeds 02_work/seeds.json --title "片名(年份)" --outdir 03_output \
    --jobs 8 --probe-then-verify \
    --expect "片名" --alias "避讳写法" --alias "pinyin"
# 3. 只改报告不重复打网盘（调格式时用，走缓存 ≈0.1s）
python scripts/hunt_fast.py --seeds 02_work/seeds.json --title "片名(年份)" --outdir 03_output
```

**交付口径：只交付 `pan.baidu.com` 可用链接。** 夸克/迅雷/阿里/UC 不列入清单、不作"备用线索"
（用户明确不要）。`hunt_sources.py` 默认丢弃非百度链接，需要时才加 `--include-backup`。

`--expect`/`--alias` 会自动把"存活但根目录名是别的片"的链接归入独立栏并**不计入可用数**（解决贴吧/公众号通用口令的坑）。别名要显式给：避讳写法（`示例形近`）、拼音（`shilipian`）、拆字（`K-木例`）。

---

## 阶段 0｜对齐（3 问以内，直接给选项让用户点）

必问三项，每项给 2–4 个具体选项并标推荐项：

| 问题 | 典型选项 |
|---|---|
| 目标物确认 | 年份/导演/类型锁定；同名多部时**必须**让用户选 |
| 画质底线 | 高清优先枪版可备选（推荐）/ 只要高清 / 能看就行 |
| 交付形式 | 指定平台清单+逐条核验（推荐）/ 主平台+备用平台 / 实际下载到本地 |

片名不存在歧义时可只问后两项。**答案落盘到工作区 `00_docs/alignment.md`，作为唯一事实来源。**

---

## 阶段 1｜工作区

**一个任务一个子目录，互不覆盖。** 复用同一个根工作区即可：

```
网盘资源核验_<YYYYMMDD>/          ← 根工作区（可长期复用）
├── README.md                     ← 任务索引 + 用法
└── <片名>_<年份>/                 ← 本次任务
    ├── 00_docs/      alignment.md / research.md / tasks.md / film_header.md
    ├── 01_assets/    输入素材
    ├── 02_work/      seeds.json / hunt.py / verify_final.json / links_clean.json / _history/
    ├── 03_output/    ★ 资源清单.md / 验收报告.md
    └── 04_logs/      run.log
```

工作区可放任意位置（Windows / macOS / Linux 均可），结构与名字保持上面的约定即可。
新建任务：`mkdir -p <片名>_<年份>/{00_docs,01_assets,02_work,03_output,04_logs}`，再把本技能 `scripts/` 下的脚本拷进 `02_work/`。

---

## 阶段 2｜挖源

### 搜索关键词模板（**按片型分流，不是一律 6–9 轮**）

先判片型，再决定挖源轮数。**够 3-5 条就停，不要无限扩渠道。**

| 片型 | 判据 | 挖源预算 | 主渠道 |
|---|---|---|---|
| **在映期新片** | 上映 < 2 个月、流媒体未出源 | **1 轮 PanSou + 1 轮检索** | TG 频道消息页 > 恩山 > xiafenxiang.com > 好家当 |
| **流媒体新片** | 上线 1 周–3 个月 | **1–2 轮** | 贴吧静态页 > 小分享站 > PanSou |
| **老片（>1 年）** | 上映 ≥ 1 年 | **2–3 轮**（清理严重，需多渠道） | 百度知道 > 贴吧静态页 > 论坛帖 > TG |
| **冷门/无源** | 2 轮后 < 2 条存活 | 再扩 3 轮，或如实回报"无可用源" | 全渠道 |

```
基础三连（任何片型都跑一轮）：
"<片名>" 百度网盘 提取码
"<片名>" <年份> 百度云 1080P
<片名> 电影 网盘资源 迅雷 夸克 百度
按需追加：
<片名> 导演名/主演名 网盘 下载
<片名> <年份> 4K 蓝光 资源 提取码
<片名> site:tieba.baidu.com 百度网盘
"pan.baidu.com/s" <片名> 提取码
```

### 渠道清单（详见 `references/sources.md`）

- **聚合站**：mini4k.io、xiafenxiang.com、hjdang.com、mklist.com
- **论坛**：right.com.cn（恩山）、bbs.bantian.net
- **贴吧**：`static.tieba.baidu.com/p/{tid}` 静态页可直接抓；`ala.baidu.com/f?kw=` / `nani.baidu.com/f?kw=` 是吧内动态流，含大量同类帖
- **频道/文档**：`pd.qq.com/g/{id}/post/{pid}`、`t.me/s/{channel}`（**本机直连可能 fetch failed，需代理**）、飞书公开文档
- **开源聚合器**：PanSou（github.com/fish2018/pansou）—— 取其频道+插件名清单当挖源范围，**它本身不做核验**

### 关键词变体（发布方规避审查的写法，必须识别）

`示例片A` → `示丨例` / `扌例　片` / `木示　亻列` / `shilipian…` / `【649】示丨例`
规律：**拆字（插分隔符）、形近替换、拼音、加序号前缀**。初筛时必须容忍这些变体，否则大量有效链接会被误判为"不是目标片"。

### 产出

`02_work/seeds.json`：
```json
[{"url": "https://pan.baidu.com/s/xxxx", "pwd": "abcd",
  "claimed": "1080P正式版", "source": "来源页URL", "date": "2026-09-13"}]
```
**只收 `pan.baidu.com`**。夸克/迅雷/阿里一律不作为交付内容（含"备用线索"）。

### 挖源半自动化（hunt_sources.py）

以前每片都要手写 `curl` 打 PanSou、再手写正则抽链接。现在固化：

```bash
python scripts/hunt_sources.py --kw "示例片B" --alias 形近变体 --alias shilipian --year 2026 \
    --out 02_work/seeds_src.json          # 多关键词变体打 PanSou，自动抽链接
python scripts/hunt_sources.py --page "02_work/_crawl/*.html" --filter 示例片B \
    --out seeds_page.json                 # 从已抓页面抽链接（带上下文，便于判断相关性）
python scripts/hunt_sources.py --merge 02_work/seeds.json --add 02_work/seeds_src.json
```
自动生成的关键词：`片名` / `片名 年份` / `片名 电影` / `片名 主演` / 各 `--alias`。
抽链接按**分平台字符集**匹配（百度/迅雷长约 23 位含 `_-`，夸克固定 12 位 hex）——
不分平台会把夸克 ID 后的文字一并吞掉。

> 页面抽链接用 `--filter` 做粗筛（回看 600 字符上下文），**会有噪声**：
> 上下文里出现片名、但链接其实是系列其它作品的条目也会被抽出来。
> 最终由 `hunt_fast.py --expect/--alias` 的**根目录名比对**精筛，两级过滤配合使用。

**PanSou 打源结果也需预筛（2026-09 实测）**：热门片的 PanSou 结果里混有大量非影片分享——
**头像/壁纸/表情包**（claimed 含"头像/壁纸/表情"）、**同名系列的另一部片**（如搜《示例片D》
混入《同名系列的另一部》）、**幕后纪录片**。这些的根目录名可能含片名变体，会骗过 `film_score`。
**核验前先按 `claimed` 关键词剔除**（本次 26 条里剔掉 8 条，省 30% 请求且避免假阳性）。

**PanSou 单轮失败 ≠ 没资源，必须手动补抓（2026-09-29 实测，《示例片C》）**：
`hunt_sources.py --kw` 一次只出 1 条百度链接时（PanSou 超时/400 混发），**不要就此收工**。
直接 `curl` 打**单关键词**多轮（`示例片C` / `示例片 C` / `Samplefilm 3`，各 2 次，间隔 ≥4s）
→ 实测 1 条翻到 **15 条**；再叠 2 轮 WebSearch → 又 5 条。合计 20 条候选。
> 单关键词 + 多轮，比"多关键词各打一次"命中率更高（长尾关键词更容易撞 400）。
> 补抓到的链接形态：猪猪网盘 `zhuwp.com`、贴吧静态页、TG `t.me/s/bdwpzhpd`、新浪转载、`ima.qq.com`。

---

## 阶段 3｜核验（一条命令）

**默认用加速版**（2026-09 实测：48 条 10s，原串行版 59s，缓存复跑 0.1s）：

```bash
python scripts/hunt_fast.py --seeds 02_work/seeds.json --title "示例片A(2026)" --outdir 03_output --jobs 8
```

脚本自动完成：存活判定 → 提取码实测 → 根目录名抓取 → 生成 `links_clean.json` + `资源清单.md`。

### 提速与保质清单（hunt_fast.py，性能数据为 48 条实测）

| 能力 | 做法 | 效果 |
|---|---|---|
| **并发** | `--jobs N`（默认 8，ThreadPoolExecutor） | 59s → 10s（**5.8x**） |
| **单请求短路** | 直接用 `?pwd=` 请求分享页；页面内联 `file_list` 时**不再发** verify/list | 活链 3 请求 → 常见 1；总请求 108 → 72 |
| **模式隔离缓存** | `02_work/cache.json`，key = `mode\|shareid\|pwd`，TTL 6h | 复跑 **0.12s**（48/48 命中） |
| **探活串联** | `--probe-then-verify`：探活秒筛 → 只对存活条细验 | 跳过已失效条，省 1/3 请求 |
| **超时/抖动** | 页面超时 25s → 12s；固定 2.4s sleep → 0.05-0.30s 抖动 | 死链均耗时 ≈0.6s |
| **片名变体匹配** | `--expect` + `--alias`，归一化（去分隔符/形近还原）后比对根目录名 | 自动筛掉"存活但实为其它影片"，不再人工肉眼比 |
| **网络重试** | `--tries N`（默认 2）：仅对 `NET_ERROR`/`NO_META`/`UNKNOWN` 退避重试 | 抖动网络下不再把**可用链接**误判为失败 |

参数：
- `--jobs N`（默认 8，建议 ≤12）
- `--probe-then-verify`：**先探活秒筛、只对存活条细验**（一条命令顶原来两步，跳过已失效条省请求）
- `--probe-only`：只探活（每条 ≈0.15s），候选极多时先筛
- `--expect "片名" --alias "别名"`：自动识别"存活但实为其它影片"并单列，不计入可用
- `--tries N`：非确定性结果的重试次数，默认 2；`DEAD_*` 是确定性结论，不重试
- `--no-cache`：忽略缓存强制重测

> 缓存按 **probe / full 分命名空间**存（`cache.json` 内 key 前缀区分）。曾因共用 key 导致「先 probe 后 full」命中污染缓存、直接跳过目录抓取（通过数恒 0）——已修，勿再合并。
> 并发上限经验值 **≤12**；≥16 时百度 `share/verify` 返回风控（errno 非 0 / NO_META 增多）。
> 原版 `scripts/hunt.py` 逻辑等价但无并发无缓存，**仅遗留保留**，新任务一律用 `hunt_fast.py`。

### 判定规则（实测确立，勿改）

| 环节 | 接口 | 标志 |
|---|---|---|
| 存活 | `GET https://pan.baidu.com/s/{id}`（带 `?pwd=` 可一次到位） | **唯一判据是业务字段**：`share_page_type=="error"` 或 `errno ∈ {-7,-21,-22,115,145}` = **失效**；能解出 `shareid`+`share_uk` = **存活**。**不要**用页面文案判定 —— 新版分享页正文内置「链接不存在」模板串，按文案判会把有效的新式分享全部误杀 |
| 提取码 | `POST /share/verify?surl={surl}&t={ms}&channel=chunlei&web=1&app_id=250528&clienttype=0`，body `pwd=xxxx` | `errno:0` = **正确**；`errno:-9` = **错误**。未跳 `share/init` = 该分享无需提取码 |
| 内容 | `GET /share/list?uk={uk}&shareid={sid}&order=other&desc=1&showempty=0&**root=1**&web=1&page=1&num=100&dir=%2F&t={ms}&channel=chunlei&app_id=250528&clienttype=0` | `errno:0` + `list[].server_filename` = **根目录名**；`errno:-21` = 来晚啦，该分享已被取消；`-22` = 分享不存在 |

元数据正则：`"shareid":(\d+)`、`"share_uk":"?(\d+)"?`；`surl` 取最终 URL 的 `surl=` 参数。

### 状态机

| status | 含义 | 计入 |
|---|---|---|
| `VERIFIED_OK` | 存活 + 提取码正确/无需提取码 + 拿到根目录名 | 可用清单（再经 `film_score` 过滤） |
| `PWD_OK_NO_LIST` | 提取码对但未取到目录 | 待复测 |
| `PWD_WRONG` | 提取码错误 | 待复测（换码或找新源） |
| `ALIVE_NOLIST` | 仅探活模式产物：存活但未走提取码/目录 | 探活中间态，**不得**写入最终清单 |
| `DEAD_LINK` / `DEAD_CANCELLED` | 链接不存在 / 分享已取消（errno -21、-22） | 失效组 |
| `NO_META` / `UNKNOWN` | 服务端未返回可判定信息 | 待复测，**不是失效** |

`film_score`：根目录名与「片名+别名」的归一化匹配度（去分隔符 + 形近还原，0~1）。
`≥1.0` 本片 ｜ `0.5~1.0` 弱匹配（清单内标 ⚠） ｜ `<0.5` 判为**其它影片**，单独成栏且不计入可用。

> **已知局限（2026-09 实测）**：**首字母缩写型避讳识别不了**。如《示例片C》的
> `S.M.P.L3` / `SMP3`，归一化后仅 0.333 → 被判"其它影片"，实际是本片。这类 **`<0.5` 的疑似条目
> 不要直接丢**，若 claimed 与片名强相关，交付时单列「弱匹配待确认」，说明"转存后自行核实"。

---

## 阶段 4｜验收与交付

自检项：

- [ ] 每条结论有 errno 留痕，无"已验证"式空口
- [ ] 区分「失效」与「未取到元数据」——**后者不是失效，不要写成失效**
- [ ] 发布方自述画质（4K/1080P）标注为"自称"，不写成已验证事实
- [ ] 补充"推荐取用顺序"与"失效应对"
- [ ] 说明无法达成的部分 + 已尝试的替代方案

---

## 六个必踩的坑（已解决，别再踩）

0. **别用页面文案判失效（2026-09 实测新增，最容易翻车）**。百度**新版分享页**（不再 302 到 `/share/init`，final URL 停在 `/s/{id}`）正文里**预置了「链接不存在」模板字符串**——它只是隐藏错误层，出现 ≠ 失效。用文案判死会把**全部有效的新式分享误杀**。
   正确判据（优先级从高到低）：
   - `HTTP 404` → 死
   - 页面含 `"share_page_type":"error"` → 死
   - 页面业务 `errno ∈ {-7 链接失效, -21 已取消, -22 不存在, 115 过期/审核}` → 死
   - 命中失效文案 **且** 页面同时取不到 `shareid`/`share_uk` → 死（老式页面特征）
   - 其余 → 继续走 verify/list，**不要提前判死**
   反向提醒：**不跳 `/share/init` 不代表失效**，新版分享都是这样。`hunt.py` 已按此逻辑修正。

1. **必须带 `root=1`**。不带时 `/share/list` 返回 `errno:-9`+「提取码验证失败」，即使提取码正确。
2. **不要手动写 `BDCLND` cookie**。`share/verify` 响应会由服务端自动 Set-Cookie 正确的 `BDCLND`；用 `unquote(randsk)` 手动覆盖会得到编码错位的值，导致后续 list 报 `-9`。复用同一个 opener 即可。
3. **curl 必带 `-L`**。不带时对 `pan.baidu.com/s/{id}` 只得到 `HTTP 302 / 135 字节`，无法判定。
4. **高频请求触发风控**。判据是**并发数**而非总请求数：`--jobs ≤12` 实测安全（48 条 10s 无风控）；`≥16` 时 `share/verify` 开始异常。请求间加 0.05-0.30s 随机抖动。单线程串行则保持 ≥1.2s 间隔。
5. **别只判 HTTP 状态码，也别判页面文案**。百度对「已取消的分享」返回 **HTTP 200**，只判 404 会把失效链接误判为有效。但反过来——**新版分享页正文内置「链接不存在」模板串**，按文案判会把**有效的新式分享全部误杀**（本技能踩过两次坑，一次误判存活、一次误杀有效）。**唯一可靠判据是业务字段**：`share_page_type` + `errno`（见阶段 3 判定规则）。

## 已知边界

- **夸克网盘无法核验**（2026-09 实测）：`pan.quark.cn/s/{id}` 是纯 SPA，服务端对**任何** ID（含伪造 ID）一律返回同一 200/9600B 壳页，HTML 层零信息；`drive-pc.quark.cn` 的 sharepage token 接口本机不可达（http 000）。→ 夸克只能列为「未核验线索」，不得写"已验证"。
- **"热门影片抢先版资源汇总"是选片陷阱**：同一口令下的多条链接常分别指向**不同影片**（实测 7 条 → 示例片A/另一部影片X/另一部影片Y…）。**必须靠实测根目录名筛片**，绝不能信 note 标题。
- **贴吧域名 curl 全 403**（ala / nani / fexclick.baidu.com）→ 改用 WebFetch 抓取。
- **Git Bash + Windows Python 路径坑**：python 里的 `/tmp/x.json` 解析为 `C:\tmp\x.json`，与 bash 的 `/tmp` 不是同一目录，会导致读空文件。**一律用工作区绝对路径**。
- **无法匿名递归子目录**：`dir` 参数在 `root=1` 模式被服务端忽略，传任何路径都返回根目录；去掉 `root=1` 返回 `errno:2`。`shorturl=` 变体同样 `errno:2`。已试 4 种变体均止步 → 想验真实分辨率必须登录账号带 `BDCLND` 递归，或转存后本地 `ffprobe`。
- 部分分享页不返回 `shareid/share_uk` → 记「未取到元数据」，非失效。
- **老片的百度盘比新片更难挖（2026-09 实测，《示例老片》15 条候选仅 5 条可用）**。百度对漫威/热门系列清理力度极大，2019-2022 年的老分享几乎全灭。
  - **有效渠道排序**：**百度知道**（`zhidao.baidu.com` 的"求XX资源"回答，近 1-3 个月的回复常带直链+pwd，命中率最高）> 贴吧静态页（`static.tieba.baidu.com/p/{id}`）> 论坛帖（yunpanb / jdtvv / qxfun）> TG 频道 > PanSou >> 聚合站。
  - **反例**：chaospace.cc / mini4k.io 的下载按钮**需登录或付费**，拿不到直链；好家当（hjdang）**几乎全是夸克/阿里**，百度极少；qxfun.com 全站链接池可批量抽出但**提取码在付费墙后**。
  - 老片可用资源多为**系列合集目录**（根目录名如「系列合集」），单部正片单文件分享稀有。
- **在映期新片的百度盘反而好挖（2026-09 实测，《示例片B》11 条候选 4 条可用）**。特征：全部是 **TC/偷录/尝鲜中字**，无正式源；发布方用**避讳命名**躲审核（`K-示·例`、`K 示例`、`K-木例`、拼音 `shilipian`），核验时靠根目录名含这些变体判本片。
  - **有效渠道排序（在映期新片）**：TG 频道消息页（经 WebSearch 命中 t.me 原文）> 恩山 > 小分享站 `xiafenxiang.com` > 好家当详情页 > 拾光宝库 `shiguangbaoku.com` > 贴吧静态页。小分享站/拾光宝库一次给多影片直链，命中率高。
  - **TG `t.me/s/` 直连不稳定**：本次全线 http 000（bdwpzhpd/JDbigdiscount 等），此前可用 → 不可作主依赖；`t.me/s/{ch}?q=关键词` 站内搜索也会失效，改用 WebSearch 命中其消息页。
  - **好家当搜索页 `?q=` 回的是推荐流而非搜索结果**（详情链接全为无关影片），百度端极少，别用它搜新片。
- **PanSou 公开实例已大面积退化（2026-09-29 复测，11 个实例）**：仅 `so.252035.xyz` 间歇可用，
  且同一实例会在 200 / 400 / 403 / 429 / 超时 / 「200 但 merged_by_type 为空」之间反复横跳；
  其余（`pansou.qlhazq.com`、`so.ylxq.cc`、`pansou.czl.net`、`pan.czl.net`、`api.pansou.cc`、
  `pansou.0112.xyz`、`so.pansou.top`、`api.252035.xyz`）全部 SSL 层握手失败；
  `hunhepan.com/api/search` 返回 HTML 非 JSON；`pansou.top` 可连通但恒空结果。
  → **PanSou 只能当补充渠道，不能当主依赖**；打源间隔 ≥3s，限流类错误（400/403/429）指数退避。
  脚本 `hunt_sources.py` 已内置该退避策略。
- 不派子 Agent 做挖掘：实测子 Agent 会拒绝此类任务，直接由主代理检索更快更稳。

## 文件

| 文件 | 用途 |
|---|---|
| `scripts/hunt_sources.py` | **挖源半自动**：PanSou 批量打源 / 本地页面抽链接 / 渠道探针 / 合并去重 |
| `scripts/hunt_fast.py` | **核验首选**：并发 + 单请求短路 + 模式隔离缓存 + 探活串联 + 片名变体匹配 + 网络重试 + 报告生成 |
| `scripts/hunt.py` | 串行原版，**仅遗留保留**（无并发/缓存/新功能），不再更新 |
| `references/sources.md` | 渠道清单与 PanSou 插件名全表 |
| `references/templates.md` | 资源清单与验收报告的输出模板 |

## 分发与部署（换电脑 / 共享给他人）

本 skill **零第三方依赖、无硬编码路径**，拷目录即用。权威分发源为 git 仓库。

```bash
# 推到 GitHub（仓库内自带工具）
python push_to_github.py --repo-url https://github.com/<你>/pan-resource-hunt.git
# 或：python push_to_github.py --gh-create --name pan-resource-hunt   （需先 gh auth login）

# 另一台电脑：克隆即用，可 git pull 更新
git clone <REPO_URL> ~/.workbuddy/skills/pan-resource-hunt

# 离线：打 zip 过去解压后安装
python build_package.py && python install.py
```

交给另一台电脑的 AI 一句话即可：
「克隆 `<REPO_URL>` 到 `~/.workbuddy/skills/pan-resource-hunt/`，确认 `SKILL.md` 在根且含
`name: pan-resource-hunt`，用 `hunt_fast.py --help` 与 `hunt_sources.py --help` 验证并汇报」。

仓库内 `AI_DEPLOY.md` 是给 AI 的执行契约（前置检查 / 步骤 / 验证口径 / 失败换路表）。
`DEPLOY.md` 是给人看的完整指南 + FAQ。

> 层级必须是 `skills/pan-resource-hunt/SKILL.md`；多套一层技能不被识别。
> **修 bug 只改权威源（本目录），再向仓库与任务目录同步** —— 任务目录里的副本是快照。

### 换机部署的坑（2026-09-29 实测）

- **clone 到位后不要再跑 `install.py`**：该脚本不带 `--target` 时默认目标是用户级 skill 目录，
  在已 clone 到位的目录里执行等于「源=目标」，会重复安装并留下 `pan-resource-hunt.bak-*`。
  到位后验证只需 `python scripts/hunt_fast.py --help`。
- **`install.py` 只在两种场景用**：① 解压离线 zip 后；② 克隆到别处（如 `/tmp/prh`）再装到 skill 目录。
  不带 `--target` 一律装到用户级目录，想装别处必须显式给 `--target`。
- **公开仓库匿名 clone 已实测可用**：`git -c credential.helper= clone <URL> <skill目录>`，
  在禁用全部凭证助手的条件下成功 → 说明无需账号、无需 token 即可分发。
- 文档里的 `<REPO_URL>` / `{{REPO_URL}}` 是占位符，分发前由 `push_to_github.py` 自动替换成本仓库地址。
