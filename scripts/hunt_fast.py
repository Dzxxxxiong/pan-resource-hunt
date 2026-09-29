# -*- coding: utf-8 -*-
"""
网盘资源核验（加速版，唯一在用版本）
相比原 hunt.py 的优化：
  1. 并发核验：--jobs N（默认 8），ThreadPoolExecutor
  2. 单请求短路：直接带 ?pwd= 请求分享页，页面内联 file_list 时不出第二枪
                 （原版固定 3 请求：page -> verify -> list）
  3. 模式隔离缓存：cache.json，key=mode|shareid|pwd，probe 与 full 互不污染
  4. 超时收紧 + 抖动替代固定 sleep（原版每条固定 2.4s sleep）
  5. --probe-then-verify：先探活秒筛，只对存活条跑完整核验（一条命令顶两步）
  6. --expect/--alias：片名变体匹配，自动识别"存活但实为其它影片"并剔除

用法:
  python hunt_fast.py --seeds seeds.json --title "片名(年份)" --outdir 03_output \
      --jobs 8 --probe-then-verify --expect "片名" --alias "避讳写法" --alias "pinyin"
  python hunt_fast.py --seeds seeds.json --probe-only          # 只探活（候选极多时）
  python hunt_fast.py --seeds seeds.json --no-cache            # 忽略缓存强制重测
"""
import argparse, json, os, re, ssl, sys, time, random, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.parse, urllib.error, http.cookiejar

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PAGE_TO = 12          # 分享页超时（原 25s，失效页通常 <1s 返回，12s 足够）
API_TO = 12
JITTER = (0.05, 0.30)  # 请求间随机抖动，替代固定 sleep
CACHE_TTL = 6 * 3600   # 缓存有效期
_print_lock = threading.Lock()


def new_op():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=CTX))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', 'https://pan.baidu.com/')]
    return op


def get(op, url, t=PAGE_TO):
    try:
        r = op.open(url, timeout=t)
        return r.getcode(), r.geturl(), r.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as e:
        b = ''
        try:
            b = e.read().decode('utf-8', 'ignore')
        except Exception:
            pass
        return e.code, url, b
    except Exception as e:
        return None, url, 'ERR:' + str(e)


def human(n):
    try:
        n = float(n or 0)
    except Exception:
        return '-'
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024:
            return '%.2f%s' % (n, u)
        n /= 1024
    return '%.2fPB' % n


# ---------------- 片名变体匹配（破解避讳命名，自动筛"实为其它影片"） ----------------
# 发布方躲审核的写法：插分隔符（·.-_丨）、形近替换（箜→空、抢→枪）、拼音、前缀序号。
_SEP = re.compile(r'[\s·．.\-_—–~丨|/\\、,，:：()（）\[\]【】<>《》"\']+')
_CONFUSE = {
    # 只做「真·形近/异体」还原；不裸删偏旁（木 口 氵 亻…），否则会误伤普通词。
    # 拆字型（木仓=枪）不在此还原，走 --alias 显式声明，避免假阳性。
    '箜': '空', '埪': '空', '倥': '空',
    '抢': '枪', '搶': '枪', '鎗': '枪',
}


def norm(s):
    """归一化：去分隔符 + 形近字还原 + 小写。用于片名/根目录名比对。"""
    if not s:
        return ''
    s = str(s).lower()
    out = []
    for ch in s:
        out.append(_CONFUSE.get(ch, ch))
    s = ''.join(out)
    return _SEP.sub('', s)


def film_score(root_name, expect_terms):
    """返回 (score, matched_term)。score 为 expect 词在根目录名中的字符覆盖率 0~1。

    expect_terms 是归一化后的期望词表（片名 + 用户给的别名/拼音）。
    命中规则：expect 词的所有字符都出现在根目录名里（多重集包含），取覆盖率最高的词。
    """
    n = norm(root_name)
    if not n or not expect_terms:
        return 0.0, None
    best, bt = 0.0, None
    for t in expect_terms:
        t = norm(t)
        if not t:
            continue
        if t in n:                      # 子串直中
            return 1.0, t
        # 多重集包含率
        pool = list(n)
        hit = 0
        for ch in t:
            if ch in pool:
                pool.remove(ch)
                hit += 1
        sc = hit / len(t)
        if sc > best:
            best, bt = sc, t
    return best, bt


