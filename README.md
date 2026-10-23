# playlist

Auto-refreshed HLS playlist for a TV box / media player.

- feed (raw): `https://raw.githubusercontent.com/<owner>/<repo>/data/playlist.m3u`
- feed (mirror): `https://gh-proxy.com/https://raw.githubusercontent.com/<owner>/<repo>/data/playlist.m3u`
- cadence: every 3 hours, via GitHub Actions

## layout

| file | note |
|---|---|
| `refresh.py` | fetch stream URLs with headless Chrome |
| `build.py` | build `playlist.m3u` |
| `check.py` | optional reachability check |
| `sources.json` | channel table |
| `.github/workflows/refresh.yml` | scheduled job; publishes to the `data` branch |

The generated playlist is published to the **`data`** branch only, so `main` stays small.
