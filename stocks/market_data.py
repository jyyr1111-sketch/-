#!/usr/bin/env python3
"""시장 분석용 원자료를 네이버 금융에서 모은다.

사용법:
  python3 stocks/market_data.py <portfolio.json> <out.json>

지수·수급·환율·업종 등락·업종별 주도주·상승률 상위를 모으고, 업종 등락은
stocks/history/<거래일>.json 에 쌓아 5거래일 누적 등락(모멘텀)을 계산한다.
출력은 Claude 가 분석을 쓸 때 읽는 재료이며, 그대로 아티팩트에 쓰지 않는다.
"""
import glob
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "history")
M = "https://m.stock.naver.com"
UA = {"User-Agent": "Mozilla/5.0", "Referer": M + "/"}


def get(path):
    req = urllib.request.Request(path if path.startswith("http") else M + path, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def num(s):
    try:
        return float(str(s).replace(",", "").replace("+", ""))
    except ValueError:
        return None


def slim(s):
    return {"name": s["stockName"], "code": s["itemCode"], "close": num(s["closePrice"]),
            "chg": num(s["fluctuationsRatio"]), "value": num(s.get("accumulatedTradingValue")),
            "cap": num(s.get("marketValue")), "mkt": "코스피" if s.get("sosok") == "0" else "코스닥"}


def index(code):
    b = get("/api/index/%s/basic" % code)
    days = get("/api/index/%s/price?pageSize=20&page=1" % code)
    closes = [num(d["closePrice"]) for d in days]
    t = get("/api/index/%s/trend" % code)
    return {"name": b["stockName"], "close": num(b["closePrice"]), "chg": num(b["fluctuationsRatio"]),
            "date": days[0]["localTradedAt"], "status": b.get("marketStatus"),
            "ret5": round((closes[0] / closes[5] - 1) * 100, 2) if len(closes) > 5 else None,
            "ret20": round((closes[0] / closes[-1] - 1) * 100, 2) if len(closes) > 1 else None,
            "ma20": round(sum(closes) / len(closes), 2),
            "high": num(days[0]["highPrice"]), "low": num(days[0]["lowPrice"]),
            "series": [[d["localTradedAt"], num(d["closePrice"])] for d in reversed(days)],
            "flow": {"bizdate": t.get("bizdate"), "개인": num(t.get("personalValue")),
                     "외국인": num(t.get("foreignValue")), "기관": num(t.get("institutionalValue"))}}


def main(pf_path, out):
    data = {"indices": [index("KOSPI"), index("KOSDAQ")]}
    try:
        fx = get("/front-api/marketIndex/productDetail?category=exchange&reutersCode=FX_USDKRW")["result"]
        data["usdkrw"] = {"close": num(fx.get("closePrice")), "chg": num(fx.get("fluctuationsRatio"))}
    except Exception:
        data["usdkrw"] = None

    groups = get("/api/stocks/industry?page=1&pageSize=100")["groups"]
    bizdate = data["indices"][0]["date"]
    os.makedirs(HIST, exist_ok=True)
    json.dump({g["name"]: num(g["changeRate"]) for g in groups},
              open(os.path.join(HIST, bizdate + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    past = sorted(glob.glob(os.path.join(HIST, "*.json")))[-5:]
    hist = [json.load(open(p, encoding="utf-8")) for p in past]
    sectors = []
    for g in groups:
        rets = [h[g["name"]] for h in hist if h.get(g["name"]) is not None]
        cum = 1.0
        for r in rets:
            cum *= 1 + r / 100
        sectors.append({"no": g["no"], "name": g["name"], "chg": num(g["changeRate"]), "n": g["totalCount"],
                        "rise": g["riseCount"], "fall": g["fallCount"],
                        "cum5": round((cum - 1) * 100, 2), "days": len(rets)})
    sectors.sort(key=lambda s: s["chg"], reverse=True)
    data["sectors"] = sectors

    # 오늘 강한 업종 + 누적 강한 업종의 주도주 (거래대금 순)
    pick = {s["no"]: s for s in sectors[:6]}
    pick.update({s["no"]: s for s in sorted(sectors, key=lambda s: s["cum5"], reverse=True)[:4]})
    leaders = {}
    for no, s in pick.items():
        st = [slim(x) for x in get("/api/stocks/industry/%d?page=1&pageSize=100" % no)["stocks"]]
        st = [x for x in st if x["value"] and x["cap"] and x["cap"] >= 1000]  # 시총 1,000억 이상
        st.sort(key=lambda x: x["value"], reverse=True)
        leaders[s["name"]] = st[:8]
    data["leaders"] = leaders
    data["gainers"] = {m: [slim(x) for x in get("/api/stocks/up/%s?page=1&pageSize=10" % m)["stocks"]]
                       for m in ("KOSPI", "KOSDAQ")}

    pf = json.load(open(pf_path, encoding="utf-8"))
    data["portfolio"] = [{"name": h["name"], "sec": h["sec"], "buy": h["buy"], "cur": h.get("cur"), "qty": h["qty"]}
                         for h in pf["holdings"]]
    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    k, q = data["indices"]
    print("%s 코스피 %s (%+.2f%%) 코스닥 %s (%+.2f%%) | 상위 업종: %s" % (
        k["date"], k["close"], k["chg"], q["close"], q["chg"], ", ".join(s["name"] for s in sectors[:5])))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
