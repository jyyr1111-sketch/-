#!/usr/bin/env python3
"""'내 주식 노트' 포트폴리오의 현재가(cur)를 네이버 금융 종가로 갱신한다.

사용법:
  python3 stocks/update_prices.py <portfolio.json> <out.json> [--targets <targets.json> <targets_out.json>]

입력은 ArtifactData get 으로 받은 portfolio 문서(JSON), 출력은 ArtifactData
update 에 그대로 넘길 {"holdings": [...], "priceUpdated": "..."} 객체다.
--targets 를 주면 '관심 종목' 탭의 targets 문서(items·prices)도 같은 종가로 갱신해 따로 쓴다.
페이지는 열릴 때 targets 의 가격을 보유 종목 현재가에 덮어쓰므로 둘을 함께 갱신해야 한다.
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


def num(v):
    return float(str(v).replace(",", ""))


def quote(it):
    return {"cur": int(num(it["closePrice"])), "chg": num(it.get("fluctuationsRatio") or 0),
            "date": str(it.get("localTradedAt") or "")[:10]}


def market_of(code):
    # 관심 종목에 직접 추가한 종목은 시장이 비어 있어 종목 정보에서 코스피/코스닥을 채운다
    try:
        t = get_json("https://m.stock.naver.com/api/stock/%s/basic" % code).get("stockExchangeType") or {}
    except Exception:
        return None
    return {"KS": "코스피", "KQ": "코스닥"}.get(t.get("code")) or t.get("nameKor")


def fetch_prices(codes):
    # 실시간 시세(polling)는 장 마감 뒤 시간외(NXT) 거래로 계속 바뀌므로, 일별 시세의 정규장 종가를 쓴다
    out = {}
    for c in codes:
        try:
            d = get_json("https://m.stock.naver.com/api/stock/%s/price?pageSize=1&page=1" % c)
            out[c] = quote(d[0])
        except Exception:
            pass
    for k in range(0, len(codes), 20):  # 실패한 종목만 실시간 시세로
        chunk = [c for c in codes[k:k + 20] if c not in out]
        if not chunk:
            continue
        try:
            d = get_json("https://polling.finance.naver.com/api/realtime/domestic/stock/" + ",".join(chunk))
            for it in d.get("datas", []):
                out[it["itemCode"]] = quote(it)
        except Exception:
            pass
    return out


def main(src, dst, tsrc=None, tdst=None):
    doc = json.load(open(src, encoding="utf-8"))
    holdings = doc["holdings"]
    tdoc = json.load(open(tsrc, encoding="utf-8")) if tsrc else None
    titems = (tdoc or {}).get("items") or []
    codes = json.load(open(CODES, encoding="utf-8")) if os.path.exists(CODES) else {}
    for g in titems:
        if g.get("code") and g["name"] not in codes:
            codes[g["name"]] = g["code"]
    for h in holdings + titems:
        if h["name"] not in codes:
            c = lookup_code(h["name"])
            if c:
                codes[h["name"]] = c
    json.dump(dict(sorted(codes.items())), open(CODES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    prices = fetch_prices(sorted({codes[h["name"]] for h in holdings + titems if h["name"] in codes}))
    updated, missing = [], []
    for h in holdings:
        p = prices.get(codes.get(h["name"], ""))
        if p:
            h["cur"] = p["cur"]
            h["curAuto"] = p["date"]  # 자동 종가 표시. 직접 입력 표시(curAt)는 지운다
            h.pop("curAt", None)
            updated.append(h["name"])
        else:
            missing.append(h["name"])
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    json.dump({"holdings": holdings, "priceUpdated": now}, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    if tdoc is not None:
        tp = tdoc.get("prices") or {}
        for g in titems:
            p = prices.get(codes.get(g["name"], ""))
            if p:
                g.update(code=codes[g["name"]], cur=p["cur"], chg=p["chg"])
            if not g.get("mkt") and codes.get(g["name"]):
                g["mkt"] = market_of(codes[g["name"]]) or ""
        for h in holdings:
            p = prices.get(codes.get(h["name"], ""))
            if p:
                tp[h["name"]] = {"code": codes[h["name"]], "cur": p["cur"], "chg": p["chg"]}
        dates = sorted(p["date"] for p in prices.values() if p["date"])
        tdoc.update(items=titems, prices=tp, date=dates[-1] if dates else now[:10],
                    updated=datetime.now(KST).isoformat(timespec="seconds"))
        json.dump(tdoc, open(tdst, "w", encoding="utf-8"), ensure_ascii=False)
        print("targets: %d종목 · 보유 %d종목 · %s 종가" % (len(titems), len(tp), tdoc["date"]))

    cost = sum(h["buy"] * h["qty"] for h in holdings)
    val = sum((h.get("cur") or h["buy"]) * h["qty"] for h in holdings)
    print("updated %d / %d  missing: %s" % (len(updated), len(holdings), ", ".join(missing) or "-"))
    print("매입 %s원  평가 %s원  손익 %+d원 (%+.2f%%)" % (format(cost, ","), format(val, ","), val - cost, (val / cost - 1) * 100))
    return 0 if updated else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    t = a[a.index("--targets") + 1:a.index("--targets") + 3] if "--targets" in a else []
    sys.exit(main(a[0], a[1], *t))
