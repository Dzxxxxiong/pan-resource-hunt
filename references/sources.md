# 渠道清单（挖源用）

> **交付口径：只交付 `pan.baidu.com` 可用链接。**
> 夸克/迅雷/阿里/UC 不列入清单、不作"备用线索"。下表若标注某站"多为夸克/阿里"，
> 只说明该站的资源构成（不必浪费轮次去抓），不代表要交付它们。

## 一、站点模板

| 类型 | 站点 | URL 模式 | 备注 |
|---|---|---|---|
| 聚合站 | Mini4k | `https://mini4k.io/movies/{tmdb_id}` | 页面列出多条下载条目，标题常带 `[百度/迅雷/夸克]`；详情页 `/torrents/{id}` |
| 聚合站 | 瞎分享 | `https://xiafenxiang.com/d/{id}-{slug}` | 单帖多片，百度链接 `?pwd=1234` 常为统一口令 |
| 聚合站 | 好家当 | `https://www.hjdang.com/d/{id}` | 百度链接来自"超级会员 v8"分享；**搜索页 `?q=` 回的是推荐流不是结果**，百度端极少 |
| 聚合站 | 拾光宝库 | `https://shiguangbaoku.com/resource/{slug}` | 单帖单片，页面有完整百度链接 + 提取码（`?pwd` 需从正文取） |
| 聚合站 | 四海清单 | `https://mklist.com/topics/film?orderby=favorite` | 按日期归档的清单流 |
| 论坛 | 恩山无线 | `https://www.right.com.cn/forum/thread-{tid}-1-1.html` | 影视资源版块，帖子含百度+夸克；在映期新片命中率高 |
| 论坛 | 天涯 BBS | `https://bbs.bantian.net/thread-{tid}.htm` | 常给迅雷盘 |
| 贴吧 | 静态页 | `https://static.tieba.baidu.com/p/{tid}` | **可直接 WebFetch 抓正文**，含链接与提取码 |
| 贴吧 | 吧内动态流 | `https://ala.baidu.com/f?kw={urlencode}`<br>`https://nani.baidu.com/f?kw={urlencode}` | 滚动流，含大量同片多帖，按时间排序 |
| 频道 | QQ 频道 | `https://pd.qq.com/g/{guild}/post/{post}` | 百度链接+口令 |
| 频道 | Telegram 公开预览 | `https://t.me/s/{channel}` | **本机常 fetch failed，需 SOCKS5 代理**；2026-09-29 实测全线 http 000，**不可作主依赖** |
| 文档 | 飞书公开 | `https://{tenant}.feishu.cn/docx/{id}` | 汇总型，一页多片 |

## 二、可用 Telegram 频道（检索验证过存在）

- `t.me/s/JDbigdiscount`（网盘资源分享）
- `t.me/s/xiaoqiaoziyuanku`（小乔网盘资源库，夸克/百度/迅雷）

## 三、PanSou 插件名全表（可作为挖源范围）

```
hunhepan, jikepan, panwiki, pansearch, panta, qupansou, susu, wanou,
xuexizhinan, panyq, zhizhen, labi, muou, ouge, shandian, duoduo, huban,
cyg, erxiao, miaoso, fox4k, pianku, clmao, wuji, cldi, xiaozhang,
libvio, leijing, xb6v, xys, ddys, hdmoli, yuhuage, u3c3, clxiong,
jutoushe, sdso, xiaoji, xdyh, haisou, bixin, djgou, nyaa, xinjuc,
aikanzy, qupanshe, xdpan, discourse, yunsou
```

`E` 环境变量示例：`export ENABLED_PLUGINS=labi,zhizhen,shandian,duoduo,muou,wanou`

## 四、开源聚合器

| 项目 | 说明 |
|---|---|
| PanSou | `github.com/fish2018/pansou`（Go 1.18+）。聚合 TG 频道 + 插件源，自动识别 13 种网盘链接并按类型归类。提供 MCP 服务，可接入支持 MCP 的客户端。**许可证未确认**（检索页未返回 LICENSE，用前查仓库根目录）。 |
| PanSou Web | `docker run -d --name pansou -p 80:80 ghcr.io/fish2018/pansou-web` |
| PanSou API | `docker run -d --name pansou -p 8888:8888 ghcr.io/fish2018/pansou:latest`，接口 `POST /api/search {"kw":"片名","res":"merge","refresh":true}` |

**定位**：PanSou 解决"去哪找"，**不解决"找到后能否用"**。挖源可参考它，核验必须走本技能脚本。

### 公开 PanSou 实例（2026-09-29 全量复测，11 个）

| 实例 | 状态 |
|---|---|
| `so.252035.xyz` | **间歇可用**。同一实例反复横跳：200 / 400 / 403 / 429 / 超时 / 「200 但 `merged_by_type` 为空」 |
| `pansou.top` | 可连通（http 200）但恒返回空结果 |
| `hunhepan.com/api/search` | 返回 **HTML 非 JSON**，不是 PanSou API |
| `pansou.qlhazq.com`、`so.ylxq.cc`、`pansou.czl.net`、`pan.czl.net`、`api.pansou.cc`、`pansou.0112.xyz`、`so.pansou.top`、`api.252035.xyz` | **全部 SSL 握手失败**（`UNEXPECTED_EOF_WHILE_READING`） |

```bash
# 唯一可试的实例；间隔 ≥3s，限流类错误（400/403/429）需指数退避
curl -s -X POST "https://so.252035.xyz/api/search" \
  -H "Content-Type: application/json" \
  -d '{"kw":"片名","res":"merge"}'
```
返回体：`data.merged_by_type.{baidu|quark|xunlei|uc|aliyun}[]`，元素含 `url` / `password` / `note`。
`refresh:true`（全量刷新）更易超时。同一关键词两次调用结果可能不同（限流降级），需多轮累积去重。

> **结论：PanSou 只能当补充渠道，不能当主依赖。**
> 实测贡献占比很低——《示例片B》11 条可用候选里 PanSou 仅贡献 1 条，其余全靠站点直抓。
> 直接用 `scripts/hunt_sources.py --kw ...` 即可，退避策略已内置，不必手写 curl。

## 五、关键词变体规律（规避审查写法）

| 变体类型 | 示例 |
|---|---|
| 拆字插分隔符 | `示丨例`、`扌例　片` |
| 拆部件 | `木示　亻列`（捌、仙） |
| 拼音 | `shilipian1785148626652` |
| 序号前缀 | `【649】示丨例` |
| 同音 | `捌-亻山` |

→ **已工具化**：核验脚本的 `--expect "片名" --alias "变体"` 会做归一化（去分隔符 + 形近还原）比对根目录名，自动把"存活但实为其它影片"单列并剔除。
显式给别名最可靠：避讳写法（`示例形近`）、拼音（`shilipian`）、拆字（`K-木例`）。拆字型不在自动还原范围内（裸删偏旁会误伤普通词），必须显式声明。
