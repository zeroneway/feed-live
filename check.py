#!/usr/bin/env python3
"""校验已取到的 m3u8 是否可用：m3u8 状态、码率/清晰度变体、首个分片状态。"""
import json, re, sys, time, urllib.request
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"

def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return 0, str(e).encode()

def main():
    rows = json.load(open("results.json"))
    rows = [r for r in rows if r.get("ok") and r.get("playurl")]
    good = bad = 0
    out = []
    for r in rows:
        st, body = get(r["playurl"])
        seg = ""
        if st == 200:
            txt = body.decode("utf-8", "replace")
            m = re.search(r"^([^\s#].*\.ts(?:\?[^\s]*)?)\s*$", txt, re.M)
            seg = m.group(1) if m else ""
            okseg = 0
            if seg:
                base = r["playurl"].rsplit("/", 1)[0]
                okseg, _ = get(base + "/" + seg, timeout=20)
            r["m3u8_status"] = st
            r["seg_status"] = okseg
            if okseg == 200:
                good += 1
            else:
                bad += 1
            print(f'{"OK " if okseg==200 else "SEG"} {r["name"]:<24} m3u8={st} seg={okseg} targetdur={re.search(r"TARGETDURATION:(\d+)", txt).group(1) if "TARGETDURATION" in txt else "?"}')
        else:
            r["m3u8_status"] = st
            bad += 1
            print(f'M3U8 {r["name"]:<24} status={st}')
        out.append(r)
    json.dump(out, open("verified.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n可播 {good} / 取到 {len(rows)} / 失败 {bad}")

if __name__ == "__main__":
    main()
