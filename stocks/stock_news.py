#!/usr/bin/env python3
"""보유 종목별 최근 뉴스와 증권사 리포트 링크를 모은다 ('뉴스 · 리포트' 탭 재료).

사용법: python3 stocks/stock_news.py <portfolio.json> <out.json> [--targets <targets.json>] [--days 3] [--rdays 30]
- --targets 를 주면 '관심 종목'(보유 종목과 겹치지 않는 것)도 함께 모으고 watch: true 로 표시한다.
- 뉴스: 네이버 종목 뉴스에서 최근 --days 일 이내, 같은 기사 묶음은 첫 기사만, 종목당 최대 4개.
  제목·요약에 종목명이 없는 기사(시황 묶음 기사 등)는 뺀다.
- 리포트: 네이버 리서치(종목분석)에서 최근 --rdays 일 이내, 종목당 최대 3개.
- 결과: {"date","updated","items":[{name,code,news:[{t,src,dt,url}],reports:[{t,broker,dt,url}]}]}
  dt 는 "YYYY-MM-DD HH:MM"(리포트는 날짜만). 뉴스·리포트가 하나도 없는 종목은 뺀다.
"""
import html
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_prices as up  # noqa: E402


def fmt(s):
    s = str(s)
    return "%s-%s-%s" % (s[:4], s[4:6], s[6:8]) + (" %s:%s" % (s[8:10], s[10:12]) if len(s) >= 12 else "")


def main():
    a = sys.argv[1:]
    src, dst = a[0], a[1]
    days = int(a[a.index("--days") + 1]) if "--days" in a else 3
    rdays = int(a[a.index("--rdays") + 1]) if "--rdays" in a else 30
    now = datetime.now(up.KST)
    ncut = (now - timedelta(days=days)).strftime("%Y%m%d%H%M")
    rcut = (now - timedelta(days=rdays)).strftime("%Y%m%d")
    doc = json.load(open(src, encoding="utf-8"))
    codes = json.load(open(up.CODES, encoding="utf-8")) if os.path.exists(up.CODES) else {}
    stocks = [dict(h, watch=False) for h in doc["holdings"]]
    if "--targets" in a:
        t = json.load(open(a[a.index("--targets") + 1], encoding="utf-8"))
        held = {up.norm(h["name"]) for h in stocks}
        stocks += [{"name": g["name"], "code": g.get("code"), "watch": True}
                   for g in t.get("items", []) if up.norm(g["name"]) not in held]
    items, nn, nr = [], 0, 0
    for h in stocks:
        c = h.get("code") or codes.get(h["name"]) or up.lookup_code(h["name"])
        if not c:
            continue
        news, reports, seen = [], [], set()
        try:
            for grp in up.get_json("https://m.stock.naver.com/api/news/stock/%s?pageSize=20&page=1" % c):
                it = (grp.get("items") or [None])[0]
                if not it or str(it.get("datetime", "")) < ncut:
                    continue
                t = html.unescape(it.get("titleFull") or it.get("title") or "")
                text = up.norm(t + html.unescape(it.get("body") or ""))
                if up.norm(h["name"]) not in text or t in seen:
                    continue
                seen.add(t)
                news.append({"t": t, "src": it.get("officeName", ""), "dt": fmt(it["datetime"]),
                             "url": it.get("mobileNewsUrl") or "https://n.news.naver.com/mnews/article/%s/%s" % (it["officeId"], it["articleId"])})
                if len(news) >= 4:
                    break
        except Exception:
            pass
        try:
            for r in up.get_json("https://m.stock.naver.com/api/stock/%s/integration" % c).get("researches") or []:
                if str(r.get("wdt", "")) < rcut:
                    continue
                reports.append({"t": html.unescape(r.get("tit", "")), "broker": r.get("bnm", ""), "dt": fmt(r["wdt"]),
                                "url": "https://finance.naver.com/research/company_read.naver?nid=%s" % r["id"]})
                if len(reports) >= 3:
                    break
        except Exception:
            pass
        if news or reports:
            items.append({"name": h["name"], "code": c, "watch": h["watch"], "news": news, "reports": reports})
            nn += len(news)
            nr += len(reports)
    last = lambda x: max([n["dt"] for n in x["news"]] + [r["dt"] for r in x["reports"]])
    items.sort(key=last, reverse=True)
    out = {"date": now.strftime("%Y-%m-%d"), "updated": now.isoformat(timespec="seconds"),
           "days": days, "rdays": rdays, "items": items}
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("%d종목 · 뉴스 %d건 · 리포트 %d건" % (len(items), nn, nr))
    for x in items:
        if x["reports"]:
            print("  %s: %s" % (x["name"], " / ".join("%s %s" % (r["broker"], r["t"]) for r in x["reports"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
