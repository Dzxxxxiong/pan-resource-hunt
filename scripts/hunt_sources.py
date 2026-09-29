#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
挖源半自动化（hunt_sources.py）

把以往每片都要手写的「curl 打 PanSou + 正则抽链接 + 合并去重」固化为命令。
四种模式，可组合：

  1) PanSou 批量打源（多关键词变体）
     python hunt_sources.py --kw "示例片B" --alias 示例形近 --alias shilipian --year 2026 \
         --out 02_work/seeds_src.json

  2) 本地页面抽链接（带上下文，便于判断相关性；配合 curl 抓回的 html 用）
     python hunt_sources.py --page "02_work/_crawl/*.html" --filter 示例片B --out seeds_page.json

  3) 渠道健康度探针（任务开始先跑，避免把「渠道挂了」当成「没资源」）
     python hunt_sources.py --probe-sites

  4) 合并去重进主 seeds.json
     python hunt_sources.py --merge 02_work/seeds.json --add 02_work/seeds_src.json

输出约定：百度链接写入 --out（可直接喂 hunt_fast.py）；
其余平台（夸克/迅雷/阿里/UC）写入 <out>_backup.json 作备用线索。
"""
import argparse
import glob
import html as htmlmod
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PANSOU = ['https://so.252035.xyz']

# 渠道探针（名称, URL, 方法）
SITE_PROBES = [
    ('PanSou-API', 'https://so.252035.xyz/api/search', 'POST'),
    ('TG-JDbigdiscount', 'https://t.me/s/JDbigdiscount', 'GET'),
    ('好家当', 'https://www.hjdang.com/', 'GET'),
    ('瞎分享', 'https://xiafenxiang.com/', 'GET'),
    ('拾光宝库', 'https://shiguangbaoku.com/', 'GET'),
    ('Mini4k', 'https://mini4k.io/', 'GET'),
    ('恩山', 'https://www.right.com.cn/forum/forum-84-1.html', 'GET'),
    ('hunhepan', 'https://hunhepan.com/', 'GET'),
    ('贴吧静态', 'https://static.tieba.baidu.com/f?kw=%E7%94%B5%E5%BD%B1', 'GET'),
]

# 分平台字符集：百度/迅雷/阿里 ID 长且含 _-；夸克是 12 位 hex。
# 不分平台时会出问题——夸克 ID 后紧跟文字（页面无引号分隔）时，
# 通用 [A-Za-z0-9_\-]+ 会把后续 "https..." 一并吞掉。
NETDISK_RE = re.compile(
    r'(?P<host>pan\.baidu\.com|pan\.quark\.cn|pan\.xunlei\.com|'
    r'www\.aliyundrive\.com|www\.alipan\.com|alipan\.com|drive\.uc\.cn)'
    r'/s/(?P<sid>[A-Za-z0-9_\-]{22,26}|[0-9a-fA-F]{10,21}|[A-Za-z0-9_\-]{8,21})'
    r'(?:\?pwd=(?P<pwd>[A-Za-z0-9]{4,8}))?')

HOST2PLAT = {
    'pan.baidu.com': 'baidu',
    'pan.quark.cn': 'quark',
    'pan.xunlei.com': 'xunlei',
    'www.aliyundrive.com': 'aliyun',
    'www.alipan.com': 'aliyun',
    'alipan.com': 'aliyun',
    'drive.uc.cn': 'uc',
}


def log(*a):
    print(*a)
    sys.stdout.flush()


def plain(s):
    """去标签 + 去脚本 + 反转义 + 压空白"""
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = htmlmod.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def ctx_of(raw, start, back=600, fwd=120):
    """取链接前后片段的纯文本上下文（用于判断是否本片）。
    回看 600 字符与手工筛选口径一致——窗口太窄会漏掉标题在前的条目。"""
    frag = raw[max(0, start - back):start + fwd]
    return plain(frag)


def extract_links(text, want=()):
    """返回 [(platform, host, sid, pwd, start, end)]；want 为空表示全部平台"""
    out = []
    for m in NETDISK_RE.finditer(text):
        plat = HOST2PLAT.get(m.group('host'))
        if not plat or (want and plat not in want):
            continue
        out.append((plat, m.group('host'), m.group('sid'), m.group('pwd'),
                    m.start(), m.end()))
    return out


# ---------------- 模式 1：PanSou 批量打源 ----------------
def gen_kws(kw, aliases, year, actor):
    ks = [kw]
    if year:
        ks.append('%s %s' % (kw, year))
    ks.append('%s 电影' % kw)
    if actor:
        ks.append('%s %s' % (kw, actor))
    ks += [a for a in aliases if a]
    seen, out = set(), []
    for k in ks:
        k = k.strip()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def pansou_search(kw, timeout=45, tries=2):
    """打 PanSou。实测该实例限流严重：400/403/429/超时/空结果混发，
    因此按错误类型退避重试——限流类长退避，其它短退避。"""
    body = json.dumps({'kw': kw, 'res': 'merge'}).encode()
    last = None
    for host in PANSOU:
        for k in range(tries):
            try:
                req = urllib.request.Request(
                    host + '/api/search', data=body,
                    headers={'User-Agent': UA, 'Content-Type': 'application/json'})
                raw = urllib.request.urlopen(req, timeout=timeout,
                                             context=CTX).read().decode('utf-8', 'ignore')
                d = json.loads(raw)
                if d.get('data'):
                    return d
                last = 'code=%s msg=%s（空 data，疑似限流降级）' % (
                    d.get('code'), d.get('message'))
                time.sleep(2.5 * (k + 1))
            except urllib.error.HTTPError as e:
                last = 'HTTP %s' % e.code
                if e.code in (400, 403, 429):
                    time.sleep(3.0 * (k + 1))
                else:
                    time.sleep(1.5 * (k + 1))
            except Exception as e:
                last = str(e)
                time.sleep(1.5 * (k + 1))
    log('  ! PanSou 失败: %s' % last)
    return None


def do_pansou(kw, aliases, year, actor, timeout, tries):
    items = []
    for k in gen_kws(kw, aliases, year, actor):
        d = pansou_search(k, timeout, tries)
        if not d:
            continue
        bt = d.get('data', {}).get('merged_by_type', {}) or {}
        cnt = 0
        for plat, arr in bt.items():
            for it in (arr or []):
                u = it.get('url', '') or ''
                m = NETDISK_RE.search(u)
                if not m:
                    continue
                p = HOST2PLAT.get(m.group('host'))
                if not p:
                    continue
                items.append(dict(
                    url=u if u.startswith('http') else 'https://' + u,
                    platform=p,
                    pwd=it.get('password') or m.group('pwd'),
                    claimed=(it.get('note') or '')[:110],
                    source='PanSou[%s]' % k))
                cnt += 1
        log('  [%s] 抽到 %d 条' % (k, cnt))
        time.sleep(3.0)   # 实测间隔 <3s 易触发限流
    return items


# ---------------- 模式 2：本地页面抽链接 ----------------
def do_pages(patterns, filt):
    files = []
    for p in patterns:
        files += sorted(glob.glob(p))
    if not files:
        log('  ! 无匹配文件: %s' % patterns)
        return []
    items = []
    for f in files:
        try:
            raw = open(f, encoding='utf-8', errors='replace').read()
        except Exception as e:
            log('  ! 读取失败 %s: %s' % (f, e))
            continue
        n = 0
        for plat, host, sid, pwd, s, e in extract_links(raw):
            ctx = ctx_of(raw, s)
            if filt and filt not in ctx:
                continue
            if pwd is None:
                # 上下文里可能有「提取码 xxxx」写法
                mm = re.search(r'(?:提取码|密码|口令)[：: ]*([A-Za-z0-9]{4,8})', ctx)
                if mm:
                    pwd = mm.group(1)
            items.append(dict(url='https://%s/s/%s' % (host, sid),
                              platform=plat, pwd=pwd,
                              claimed=ctx[:110] or '(无上下文)',
                              source=os.path.basename(f)))
            n += 1
        log('  [%s] 抽到 %d 条' % (os.path.basename(f), n))
    return items


# ---------------- 模式 3：渠道探针 ----------------
def probe_sites():
    log('%-18s %-6s %-8s %s' % ('渠道', 'HTTP', '耗时', '判定'))
    log('-' * 60)
    ok = 0
    for name, url, method in SITE_PROBES:
        t0 = time.time()
        code = 0
        try:
            if method == 'POST':
                req = urllib.request.Request(
                    url, data=json.dumps({'kw': '测试', 'res': 'merge'}).encode(),
                    headers={'User-Agent': UA, 'Content-Type': 'application/json'})
            else:
                req = urllib.request.Request(url, headers={'User-Agent': UA})
            r = urllib.request.urlopen(req, timeout=20, context=CTX)
            code = r.getcode()
        except Exception as e:
            code = getattr(e, 'code', 0) or 0
        dt = time.time() - t0
        verdict = 'OK' if 200 <= code < 400 else ('BLOCKED' if code in (401, 403, 429) else 'DOWN')
        if verdict == 'OK':
            ok += 1
        log('%-18s %-6s %-8s %s' % (name, code or '-', '%.1fs' % dt, verdict))
    log('-' * 60)
    log('可用 %d/%d。DOWN 的渠道本轮直接跳过，别把「渠道挂了」当成「没资源」。'
        % (ok, len(SITE_PROBES)))


# ---------------- 写盘 / 合并 ----------------
def dedup(items):
    seen, out = set(), []
    for it in items:
        m = NETDISK_RE.search(it['url'])
        sid = m.group('sid') if m else it['url']
        k = (it.get('platform', 'baidu'), sid)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def to_seed(it, date):
    return dict(url=it['url'].split('?')[0], pwd=it.get('pwd'),
                claimed=it.get('claimed') or '', source=it.get('source') or '',
                date=date)


def write_seeds(items, out_path, date, include_backup=False):
    """默认只落百度链接（交付要求：只要百度网盘可用）。
    备用盘（夸克/迅雷/阿里/UC）仅在 --include-backup 时另存。"""
    baidu = [to_seed(i, date) for i in items if i['platform'] == 'baidu']
    other = [ito for ito in items if ito['platform'] != 'baidu']
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(baidu, f, ensure_ascii=False, indent=1)
    log('\n百度 %d 条 -> %s' % (len(baidu), out_path))
    if other:
        if include_backup:
            bp = os.path.splitext(out_path)[0] + '_backup.json'
            with open(bp, 'w', encoding='utf-8') as f:
                json.dump([dict(url=o['url'], platform=o['platform'], pwd=o.get('pwd'),
                                claimed=o.get('claimed'), source=o.get('source'))
                           for o in other], f, ensure_ascii=False, indent=1)
            log('备用盘 %d 条 -> %s' % (len(other), bp))
        else:
            log('（另有 %d 条非百度链接已丢弃；交付口径：只要百度网盘）' % len(other))


def merge(main_path, add_paths, date):
    main = json.load(open(main_path, encoding='utf-8'))
    have = set()
    for s in main:
        m = NETDISK_RE.search(s['url'])
        have.add(m.group('sid') if m else s['url'])
    added = 0
    for p in add_paths:
        if not os.path.exists(p):
            log('  ! 跳过不存在: %s' % p)
            continue
        arr = json.load(open(p, encoding='utf-8'))
        for s in arr:
            if s.get('platform') and s['platform'] != 'baidu':
                continue
            m = NETDISK_RE.search(s['url'])
            sid = m.group('sid') if m else s['url']
            if sid in have:
                continue
            have.add(sid)
            main.append(dict(url=s['url'].split('?')[0], pwd=s.get('pwd'),
                             claimed=s.get('claimed') or '', source=s.get('source') or '',
                             date=s.get('date') or date))
            added += 1
    json.dump(main, open(main_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log('合并新增 %d 条，seeds.json 现共 %d 条 -> %s' % (added, len(main), main_path))


def report(items):
    by = {}
    for it in items:
        by.setdefault(it['platform'], []).append(it)
    log('\n===== 去重后汇总 =====')
    for p in sorted(by):
        log('## %s %d 条' % (p, len(by[p])))
        for it in by[p]:
            log('   %s |pwd=%s| %s' % (it['url'], it.get('pwd') or '', (it.get('claimed') or '')[:60]))
    log('合计 %d 条' % len(items))


def main():
    ap = argparse.ArgumentParser(
        description='网盘挖源半自动化：PanSou 打源 / 页面抽链接 / 渠道探针 / 合并去重')
    ap.add_argument('--kw', help='片名（触发 PanSou 批量打源）')
    ap.add_argument('--alias', action='append', default=[], help='别名/变体关键词，可多次')
    ap.add_argument('--year', help='年份，用于生成 "<片名> <年份>" 关键词')
    ap.add_argument('--actor', help='主演/导演名，用于生成关键词')
    ap.add_argument('--page', action='extend', nargs='+', default=[],
                    help='本地 HTML 路径或 glob（可多个，空格分隔或多次 --page）')
    ap.add_argument('--filter', help='只保留上下文含该词的链接（用于页面抽链接）')
    ap.add_argument('--probe-sites', action='store_true', help='渠道健康度探针')
    ap.add_argument('--merge', help='主 seeds.json（与 --add 配合）')
    ap.add_argument('--add', action='extend', nargs='+', default=[],
                    help='要并入的文件（可多个）')
    ap.add_argument('--out', help='输出文件（只写百度链接）')
    ap.add_argument('--include-backup', action='store_true',
                    help='同时落盘非百度平台链接（默认丢弃，交付口径只要百度）')
    ap.add_argument('--timeout', type=int, default=45, help='PanSou 超时，默认 45s')
    ap.add_argument('--tries', type=int, default=2, help='PanSou 每关键词重试次数')
    a = ap.parse_args()

    date = time.strftime('%Y-%m-%d')
    did = False

    if a.probe_sites:
        probe_sites()
        did = True

    items = []
    if a.page:
        log('--- 页面抽链接 ---')
        items += do_pages(a.page, a.filter)
        did = True
    if a.kw:
        log('--- PanSou 打源 ---')
        items += do_pansou(a.kw, a.alias, a.year, a.actor, a.timeout, a.tries)
        did = True

    if items:
        items = dedup(items)
        report(items)
        if a.out:
            write_seeds(items, a.out, date, include_backup=a.include_backup)
        else:
            log('\n（未指定 --out，仅预览不落盘）')

    if a.merge:
        log('--- 合并 ---')
        merge(a.merge, a.add, date)
        did = True

    if not did:
        ap.print_help()


if __name__ == '__main__':
    main()
