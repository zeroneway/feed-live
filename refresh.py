#!/usr/bin/env python3
"""用本机 Chrome（CDP）批量从央视频网页取直播流地址，输出 sources.json + playlist.m3u。
用法: python3 mint.py [--only 600001859,600002475] [--out dir]
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request
from websockets.sync.client import connect

CHROME = os.environ.get("CHROME_BIN") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
PROFILE = "/tmp/ysp-mint-profile"
HOME = "https://www.yangshipin.cn/tv/home?pid="

def ensure_chrome():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2).read()
        return
    except Exception:
        pass
    extra = []
    if os.environ.get("CI") or os.geteuid() == 0:
        extra = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
    subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
                      f"--user-data-dir={PROFILE}", "--no-first-run", "--no-default-browser-check",
                      "--mute-audio", "--autoplay-policy=no-user-gesture-required",
                      "--window-size=1280,720", *extra, "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2).read()
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("chrome 启动失败")

class CDP:
    def __init__(self, url):
        self.ws = connect(url, max_size=128 * 1024 * 1024)
        self.n = 0
        self.h = {}
    def send(self, method, params=None, timeout=40):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            msg = json.loads(self.ws.recv(timeout=timeout))
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})
            f = self.h.get(msg.get("method"))
            if f:
                f(msg["params"])
        raise TimeoutError(method)
    def pump_until(self, cond, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            try:
                msg = json.loads(self.ws.recv(timeout=max(0.05, end - time.time())))
            except Exception:
                return cond()
            f = self.h.get(msg.get("method"))
            if f:
                f(msg["params"])
        return cond()

def new_tab():
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
    d = json.load(urllib.request.urlopen(req))
    return CDP(d["webSocketDebuggerUrl"])

def mint(cdp, pid, timeout=20):
    pending = []
    reqs = []
    def on_req(p):
        if "get_live_info" in p["request"]["url"]:
            reqs.append(p["request"].get("postData", ""))
    seen = {}
    def on_res(p):
        seen[p["requestId"]] = p["response"]["url"]
    def on_fin(p):
        if "get_live_info" in seen.get(p["requestId"], ""):
            pending.append(p["requestId"])
    cdp.h["Network.requestWillBeSent"] = on_req
    cdp.h["Network.responseReceived"] = on_res
    cdp.h["Network.loadingFinished"] = on_fin
    pending.clear(); reqs.clear()
    cdp.send("Page.navigate", {"url": HOME + str(pid)})
    cdp.pump_until(lambda: len(pending) > 0, timeout)
    if not pending:
        return {"pid": pid, "ok": False, "error": "no get_live_info response"}
    body = ""
    for attempt in range(6):
        for rid in pending:
            try:
                body = cdp.send("Network.getResponseBody", {"requestId": rid})["body"]
                break
            except Exception as e:
                last = str(e)
        if body:
            break
        time.sleep(0.25)
    if not body:
        return {"pid": pid, "ok": False, "error": "no body " + locals().get("last", "")}
    try:
        top = json.loads(body)
    except Exception:
        return {"pid": pid, "ok": False, "error": "bad json", "raw": body[:200]}
    d = (top or {}).get("data") or {}
    try:
        req = json.loads(reqs[-1]) if reqs else {}
    except Exception:
        req = {}
    return {
        "pid": pid,
        "ok": top.get("code") == 0 and d.get("code") == 0,
        "api_code": top.get("code"),
        "errinfo": d.get("errinfo"),
        "cnlid": d.get("cnlid") or req.get("cnlid"),
        "livepid": d.get("livepid") or req.get("livepid"),
        "defn": d.get("defn"),
        "playurl": d.get("playurl", ""),
        "formats": [{"id": f.get("id"), "fn": f.get("fn"), "defnname": f.get("defnname"), "defnrate": f.get("defnrate")} for f in (d.get("formats") or [])],
        "http_header": d.get("http_header"),
        "playback": d.get("playback"),
        "extra": d.get("extraInfo"),
    }

TRANSIENT = ("no get_live_info response", "no body", "Timeout", "timeout", "connection")

def fresh_tab():
    c = new_tab()
    c.send("Network.enable", {"maxTotalBufferSize": 256 * 1024 * 1024, "maxResourceBufferSize": 32 * 1024 * 1024})
    c.send("Page.enable")
    c.send("Runtime.enable")
    return c

def mint_retry(cdp, pid, tries=3):
    """瞬时失败（请求没回来/句柄丢了）换新标签页重试；真错误（地区限制/需登录）立即返回。"""
    last = None
    for k in range(tries):
        r = mint(cdp, pid)
        if r.get("ok"):
            return r, cdp
        last = r
        msg = str(r.get("errinfo") or r.get("error") or "")
        if not any(t in msg for t in TRANSIENT):
            return r, cdp
        if k + 1 < tries:
            print(f"    重试 {k+1}/{tries-1}", flush=True)
            try:
                cdp.ws.close()
            except Exception:
                pass
            time.sleep(1 + k)
            cdp = fresh_tab()
    return last, cdp

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true", help="忽略已有结果，全部重新取流")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--channels", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "sources.json"))
    args = ap.parse_args()
    chans = json.load(open(args.channels))
    if args.only:
        want = set(args.only.split(","))
        chans = [c for c in chans if str(c["pid"]) in want]
    ensure_chrome()
    outjson = os.path.join(args.out, "results.json")
    done = {}
    if os.path.exists(outjson) and not args.fresh:
        try:
            for r in json.load(open(outjson)):
                done[str(r["pid"])] = r
        except Exception:
            pass
    t0 = time.time()
    for i, c in enumerate(chans, 1):
        pid = str(c["pid"])
        if pid in done and done[pid].get("ok"):
            continue
        cdp = fresh_tab()
        r, cdp = mint_retry(cdp, pid)
        try:
            cdp.ws.close()
        except Exception:
            pass
        r["name"] = c["name"]; r["cnlid_cms"] = c.get("cnlid")
        done[pid] = r
        status = "OK " if r.get("ok") else "FAIL"
        print(f"[{i}/{len(chans)}] {status} {c['name']:<24} pid={pid} cnlid={r.get('cnlid')} {r.get('errinfo') or r.get('error') or ''}", flush=True)
        json.dump(list(done.values()), open(outjson, "w"), ensure_ascii=False, indent=1)
    ok = [r for r in done.values() if r.get("ok") and r.get("playurl")]
    stat = [r for r in ok if not args.only or str(r["pid"]) in want]
    with open(os.path.join(args.out, "playlist.m3u"), "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for r in ok:
            f.write(f'#EXTINF:-1 tvg-id="{r["pid"]}" tvg-name="{r["name"]}",{r["name"]}\n{r["playurl"]}\n')
    print(f"\n成功 {len(stat)}/{len(chans)}，用时 {int(time.time()-t0)}s")
    print("playlist:", os.path.join(args.out, "playlist.m3u"))

if __name__ == "__main__":
    main()
