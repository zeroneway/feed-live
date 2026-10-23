#!/usr/bin/env python3
"""把 verified.json 生成带分组/台标的 M3U 播放列表（供电视端 IPTV/播放器直接读取）。"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def group_of(name):
    if name.startswith(("CCTV", "CGTN")):
        return "央视"
    if "教育" in name:
        return "教育"
    return "卫视"

def main():
    chans = {str(c["pid"]): c for c in json.load(open(os.path.join(HERE, "sources.json")))}
    src = os.path.join(HERE, "verified.json")
    if not os.path.exists(src):
        src = os.path.join(HERE, "results.json")
    rows = json.load(open(src))
    if src.endswith("verified.json"):
        rows = [r for r in rows if r.get("seg_status") == 200 and r.get("playurl")]
    else:
        rows = [r for r in rows if r.get("ok") and r.get("playurl")]
    order = {"央视": 0, "卫视": 1, "教育": 2}
    rows.sort(key=lambda r: (order.get(group_of(r["name"]), 9),
                             list(chans).index(str(r["pid"])) if str(r["pid"]) in chans else 999))
    out = os.path.join(HERE, "playlist.m3u")
    with open(out, "w", encoding="utf-8") as f:
        f.write("#EXTM3U x-tvg-url=\"\"\n")
        for r in rows:
            c = chans.get(str(r["pid"]), {})
            g = group_of(r["name"])
            logo = c.get("logo", "")
            f.write(f'#EXTINF:-1 tvg-id="{r["pid"]}" tvg-name="{r["name"]}" tvg-logo="{logo}" group-title="{g}",{r["name"]}\n')
            f.write(r["playurl"] + "\n")
    print(f"写出 {len(rows)} 个频道 -> {out}")
    # 同时给一份纯地址清单，方便排查
    with open(os.path.join(HERE, "urls.txt"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f'{r["name"]}\t{r["playurl"]}\n')

if __name__ == "__main__":
    main()
