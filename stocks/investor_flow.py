#!/usr/bin/env python3
"""보유 종목 중 외국인·기관이 같은 날 함께 순매수한 종목을 고른다 ('내 포트폴리오' 탭 재료).

사용법: python3 stocks/investor_flow.py <portfolio.json> <out.json>
- 네이버 종목별 투자자 동향(최근 거래일 확정치)을 본다. 당일 수치는 장 마감 뒤 저녁~다음 날 아침에
  올라오므로, 아침에 돌리면 전 거래일 기준이 된다.
- 결과: {"date","updated","checked","items":[{name,code,close,chg,frgn,organ,frgnAmt,organAmt,streak,frgn5,organ5}]}
  수량은 주, 금액(Amt)은 수량 × 종가로 어림한 억원. streak 은 둘이 함께 순매수한 연속 거래일 수.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_prices as up  # noqa: E402


def num(v):
    return int(str(v or 0).replace(",", "").replace("+", "") or 0)


def main(src, dst):
    doc = json.load(open(src, encoding="utf-8"))
    codes = json.load(open(up.CODES, encoding="utf-8")) if os.path.exists(up.CODES) else {}
    rows, dates, checked = [], [], 0
    for h in doc["holdings"]:
        c = codes.get(h["name"]) or up.lookup_code(h["name"])
        if not c:
            continue
        try:
            t = up.get_json("https://m.stock.naver.com/api/stock/%s/trend?pageSize=10" % c)
        except Exception:
            continue
        if not t:
            continue
        checked += 1
        dates.append(t[0]["bizdate"])
        rows.append((h, c, t))
    if not dates:
        print("투자자 동향을 받지 못함")
        return 1
    day = max(dates)
    items = []
    for h, c, t in rows:
        d = t[0]
        if d["bizdate"] != day:
            continue
        f, o, close = num(d["foreignerPureBuyQuant"]), num(d["organPureBuyQuant"]), num(d["closePrice"])
        if f <= 0 or o <= 0:
            continue
        streak = 0
        for r in t:
            if num(r["foreignerPureBuyQuant"]) > 0 and num(r["organPureBuyQuant"]) > 0:
                streak += 1
            else:
                break
        prev = num(t[1]["closePrice"]) if len(t) > 1 else 0
        items.append({"name": h["name"], "code": c, "close": close,
                      "chg": round((close / prev - 1) * 100, 2) if prev else None,
                      "frgn": f, "organ": o, "frgnAmt": round(f * close / 1e8, 1), "organAmt": round(o * close / 1e8, 1),
                      "streak": streak,
                      "frgn5": sum(num(r["foreignerPureBuyQuant"]) for r in t[:5]),
                      "organ5": sum(num(r["organPureBuyQuant"]) for r in t[:5])})
    items.sort(key=lambda x: -(x["frgnAmt"] + x["organAmt"]))
    out = {"date": "%s-%s-%s" % (day[:4], day[4:6], day[6:]), "updated": datetime.now(up.KST).isoformat(timespec="seconds"),
           "checked": checked, "items": items}
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("%s 기준 · %d종목 확인 · 외국인·기관 동시 순매수 %d종목" % (out["date"], checked, len(items)))
    for x in items:
        print("  %s  외 %+d주(%.1f억) 기 %+d주(%.1f억) 연속 %d일" % (x["name"], x["frgn"], x["frgnAmt"], x["organ"], x["organAmt"], x["streak"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
