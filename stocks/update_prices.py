#!/usr/bin/env python3
"""'내 주식 노트' 포트폴리오의 현재가(cur)를 네이버 금융 종가로 갱신한다.

사용법:
  python3 stocks/update_prices.py <portfolio.json> <out.json>

입력은 ArtifactData get 으로 받은 portfolio 문서(JSON), 출력은 ArtifactData
update 에 그대로 넘길 {"holdings": [...], "priceUpdated": "..."} 객체다.
종목명 -> 종목코드는 stocks/codes.json 에 캐시하고, 없으면 네이버 자동완성으로 찾는다.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CODES = os.path.join(HERE, "codes.json")
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"}
KST = timezone(timedelta(hours=9))


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def norm(s):
    return "".join(s.split()).lower()


def lookup_code(name):
    q = urllib.parse.quote(name)
    tries = [
        ("https://ac.stock.naver.com/ac?q=%s&target=stock" % q, lambda d: d.get("items", [])),
        ("https://m.stock.naver.com/front-api/search/autoComplete?query=%s&target=stock" % q,
         lambda d: (d.get("result") or {}).get("items", [])),
    ]
    for url, pick in tries:
        try:
            items = pick(get_json(url))
        except Exception:
            continue
        exact = [i for i in items if norm(i.get("name", "")) == norm(name) and i.get("nationCode", "KOR") == "KOR"]
        for i in exact or items[:1]:
            code = i.get("code") or i.get("reutersCode")
            if code and code[:6].isalnum():
                return code[:6]
    return None


def fetch_prices(codes):
    out = {}
    for k in range(0, len(codes), 20):
        chunk = ",".join(codes[k:k + 20])
        try:
            d = get_json("https://polling.finance.naver.com/api/realtime/domestic/stock/" + chunk)
            for it in d.get("datas", []):
                out[it["itemCode"]] = int(str(it["closePrice"]).replace(",", ""))
        except Exception:
            pass
    for c in codes:  # 실패한 종목은 하나씩 재시도
        if c in out:
            continue
        try:
            d = get_json("https://m.stock.naver.com/api/stock/%s/basic" % c)
            out[c] = int(str(d["closePrice"]).replace(",", ""))
        except Exception:
            pass
    return out


def main(src, dst):
    doc = json.load(open(src, encoding="utf-8"))
    holdings = doc["holdings"]
    codes = json.load(open(CODES, encoding="utf-8")) if os.path.exists(CODES) else {}
    for h in holdings:
        if h["name"] not in codes:
            c = lookup_code(h["name"])
            if c:
                codes[h["name"]] = c
    json.dump(dict(sorted(codes.items())), open(CODES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    prices = fetch_prices(sorted({codes[h["name"]] for h in holdings if h["name"] in codes}))
    updated, missing = [], []
    for h in holdings:
        p = prices.get(codes.get(h["name"], ""))
        if p:
            h["cur"] = p
            updated.append(h["name"])
        else:
            missing.append(h["name"])
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    json.dump({"holdings": holdings, "priceUpdated": now}, open(dst, "w", encoding="utf-8"), ensure_ascii=False)

    cost = sum(h["buy"] * h["qty"] for h in holdings)
    val = sum((h.get("cur") or h["buy"]) * h["qty"] for h in holdings)
    print("updated %d / %d  missing: %s" % (len(updated), len(holdings), ", ".join(missing) or "-"))
    print("매입 %s원  평가 %s원  손익 %+d원 (%+.2f%%)" % (format(cost, ","), format(val, ","), val - cost, (val / cost - 1) * 100))
    return 0 if updated else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
