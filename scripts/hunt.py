# -*- coding: utf-8 -*-
"""
网盘资源一站式核验 + 报告生成
用法:
    python hunt.py --seeds 02_work/seeds.json --title "示例片A(2026)" --outdir 03_output
产出:
    <outdir>/../02_work/verify_final.json   (原始核验数据)
    <outdir>/../02_work/links_clean.json    (归一化)
    <outdir>/资源清单.md                     (交付物)
"""
import argparse, json, os, re, ssl, sys, time
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
SLEEP = 1.2


def new_op():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.HTTPSHandler(context=CTX))
    op.addheaders = [('User-Agent', UA), ('Accept-Language', 'zh-CN,zh;q=0.9'),
                     ('Referer', 'https://pan.baidu.com/')]
    return op


def get(op, url, t=25):
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


def check_one(seed):
    """返回单条核验结果 dict"""
    url, pwd = seed['url'], seed.get('pwd')
    rec = dict(url=url, pwd=pwd, claimed=seed.get('claimed'),
               source=seed.get('source'), date=seed.get('date'))
    op = new_op()
    code, final, body = get(op, url)
    rec['http'] = code
    if code is None:
        rec['status'] = 'NET_ERROR'
        rec['detail'] = body
        return rec
    # 判定失效：不能只看页面文案。
    # 百度新版分享页（不再 302 到 /share/init）正文里预置了「链接不存在」这段
    # 模板字符串，但它只是隐藏错误层，出现≠失效。真正可靠的失效信号是：
    #   1) HTTP 404（老式短链彻底没了）
    #   2) 页面内 share_page_type == "error"
    #   3) 页面内业务 errno ∈ {-7 链接失效, -21 分享已取消, -22 分享不存在, 115 过期/审核}
    #   4) 命中失效文案且页面同时拿不到 shareid/share_uk（老式页面失效特征）
    msid = re.search(r'"shareid":(\d+)', body)
    muk = re.search(r'"share_uk":"?(\d+)"?', body)
    mpt = re.search(r'"share_page_type":"(\w+)"', body)
    men = re.search(r'"errno":(-?\d+)', body)
    page_type = mpt.group(1) if mpt else ''
    try:
        page_errno = int(men.group(1)) if men else None
    except Exception:
        page_errno = None
    rec['page_type'] = page_type
    rec['page_errno'] = page_errno

    hard_dead = (code == 404) or page_type == 'error' or page_errno in (-7, -21, -22, 115)
    soft_dead = any(k in body for k in ('链接不存在', '该分享已被取消', '分享的文件已经被取消',
                                        '该链接已失效', '分享已过期')) and not (msid and muk)
    if hard_dead or soft_dead:
        rec['status'] = 'DEAD_LINK'
        rec['note'] = '服务端失效提示: http=%s page_type=%s errno=%s' % (code, page_type, page_errno)
        return rec

    msurl = re.search(r'surl=([0-9A-Za-z_\-]+)', final)
    if not (msid and muk):
        rec['status'] = 'NO_META'
        rec['note'] = '分享页未返回 shareid/share_uk（疑似限流或需登录），非失效'
        return rec

    shareid, uk = msid.group(1), muk.group(1)
    surl = msurl.group(1) if msurl else ''
    rec['shareid'], rec['share_uk'] = shareid, uk

    rec['pwd_ok'] = None
    if pwd and surl:
        vurl = ("https://pan.baidu.com/share/verify?surl=%s&t=%d&channel=chunlei"
                "&web=1&app_id=250528&clienttype=0" % (surl, int(time.time() * 1000)))
        req = urllib.request.Request(
            vurl, data=urllib.parse.urlencode({'pwd': pwd}).encode(),
            headers={'User-Agent': UA, 'Referer': final,
                     'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            j = json.loads(op.open(req, timeout=25).read().decode('utf-8', 'ignore'))
            rec['errno'] = j.get('errno')
            rec['pwd_ok'] = (j.get('errno') == 0)
            rec['verify_msg'] = j.get('err_msg') or j.get('show_msg')
        except Exception as e:
            rec['verify_error'] = str(e)
        time.sleep(SLEEP)
    else:
        # 未跳转 /share/init 说明该分享无需提取码 → 直接走 list 判定
        rec['pwd_ok'] = 'NOT_REQUIRED'

    files = []
    lu = ("https://pan.baidu.com/share/list?uk=%s&shareid=%s&order=other&desc=1"
          "&showempty=0&root=1&web=1&page=1&num=100&dir=%%2F&t=%d&channel=chunlei"
          "&app_id=250528&clienttype=0" % (uk, shareid, int(time.time() * 1000)))
    _, _, b2 = get(op, lu)
    try:
        jb = json.loads(b2)
        rec['list_errno'] = jb.get('errno')
        rec['list_msg'] = jb.get('show_msg')
        for f in (jb.get('list') or []):
            files.append(dict(name=f.get('server_filename'), size=f.get('size'),
                              size_h=human(f.get('size')), isdir=f.get('isdir')))
    except Exception as e:
        rec['list_error'] = str(e)

    if not files:
        _, _, b3 = get(op, url + ('?pwd=' + str(pwd) if pwd else ''))
        m = re.search(r'file_list":(\[.*?\])\s*,\s*"', b3, re.S)
        if m:
            try:
                for f in json.loads(m.group(1)):
                    files.append(dict(name=f.get('server_filename'), size=f.get('size'),
                                      size_h=human(f.get('size')), isdir=f.get('isdir')))
            except Exception:
                pass

    rec['files'] = files
    le = rec.get('list_errno')
    # -21 = 来晚啦，该分享已被取消；-22 = 分享不存在
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
    return rec


def render_report(title, results):
    ok = [r for r in results if r['status'] in ('VERIFIED_OK', 'PWD_OK_NO_LIST')]
    bad = [r for r in results if r['status'] in ('NO_META', 'UNKNOWN', 'PWD_OK_NO_LIST')]
    dead = [r for r in results if r['status'] in ('DEAD_LINK', 'DEAD_CANCELLED')]
    L = []
    CN = '一二三四五六七八九'
    sec = [0]

    def head(t):
        sec[0] += 1
        L.append('\n## %s、%s\n' % (CN[sec[0] - 1], t))

    L.append('# %s 网盘资源清单（已核验）\n' % title)
    L.append('> 核验时间：%s | 核验方式：网盘 share/init 存活探测 + share/verify 提取码实测 + 分享根目录名比对\n'
             % time.strftime('%Y-%m-%d %H:%M'))
    head('已核验可用（提取码实测通过）')
    if ok:
        L.append('| # | 版本（发布方自称） | 提取码 | 分享根目录名（实测） | 链接 | 来源 | 发布 |')
        L.append('|---|---|---|---|---|---|---|')
        for i, r in enumerate(ok, 1):
            rn = ' / '.join(str(f['name']) for f in r.get('files', [])) or '（未取到）'
            pw = r.get('pwd') or '无需'
            L.append('| %d | %s | `%s` | %s | `%s` | %s | %s |' % (
                i, r.get('claimed') or '未标注', pw, rn,
                r['url'] + ('?pwd=' + str(r['pwd']) if r.get('pwd') else ''),
                r.get('source') or '-', r.get('date') or '-'))
    else:
        L.append('_无_')
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
    L.append('- 通过核验：**%d** 条 | 待复测：%d | 失效：%d | 合计：%d'
             % (len(ok), len(bad), len(dead), len(results)))
    L.append('- 画质标注为发布方自述，**未经内容级验证**（匿名无法递归子目录）。')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', required=True)
    ap.add_argument('--title', default='资源')
    ap.add_argument('--outdir', default='03_output')
    ap.add_argument('--from-json', dest='from_json', default=None,
                    help='跳过核验，直接从已有 verify_final.json 重新生成报告')
    a = ap.parse_args()

    seeds_path = os.path.abspath(a.seeds)
    work = os.path.dirname(seeds_path)

    if a.from_json:
        results = json.load(open(a.from_json, encoding='utf-8'))
        print('report-only mode, records =', len(results))
    else:
        seeds = json.load(open(seeds_path, encoding='utf-8'))
        print('seeds =', len(seeds))
        results = []
        for i, s in enumerate(seeds, 1):
            r = check_one(s)
            results.append(r)
            names = ' '.join(str(f['name']) for f in r.get('files', []))
            print('[%2d/%2d] %-20s %-16s %s' % (i, len(seeds), r['url'][-20:],
                                                r['status'], names[:50]))
            time.sleep(SLEEP)
        json.dump(results, open(os.path.join(work, 'verify_final.json'), 'w',
                                encoding='utf-8'), ensure_ascii=False, indent=2)
        clean = [dict(url=r['url'], full_url=r['url'] + ('?pwd=' + str(r['pwd']) if r.get('pwd') else ''),
                      pwd=r.get('pwd'), claimed=r.get('claimed'), source=r.get('source'),
                      date=r.get('date'), link_alive=(r['status'] not in ('DEAD_LINK', 'DEAD_CANCELLED')),
                      pwd_ok=r.get('pwd_ok'), verify_errno=r.get('errno'),
                      list_errno=r.get('list_errno'), list_msg=r.get('list_msg'),
                      root_names=[f['name'] for f in r.get('files', [])], status=r['status'])
                 for r in results]
        json.dump(clean, open(os.path.join(work, 'links_clean.json'), 'w',
                              encoding='utf-8'), ensure_ascii=False, indent=2)

    os.makedirs(a.outdir, exist_ok=True)
    rp = os.path.join(a.outdir, '资源清单.md')
    open(rp, 'w', encoding='utf-8').write(render_report(a.title, results))

    okn = len([r for r in results if r['status'] in ('VERIFIED_OK', 'PWD_OK_NO_LIST')])
    print('\n=== 通过核验 %d / 合计 %d ===' % (okn, len(results)))
    print('report ->', os.path.abspath(rp))


if __name__ == '__main__':
    main()
