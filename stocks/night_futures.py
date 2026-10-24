#!/usr/bin/env python3
"""야간선물 시세를 모은다 ('미국장' 탭 위쪽 야간선물 칸 재료).

사용법: python3 stocks/night_futures.py <out.json>
- 나스닥100 선물(NQ=F, CME 근월물): Yahoo Finance 일봉. 마지막 봉이 진행 중인 거래일, 바로 앞 봉 종가와 비교한 등락률.
- 코스피200 야간선물: 접근 가능한 자료원이 아직 없어 비워 둔다(kospi: null).
- 결과: {"updated","items":[{key,name,close,prev,chg,time}]}  time 은 마지막 체결 시각(KST "MM/DD HH:MM").
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def yahoo(sym, name, key):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=1d" % sym
    d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15))
    r = d["chart"]["result"][0]
    closes = [c for c in r["indicators"]["quote"][0]["close"] if c is not None]
    last = r["meta"].get("regularMarketPrice") or closes[-1]
    prev = closes[-2] if len(closes) > 1 else None
    t = datetime.fromtimestamp(r["meta"]["regularMarketTime"], KST)
    return {"key": key, "name": name, "close": round(last, 2), "prev": round(prev, 2) if prev else None,
            "chg": round((last / prev - 1) * 100, 2) if prev else None, "time": t.strftime("%m/%d %H:%M")}


def main(dst):
    items = []
    try:
        items.append(yahoo("NQ=F", "나스닥100 선물", "nq"))
    except Exception as e:
        print("나스닥100 선물 실패:", e)
    if not items:
        return 1
    out = {"updated": datetime.now(KST).isoformat(timespec="seconds"), "items": items}
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    for x in items:
        print("%s %s (%+.2f%%) · %s" % (x["name"], x["close"], x["chg"] or 0, x["time"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