def _parse_page(body):
    """从分享页 HTML 提取元数据 + 内联 file_list"""
    msid = re.search(r'"shareid":(\d+)', body)
    muk = re.search(r'"share_uk":"?(\d+)"?', body)
    mpt = re.search(r'"share_page_type":"(\w+)"', body)
    men = re.search(r'"errno":(-?\d+)', body)
    files = []
    m = re.search(r'file_list":(\[.*?\])\s*,\s*"', body, re.S)
    if m:
        try:
            for f in json.loads(m.group(1)):
                files.append(dict(name=f.get('server_filename'), size=f.get('size'),
                                  size_h=human(f.get('size')), isdir=f.get('isdir')))
        except Exception:
            pass
    try:
        pen = int(men.group(1)) if men else None
    except Exception:
        pen = None
    return (msid.group(1) if msid else None,
            muk.group(1) if muk else None,
            (mpt.group(1) if mpt else ''),
            pen, files)


def check_one(seed, probe_only=False):
    url, pwd = seed['url'], seed.get('pwd')
    rec = dict(url=url, pwd=pwd, claimed=seed.get('claimed'),
               source=seed.get('source'), date=seed.get('date'),
               reqs=0, t0=time.time())
    op = new_op()

    # --- 优化点 2：一次性带上提取码请求分享页 ---
    first = url + ('?pwd=' + str(pwd) if pwd else '')
    code, final, body = get(op, first)
    rec['reqs'] += 1
    rec['http'] = code
    if code is None:
        rec['status'] = 'NET_ERROR'
        rec['detail'] = body
        rec['cost'] = round(time.time() - rec['t0'], 2)
        return rec

    shareid, muk, page_type, page_errno, files = _parse_page(body)
    rec['page_type'], rec['page_errno'] = page_type, page_errno
    rec['shareid'], rec['share_uk'] = shareid, muk

    hard_dead = (code == 404) or page_type == 'error' or page_errno in (-7, -21, -22, 115)
    soft_dead = any(k in body for k in ('链接不存在', '该分享已被取消', '分享的文件已经被取消',
                                        '该链接已失效', '分享已过期')) and not (shareid and muk)
    if hard_dead or soft_dead:
        rec['status'] = 'DEAD_LINK'
        rec['note'] = '服务端失效提示: http=%s page_type=%s errno=%s' % (code, page_type, page_errno)
        rec['files'] = []
        rec['cost'] = round(time.time() - rec['t0'], 2)
        return rec

    if not (shareid and muk):
        rec['status'] = 'NO_META'
        rec['note'] = '分享页未返回 shareid/share_uk（疑似限流或需登录），非失效'
        rec['cost'] = round(time.time() - rec['t0'], 2)
        return rec

    # --- 优化点 2 核心：页面已内联目录 → 直接收工，省掉 verify + list ---
    if files:
        rec['files'] = files
        rec['pwd_ok'] = True if pwd else 'NOT_REQUIRED'
        rec['list_errno'] = 0
        rec['status'] = 'VERIFIED_OK'
        rec['note'] = '单请求命中（页面内联目录）'
        rec['cost'] = round(time.time() - rec['t0'], 2)
        return rec

    if probe_only:
        rec['status'] = 'ALIVE_NOLIST'
        rec['note'] = '探活模式：链接存活，未走提取码/目录'
        rec['files'] = []
        rec['cost'] = round(time.time() - rec['t0'], 2)
        return rec

    # --- 回退：仍需 verify + list（少数不内联的情况） ---
    surl_m = re.search(r'surl=([0-9A-Za-z_\-]+)', final)
    surl = surl_m.group(1) if surl_m else ''
    rec['pwd_ok'] = None
    if pwd and surl:
        vurl = ("https://pan.baidu.com/share/verify?surl=%s&t=%d&channel=chunlei"
                "&web=1&app_id=250528&clienttype=0" % (surl, int(time.time() * 1000)))
        req = urllib.request.Request(
            vurl, data=urllib.parse.urlencode({'pwd': pwd}).encode(),
            headers={'User-Agent': UA, 'Referer': final,
                     'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            j = json.loads(op.open(req, timeout=API_TO).read().decode('utf-8', 'ignore'))
            rec['reqs'] += 1
            rec['errno'] = j.get('errno')
            rec['pwd_ok'] = (j.get('errno') == 0)
            rec['verify_msg'] = j.get('err_msg') or j.get('show_msg')
        except Exception as e:
            rec['verify_error'] = str(e)
        time.sleep(random.uniform(*JITTER))
    else:
        rec['pwd_ok'] = 'NOT_REQUIRED'

    lu = ("https://pan.baidu.com/share/list?uk=%s&shareid=%s&order=other&desc=1"
          "&showempty=0&root=1&web=1&page=1&num=100&dir=%%2F&t=%d&channel=chunlei"
          "&app_id=250528&clienttype=0" % (muk, shareid, int(time.time() * 1000)))
    _, _, b2 = get(op, lu, API_TO)
    rec['reqs'] += 1
    try:
        jb = json.loads(b2)
        rec['list_errno'] = jb.get('errno')
        rec['list_msg'] = jb.get('show_msg')
        for f in (jb.get('list') or []):
            files.append(dict(name=f.get('server_filename'), size=f.get('size'),
                              size_h=human(f.get('size')), isdir=f.get('isdir')))
    except Exception as e:
        rec['list_error'] = str(e)

    rec['files'] = files
    le = rec.get('list_errno')
    if le in (-21, -22):
        rec['status'] = 'DEAD_CANCELLED'
        rec['note'] = rec.get('list_msg') or '分享已被取消'
    elif files and rec['pwd_ok'] in (True, 'NOT_REQUIRED'):
        rec['status'] = 'VERIFIED_OK'
    elif rec['pwd_ok'] is True:
        rec['status'] = 'PWD_OK_NO_LIST'
    elif rec['pwd_ok'] is False:
        rec['status'] = 'PWD_WRONG'
    else:
        rec['status'] = 'UNKNOWN'
    rec['cost'] = round(time.time() - rec['t0'], 2)
    return rec


# ---------------- 网络重试层 ----------------
# 抖动网络 / 服务端限流会把**可用的链接**判成 NET_ERROR / NO_META / UNKNOWN。
# 只对这三类非确定性结果重试；DEAD_LINK / DEAD_CANCELLED 是确定性结论，不重试
# （复测会增加请求量、且结论不会变）。
RETRY_STATUS = ('NET_ERROR', 'NO_META', 'UNKNOWN')


def check_with_retry(seed, probe_only=False, tries=2):
    tries = max(1, tries)
    rec = None
    for k in range(tries):
        try:
            rec = check_one(seed, probe_only)
        except Exception as e:
            rec = dict(url=seed['url'], pwd=seed.get('pwd'),
                       claimed=seed.get('claimed'), source=seed.get('source'),
                       date=seed.get('date'), status='NET_ERROR', note=str(e),
                       files=[], reqs=0, cost=0)
        if rec.get('status') not in RETRY_STATUS:
            return rec
        if k + 1 < tries:
            time.sleep(0.6 * (k + 1))
    if rec is not None:
        rec['retries'] = tries
    return rec


# ---------------- 缓存层 ----------------
# 注意：probe（探活）与 full（完整核验）结果**分命名空间存**。
# 早期版本共用 key，导致「先 --probe-only 再完整核验」时命中污染缓存、
# 直接跳过目录抓取（通过数恒为 0）。勿再合并。
class Cache:
    def __init__(self, path, enabled=True, ttl=CACHE_TTL):
        self.path, self.enabled, self.ttl = path, enabled, ttl
        self.d = {}
        if enabled and os.path.exists(path):
            try:
                self.d = json.load(open(path, encoding='utf-8'))
            except Exception:
                self.d = {}

    @staticmethod
    def key(seed, mode='full'):
        sid = seed['url'].split('/s/')[-1].split('?')[0]
        return '%s|%s|%s' % (mode, sid, str(seed.get('pwd') or ''))

    def get(self, seed, mode='full'):
        if not self.enabled:
            return None
        e = self.d.get(self.key(seed, mode))
        if e and (time.time() - e.get('_ts', 0) < self.ttl):
            return e.get('rec')
        return None

    def put(self, seed, rec, mode='full'):
        if not self.enabled:
            return
        self.d[self.key(seed, mode)] = dict(_ts=time.time(), rec=rec)

    def save(self):
        if self.enabled:
            json.dump(self.d, open(self.path, 'w', encoding='utf-8'),
                      ensure_ascii=False, indent=1)


def render_report(title, results, expect_terms=None):
    """expect_terms 非空时，按片名变体匹配度把通过条拆成「本片 / 疑似他片」两栏。"""
    ok_all = [r for r in results if r['status'] in ('VERIFIED_OK', 'PWD_OK_NO_LIST')]
    bad = [r for r in results if r['status'] in ('NO_META', 'UNKNOWN', 'ALIVE_NOLIST')]
    dead = [r for r in results if r['status'] in ('DEAD_LINK', 'DEAD_CANCELLED')]

    # 片名匹配：MISMATCH（明显是别的片）单列，不计入可用
    ok, mismatch = [], []
    for r in ok_all:
        sc = r.get('film_score')
        if sc is None:
            ok.append(r)
        elif sc >= 0.999:
            ok.append(r)
        elif sc >= 0.5:
            r['_weak'] = True
            ok.append(r)
        else:
            mismatch.append(r)

    L = []
    CN = '一二三四五六七八九'
    sec = [0]

    def head(t):
        sec[0] += 1
        L.append('\n## %s、%s\n' % (CN[sec[0] - 1], t))

    def row(i, r):
        rn = ' / '.join(str(f['name']) for f in r.get('files', [])) or '（未取到）'
        pw = r.get('pwd') or '无需'
        flag = ' ⚠弱匹配' if r.get('_weak') else ''
        return '| %d | %s | `%s` | %s%s | `%s` | %s | %s |' % (
            i, r.get('claimed') or '未标注', pw, rn, flag,
            r['url'] + ('?pwd=' + str(r['pwd']) if r.get('pwd') else ''),
            r.get('source') or '-', r.get('date') or '-')

    L.append('# %s 网盘资源清单（已核验）\n' % title)
    L.append('> 核验时间：%s | 核验方式：分享页存活探测 + 提取码实测 + 分享根目录名比对\n'
             % time.strftime('%Y-%m-%d %H:%M'))
    head('已核验可用（提取码实测通过）')
    if ok:
        L.append('| # | 版本（发布方自称） | 提取码 | 分享根目录名（实测） | 链接 | 来源 | 发布 |')
        L.append('|---|---|---|---|---|---|---|')
        for i, r in enumerate(ok, 1):
            L.append(row(i, r))
    else:
        L.append('_无_')
    if mismatch:
        head('存活但实为其它影片（已剔除）')
        L.append('| 链接 | 实测根目录名 | 匹配度 | 来源 |')
        L.append('|---|---|---|---|')
        for r in mismatch:
            rn = ' / '.join(str(f['name']) for f in r.get('files', [])) or '（未取到）'
            L.append('| `%s` | %s | %.0f%% | %s |' % (
                r['url'] + ('?pwd=' + str(r['pwd']) if r.get('pwd') else ''),
                rn, (r.get('film_score') or 0) * 100, r.get('source') or '-'))
    if bad:
        head('待人工复测（非失效）')
        L.append('| 链接 | 状态 | 说明 |')
        L.append('|---|---|---|')
        for r in bad:
            L.append('| `%s` | %s | %s |' % (
                r['url'] + ('?pwd=' + str(r['pwd']) if r.get('pwd') else ''),
                r['status'], r.get('note') or '服务端未返回可判定信息'))
    if dead:
        head('已确认失效')
        L.append('| 链接 | 失效原因（服务端返回） | 来源 |')
        L.append('|---|---|---|')
        for r in dead:
            L.append('| `%s` | %s | %s |' % (
                r['url'], r.get('note') or r.get('list_msg') or '链接不存在',
                r.get('source') or '-'))
    head('使用方法')
    L.append('1. 复制链接，浏览器打开 → 输入提取码 → 点「保存到网盘」转存。')
    L.append('2. 手机端：复制整条链接（含 `?pwd=` 部分），打开对应网盘 App 自动识别。')
    L.append('3. 转存后建议立即下载到本地，避免源主取消分享。')
    L.append('4. 若链接失效：换清单内下一条；高画质条目失效概率高于 1080P 条目。')
    L.append('\n---\n')
    L.append('- 通过核验：**%d** 条（另有 %d 条实为其它影片已剔除） | 待复测：%d | 失效：%d | 合计：%d'
             % (len(ok), len(mismatch), len(bad), len(dead), len(results)))
    L.append('- 画质标注为发布方自述，**未经内容级验证**（匿名无法递归子目录）。')
    return '\n'.join(L)


def run_batch(todo, jobs, probe_only, cache, cache_mode, tries=2):
    """并发跑一批；返回 {index: rec}。probe 与 full 结果分开缓存。
    tries 控制对 NET_ERROR/NO_META/UNKNOWN 的重试次数。"""
    out = {}
    if not todo:
        return out
    done = 0
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(check_with_retry, s, probe_only, tries): (i, s) for i, s in todo}
        for f in as_completed(futs):
            i, s = futs[f]
            try:
                r = f.result()
            except Exception as e:
                r = dict(url=s['url'], pwd=s.get('pwd'), status='NET_ERROR',
                         detail=str(e), files=[], cost=0)
            out[i] = r
            cache.put(s, r, cache_mode)
            with lock:
                done += 1
                names = ' '.join(str(x['name']) for x in r.get('files', []))
                print('[%2d/%2d] %-18s %-14s rq=%d %4.1fs %s' % (
                    done, len(todo), r['url'][-18:], r['status'],
                    r.get('reqs', 0), r.get('cost', 0), names[:38]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', required=True)
    ap.add_argument('--title', default='资源')
    ap.add_argument('--outdir', default='03_output')
    ap.add_argument('--jobs', type=int, default=8, help='并发数，默认 8，建议 4-12')
    ap.add_argument('--probe-only', action='store_true', help='只探活，不走提取码')
    ap.add_argument('--probe-then-verify', action='store_true',
                    help='先秒筛探活，只对存活条跑完整核验（一条命令顶原来两步）')
    ap.add_argument('--no-cache', action='store_true', help='忽略缓存')
    ap.add_argument('--tries', type=int, default=2,
                    help='对 NET_ERROR/NO_META/UNKNOWN 的重试次数，默认 2（0 表示不重试）')
    ap.add_argument('--expect', default='', help='片名（用于自动识别"实为其它影片"）')
    ap.add_argument('--alias', action='append', default=[],
                    help='片名变体/别名/拼音，可多次给（如 --alias 示例形近 --alias shilipian）')
    a = ap.parse_args()

    seeds_path = os.path.abspath(a.seeds)
    work = os.path.dirname(seeds_path)
    seeds = json.load(open(seeds_path, encoding='utf-8'))
    print('seeds = %d | jobs = %d | cache = %s' % (len(seeds), a.jobs, 'off' if a.no_cache else 'on'))

    expect_terms = ([a.expect] if a.expect else []) + list(a.alias)

    cache = Cache(os.path.join(work, 'cache.json'), enabled=not a.no_cache)
    results = [None] * len(seeds)
    t_start = time.time()

    # 缓存回填（模式隔离：probe 与 full 互不污染）
    mode = 'probe' if a.probe_only else 'full'
    hit = 0
    todo = []
    for i, s in enumerate(seeds):
        c = cache.get(s, mode)
        if c is not None:
            results[i] = c
            hit += 1
        else:
            todo.append((i, s))
    if hit:
        print('cache hit = %d, 需实跑 = %d' % (hit, len(todo)))

    if a.probe_then_verify and not a.probe_only:
        print('--- pass 1/2 探活秒筛 ---')
        p_done = run_batch(todo, a.jobs, True, cache, 'probe', a.tries)
        results = [p_done.get(i, results[i]) for i in range(len(seeds))]
        alive = [(i, s) for i, s in todo
                 if (p_done.get(i) or {}).get('status') in
                 ('ALIVE_NOLIST', 'VERIFIED_OK', 'NO_META')]
        print('--- pass 2/2 完整核验（存活 %d，跳过已失效 %d）---'
              % (len(alive), len(todo) - len(alive)))
        f_done = run_batch(alive, a.jobs, False, cache, 'full', a.tries)
        results = [f_done.get(i, results[i]) for i in range(len(seeds))]
    else:
        done_map = run_batch(todo, a.jobs, a.probe_only, cache, mode, a.tries)
        results = [done_map.get(i, results[i]) for i in range(len(seeds))]

    results = [r for r in results if r is not None]
    cache.save()

    # 片名变体匹配 → 自动识别"存活但实为其它影片"
    if expect_terms:
        for r in results:
            if r.get('files'):
                r['film_score'] = round(
                    max(film_score(f['name'], expect_terms)[0] for f in r['files']), 3)
            else:
                r['film_score'] = None

    wall = time.time() - t_start
    tot_req = sum(r.get('reqs', 0) for r in results)
    print('\n=== 总计 %d 条 | 缓存 %d | 总请求 %d | 墙钟 %.1fs（均 %.2fs/条）==='
          % (len(results), hit, tot_req, wall, wall / max(1, len(results))))

    json.dump(results, open(os.path.join(work, 'verify_final.json'), 'w',
                            encoding='utf-8'), ensure_ascii=False, indent=2)
    clean = [dict(url=r['url'], full_url=r['url'] + ('?pwd=' + str(r['pwd']) if r.get('pwd') else ''),
                  pwd=r.get('pwd'), claimed=r.get('claimed'), source=r.get('source'),
                  date=r.get('date'), link_alive=(r['status'] not in ('DEAD_LINK', 'DEAD_CANCELLED')),
                  pwd_ok=r.get('pwd_ok'), verify_errno=r.get('errno'),
                  list_errno=r.get('list_errno'), list_msg=r.get('list_msg'),
                  root_names=[f['name'] for f in r.get('files', [])], status=r['status'],
                  film_score=r.get('film_score'))
             for r in results]
    json.dump(clean, open(os.path.join(work, 'links_clean.json'), 'w',
                          encoding='utf-8'), ensure_ascii=False, indent=2)

    os.makedirs(a.outdir, exist_ok=True)
    rp = os.path.join(a.outdir, '资源清单.md')
    open(rp, 'w', encoding='utf-8').write(render_report(a.title, results, expect_terms))
    okn = len([r for r in results
               if r['status'] in ('VERIFIED_OK', 'PWD_OK_NO_LIST')
               and (r.get('film_score') is None or r['film_score'] >= 0.5)])
    print('通过核验 %d / 合计 %d' % (okn, len(results)))
    print('report ->', os.path.abspath(rp))


if __name__ == '__main__':
    main()
