#!/usr/bin/env python3
"""合成 M3U 播放列表：cctv.json（固定地址，来自 tv.cctv.com）+ 央视频刷新结果（卫视等）。

用法: python3 build.py            # 直接合成
     VERIFY=1 python3 build.py    # 先探测固定地址是否还活着，掉了就剔除
"""
import concurrent.futures as cf
import json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0"}


def group_of(name):
    if name.startswith(("CCTV", "CGTN")):
        return "央视"
    if "教育" in name:
        return "教育"
    return "卫视"


def alive(url, timeout=8):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
        return r.status == 200 and b"#EXTM3U" in r.read(4096)
    except Exception:
        return False


def load_static():
    p = os.path.join(HERE, "cctv.json")
    if not os.path.exists(p):
        return []
    rows = json.load(open(p, encoding="utf-8"))
    if os.environ.get("VERIFY"):
        with cf.ThreadPoolExecutor(8) as ex:
            ok = list(ex.map(lambda r: alive(r["url"]), rows))
        bad = [r["name"] for r, k in zip(rows, ok) if not k]
        n_ok = len(rows) - len(bad)
        print(f"固定地址检测: {n_ok}/{len(rows)} 可用" + (f"，本机不可达: {','.join(bad)}（可能只是地区限制，仍保留）" if bad else ""))
        # 地区限制会让海外 runner 访问不到部分频道，所以只报警不剔除；全部不可达才认为地址失效
        if n_ok == 0:
            print("固定地址全部不可达，中止发布")
            sys.exit(1)
    return rows


def load_minted(chans):
    src = os.path.join(HERE, "verified.json")
    if not os.path.exists(src):
        src = os.path.join(HERE, "results.json")
    rows = json.load(open(src, encoding="utf-8"))
    if src.endswith("verified.json"):
        rows = [r for r in rows if r.get("seg_status") == 200 and r.get("playurl")]
    else:
        rows = [r for r in rows if r.get("ok") and r.get("playurl")]
    return [r for r in rows if r["name"] in chans]


def main():
    chans = {c["name"]: c for c in json.load(open(os.path.join(HERE, "sources.json"), encoding="utf-8"))}
    idx = {name: i for i, name in enumerate(chans)}

    entries = []
    for r in load_static():
        entries.append((r["name"], r["url"], r.get("logo", ""), "央视"))

    order = {"央视": 0, "卫视": 1, "教育": 2}
    minted = load_minted(chans)
    minted.sort(key=lambda r: (order.get(group_of(r["name"]), 9), idx.get(r["name"], 999)))
    for r in minted:
        entries.append((r["name"], r["playurl"], chans[r["name"]].get("logo", ""), group_of(r["name"])))

    out = os.path.join(HERE, "playlist.m3u")
    with open(out, "w", encoding="utf-8") as f:
        f.write('#EXTM3U x-tvg-url=""\n')
        for name, url, logo, g in entries:
            cid = chans.get(name, {}).get("pid", name)
            f.write(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" tvg-logo="{logo}" group-title="{g}",{name}\n')
            f.write(url + "\n")
    print(f"写出 {len(entries)} 个频道 -> {out}")

    with open(os.path.join(HERE, "urls.txt"), "w", encoding="utf-8") as f:
        for name, url, _, _ in entries:
            f.write(f"{name}\t{url}\n")


if __name__ == "__main__":
    main()
