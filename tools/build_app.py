"""italia.html(아티팩트 원본)로 휴대폰 홈 화면 앱(docs/)을 만든다.

    python3 tools/build_app.py

아이콘 PNG는 tools/icon.svg를 바꿨을 때만 --icons 를 붙여 다시 만든다(Playwright 필요).
"""
import hashlib, json, pathlib, shutil, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"

HEAD = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1f4e8c">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="신혼여행">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon-180.png">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
"""

MANIFEST = {
    "name": "이탈리아 신혼여행",
    "short_name": "신혼여행",
    "lang": "ko",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "background_color": "#efebe4",
    "theme_color": "#1f4e8c",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        {"src": "icon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}

SW = """// 오프라인용 캐시. 버전은 build_app.py가 내용 해시로 채운다.
const CACHE = "italia-__VERSION__";
const CORE = ["./", "index.html", "trip.json", "manifest.webmanifest", "icon.svg", "icon-180.png", "icon-192.png", "icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(CORE)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith("italia-") && k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const isFont = url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com";
  if (url.origin !== location.origin && !isFont) return;
  // 캐시를 먼저 보여 주고 뒤에서 새 버전을 받아 둔다
  e.respondWith(caches.open(CACHE).then(async cache => {
    const hit = await cache.match(req, { ignoreSearch: url.origin === location.origin });
    const fresh = fetch(req).then(res => {
      if (res && (res.ok || res.type === "opaque")) cache.put(req, res.clone());
      return res;
    }).catch(() => hit);
    return hit || fresh;
  }));
});
"""


def make_icons():
    script = f"""
const {{ chromium }} = require(process.env.PW);
(async () => {{
  const b = await chromium.launch();
  const p = await b.newPage();
  const svg = require('fs').readFileSync('{ROOT / "tools" / "icon.svg"}', 'utf8');
  for (const s of [180, 192, 512]) {{
    await p.setViewportSize({{ width: s, height: s }});
    await p.setContent(`<style>html,body{{margin:0}}svg{{display:block;width:${{s}}px;height:${{s}}px}}</style>` + svg);
    await p.screenshot({{ path: '{OUT}/icon-' + s + '.png' }});
  }}
  await b.close();
}})();
"""
    pw = subprocess.check_output(["npm", "root", "-g"], text=True).strip() + "/playwright"
    subprocess.run(["node", "-e", script], check=True, env={**__import__("os").environ, "PW": pw})


def main():
    OUT.mkdir(exist_ok=True)
    page = (ROOT / "italia.html").read_text(encoding="utf-8")
    html = HEAD + page.rstrip("\n") + "\n</body>\n</html>\n"
    (OUT / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(ROOT / "trip.json", OUT / "trip.json")
    shutil.copy(ROOT / "tools" / "icon.svg", OUT / "icon.svg")
    (OUT / "manifest.webmanifest").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if "--icons" in sys.argv or not (OUT / "icon-512.png").exists():
        make_icons()
    digest = hashlib.sha256()
    for name in ["index.html", "trip.json", "manifest.webmanifest", "icon.svg"]:
        digest.update((OUT / name).read_bytes())
    (OUT / "sw.js").write_text(SW.replace("__VERSION__", digest.hexdigest()[:10]), encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print("docs/ 빌드 완료")


if __name__ == "__main__":
    main()
