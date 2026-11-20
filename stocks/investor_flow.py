#!/usr/bin/env python3
"""보유 종목 중 외국인·기관이 같은 날 함께 순매수한 종목을 고른다 ('내 포트폴리오' 탭 재료).

사용법: python3 stocks/investor_flow.py <portfolio.json> <out.json>
- 네이버 종목별 투자자 동향(최근 거래일 확정치)을 본다. 당일 수치는 장 마감 뒤 저녁~다음 날 아침에
  올라오므로, 아침에 돌리면 전 거래일 기준이 된다.
- mon: 보유 전 종목의 최근 12개월(이번 달 포함) 월별 외국인·기관 순매수 합계.
  {name, code, m: {"YYYY-MM": [외국인 주, 기관 주, 외국인 억원, 기관 억원]}} — 억원은 일별 순매수 × 그날 종가의 합.
  페이지에서 월 범위를 골라 더해 보여준다. 연기금은 네이버 종목별 자료에 없어 담지 않는다.
- 결과: {"date","updated","checked","items":[...],"frgnRun":[...],"organRun":[...],"mon":[...],"months":[...]}
  items 는 외국인·기관 동시 순매수, frgnRun/organRun 은 외국인/기관이 RUN(4)거래일 이상 연속 순매수한 종목.
  각 항목 {name,code,close,chg,frgn,organ,frgnAmt,organAmt,streak,fStreak,oStreak,frgn5,organ5}
  수량은 주, 금액(Amt)은 수량 × 종가로 어림한 억원. streak 은 둘이 함께, fStreak/oStreak 은 각자 연속 순매수한 거래일 수.
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_prices as up  # noqa: E402

RUN = 4


def num(v):
    return int(str(v or 0).replace(",", "").replace("+", "") or 0)


def out_day(d):
    return "%s-%s-%s" % (d[:4], d[4:6], d[6:])


def main(src, dst):
    doc = json.load(open(src, encoding="utf-8"))
    codes = json.load(open(up.CODES, encoding="utf-8")) if os.path.exists(up.CODES) else {}
    rows, dates, checked = [], [], 0
    for h in doc["holdings"]:
        c = codes.get(h["name"]) or up.lookup_code(h["name"])
        if not c:
            continue
        try:
            t = up.get_json("https://m.stock.naver.com/api/stock/%s/trend?pageSize=60" % c)
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
    def run(t, ok):
        n = 0
        for r in t:
            if not ok(r):
                break
            n += 1
        return n

    # 최근 12개월 월별 합계: 앞에서 받은 60거래일 뒤로 bizdate 를 넘겨 가며 1년치를 더 받는다
    y, mo = int(day[:4]), int(day[4:6])
    months = []
    for _ in range(12):
        months.append("%04d-%02d" % (y, mo))
        y, mo = (y, mo - 1) if mo > 1 else (y - 1, 12)
    months.reverse()
    since = months[0].replace("-", "") + "01"
    mon = []
    for h, c, t in rows:
        if t[0]["bizdate"] != day:
            continue
        hist = list(t)
        while hist and hist[-1]["bizdate"] > since and len(hist) < 320:
            try:
                more = up.get_json("https://m.stock.naver.com/api/stock/%s/trend?pageSize=60&bizdate=%s" % (c, hist[-1]["bizdate"]))
            except Exception:
                break
            more = [x for x in more if x["bizdate"] < hist[-1]["bizdate"]]
            if not more:
                break
            hist += more
        m = {}
        for x in hist:
            if x["bizdate"] < since:
                continue
            k = x["bizdate"][:4] + "-" + x["bizdate"][4:6]
            v = m.setdefault(k, [0, 0, 0.0, 0.0])
            f, o, cp = num(x["foreignerPureBuyQuant"]), num(x["organPureBuyQuant"]), num(x["closePrice"])
            v[0] += f
            v[1] += o
            v[2] += f * cp / 1e8
            v[3] += o * cp / 1e8
        mon.append({"name": h["name"], "code": c, "m": {k: [v[0], v[1], round(v[2], 1), round(v[3], 1)] for k, v in m.items()}})

    items, frun, orun = [], [], []
    for h, c, t in rows:
        d = t[0]
        if d["bizdate"] != day:
            continue
        f, o, close = num(d["foreignerPureBuyQuant"]), num(d["organPureBuyQuant"]), num(d["closePrice"])
        streak = run(t, lambda r: num(r["foreignerPureBuyQuant"]) > 0 and num(r["organPureBuyQuant"]) > 0)
        fs = run(t, lambda r: num(r["foreignerPureBuyQuant"]) > 0)
        os_ = run(t, lambda r: num(r["organPureBuyQuant"]) > 0)
        if not (streak or fs >= RUN or os_ >= RUN):
            continue
        prev = num(t[1]["closePrice"]) if len(t) > 1 else 0
        x = {"name": h["name"], "code": c, "close": close,
                      "chg": round((close / prev - 1) * 100, 2) if prev else None,
                      "frgn": f, "organ": o, "frgnAmt": round(f * close / 1e8, 1), "organAmt": round(o * close / 1e8, 1),
                      "streak": streak, "fStreak": fs, "oStreak": os_,
                      "frgnSum": round(sum(num(r["foreignerPureBuyQuant"]) * num(r["closePrice"]) for r in t[:fs]) / 1e8, 1),
                      "organSum": round(sum(num(r["organPureBuyQuant"]) * num(r["closePrice"]) for r in t[:os_]) / 1e8, 1),
                      "frgn5": sum(num(r["foreignerPureBuyQuant"]) for r in t[:5]),
                      "organ5": sum(num(r["organPureBuyQuant"]) for r in t[:5])}
        if streak:
            items.append(x)
        if fs >= RUN:
            frun.append(x)
        if os_ >= RUN:
            orun.append(x)
    items.sort(key=lambda x: -(x["frgnAmt"] + x["organAmt"]))
    frun.sort(key=lambda x: (-x["fStreak"], -x["frgnSum"]))
    orun.sort(key=lambda x: (-x["oStreak"], -x["organSum"]))
    out = {"date": "%s-%s-%s" % (day[:4], day[4:6], day[6:]), "updated": datetime.now(up.KST).isoformat(timespec="seconds"),
           "checked": checked, "items": items,
           "frgnRun": frun, "organRun": orun, "run": RUN,
           "mon": mon, "months": months}
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("%s 기준 · %d종목 확인 · 외국인·기관 동시 순매수 %d종목" % (out["date"], checked, len(items)))
    for x in items:
        print("  %s  외 %+d주(%.1f억) 기 %+d주(%.1f억) 연속 %d일" % (x["name"], x["frgn"], x["frgnAmt"], x["organ"], x["organAmt"], x["streak"]))
    print("외국인 %d일+ 연속: %s" % (RUN, ", ".join("%s %d일(%.1f억)" % (x["name"], x["fStreak"], x["frgnSum"]) for x in frun) or "-"))
    print("기관 %d일+ 연속: %s" % (RUN, ", ".join("%s %d일(%.1f억)" % (x["name"], x["oStreak"], x["organSum"]) for x in orun) or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
