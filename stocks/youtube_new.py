#!/usr/bin/env python3
"""등록한 YouTube 채널의 새 영상을 찾아 자막을 받아 둔다 ('영상 정리' 탭 재료).

사용법:
  python3 stocks/youtube_new.py <out_dir> [--since YYYYMMDD] [--max N] [--init]

- stocks/youtube_channels.json 의 채널마다 최근 영상 목록을 보고, stocks/videos_seen.json 에
  없는 영상만 처리한다. filter 가 있는 채널은 제목·설명에 그 단어가 있는 영상만 남긴다.
- --since 보다 오래된 영상은 정리하지 않고 본 것으로만 기록한다(오랜만에 돌려도 몰아서 정리하지 않게).
- --init 은 지금 목록을 전부 본 것으로 기록만 하고 끝낸다.
- 결과: <out_dir>/new_videos.json  [{id,url,title,channel,date,duration,description,transcript}]
  자막을 못 받은 영상은 transcript 가 빈 문자열이다. 메타데이터 조회 자체가 실패한 영상은
  seen 에 넣지 않아 다음 실행 때 다시 시도한다.
YouTube 가 클라우드 IP 를 봇으로 막는 일이 잦아, 메타데이터는 web_safari, 자막은 web_embedded
클라이언트로 받는다.
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CHANNELS = os.path.join(HERE, "youtube_channels.json")
SEEN = os.path.join(HERE, "videos_seen.json")
KST = timezone(timedelta(hours=9))


def ytdlp(args, timeout=120):
    r = subprocess.run(["yt-dlp", "--no-warnings"] + args, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def latest_ids(handle, n):
    _, out, _ = ytdlp(["--flat-playlist", "--playlist-end", str(n), "--extractor-args", "youtube:lang=ko",
                       "--print", "%(id)s", "https://www.youtube.com/@%s/videos" % handle])
    return [l.strip() for l in out.splitlines() if l.strip()]


def meta(vid):
    code, out, err = ytdlp(["--skip-download", "--ignore-no-formats-error", "-J",
                            "--extractor-args", "youtube:lang=ko;player_client=web_safari",
                            "https://www.youtube.com/watch?v=" + vid])
    if not out.strip():
        return None
    d = json.loads(out)
    return {"id": vid, "url": "https://www.youtube.com/watch?v=" + vid, "title": d.get("title", ""),
            "channel": d.get("channel", ""), "date": d.get("upload_date") or "",
            "duration": d.get("duration") or 0, "description": d.get("description") or ""}


def transcript(vid, tmp):
    for f in glob.glob(os.path.join(tmp, vid + ".*")):
        os.remove(f)
    # 원어 자동자막(ko-orig)만 요청해야 번역 자막 요청이 막혀 전체가 실패하는 일을 피한다
    files = []
    for lang in ("ko-orig", "ko-orig", "ko"):
        ytdlp(["--skip-download", "--ignore-no-formats-error", "--write-auto-subs", "--write-subs",
               "--sub-langs", lang, "--sub-format", "vtt",
               "--extractor-args", "youtube:lang=ko;player_client=web_embedded",
               "-o", os.path.join(tmp, vid + ".%(ext)s"), "https://www.youtube.com/watch?v=" + vid], timeout=180)
        files = sorted(glob.glob(os.path.join(tmp, vid + ".ko*.vtt")))
        if files:
            break
    if not files:
        return ""
    lines = []
    for l in open(files[0], encoding="utf-8"):
        l = re.sub(r"<[^>]+>", "", l.strip())
        if not l or "-->" in l or l.startswith(("WEBVTT", "Kind:", "Language:")) or l.isdigit():
            continue
        if l not in lines[-3:]:
            lines.append(l)
    return " ".join(lines)


def main():
    a = sys.argv[1:]
    out_dir = a[0]
    since = a[a.index("--since") + 1] if "--since" in a else (datetime.now(KST) - timedelta(days=3)).strftime("%Y%m%d")
    cap = int(a[a.index("--max") + 1]) if "--max" in a else 6
    init = "--init" in a
    os.makedirs(out_dir, exist_ok=True)
    chans = json.load(open(CHANNELS, encoding="utf-8"))
    seen = json.load(open(SEEN, encoding="utf-8")) if os.path.exists(SEEN) else {}
    today = datetime.now(KST).strftime("%Y%m%d")
    found, log = [], []
    for c in chans:
        ids = [v for v in latest_ids(c["handle"], c.get("scan", 12)) if v not in seen]
        if init:
            for v in ids:
                seen[v] = "init"
            log.append("%s: %d개 기록" % (c["name"], len(ids)))
            continue
        for v in ids:
            m = meta(v)
            if not m:
                log.append("%s %s: 정보 조회 실패(다음에 재시도)" % (c["name"], v))
                continue
            text = m["title"] + " " + m["description"]
            if c.get("filter") and c["filter"] not in text:
                seen[v] = "skip"
                continue
            if m["date"] and m["date"] < since:
                seen[v] = "old"
                continue
            if len(found) >= cap:
                log.append("%s %s: 하루 최대 %d개 초과, 다음에 처리" % (c["name"], v, cap))
                continue
            m["channel"] = c["name"]
            m["transcript"] = transcript(v, out_dir)
            seen[v] = today
            found.append(m)
            log.append("%s: %s (%s자)" % (c["name"], m["title"], len(m["transcript"])))
    json.dump(seen, open(SEEN, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump(found, open(os.path.join(out_dir, "new_videos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(log) or "새 영상 없음")
    print("new: %d" % len(found))


if __name__ == "__main__":
    main()
