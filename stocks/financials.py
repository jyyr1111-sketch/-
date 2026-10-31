#!/usr/bin/env python3
"""보유 종목 재무 상태를 정리한다 ('재무' 탭 재료).

사용법: python3 stocks/financials.py <portfolio.json> <out.json> [--targets <targets.json>]
- --targets 를 주면 관심 종목(보유와 겹치지 않는 것)도 정리하고 watch: true 로 표시한다.
- 3년 예측·현금흐름: 네이버 기업분석(navercomp.wisereport.co.kr) 주요재무정보 연간 표에서
  최근 실적 3년 + 예상 3년(E)의 매출·영업이익·순이익·영업활동현금흐름·FCF·부채비율·EPS·PER 을 fc 로 담는다.
- 네이버 종목 재무(연간·분기, 컨센서스 포함)에서 부채비율·당좌비율·유보율, 매출·영업이익·순이익,
  ROE·PER·PBR 을 모은다. 금액은 억원. 컨센서스(예상) 열은 키 끝에 "E" 를 붙인다.
- 등급: 신호별 점수 합산 — 부채비율(300%↑ 2, 200%↑ 1, 100%↑ 0.5), 당좌비율(30%↓ 2, 50%↓ 1, 100%↓ 0.5),
  최근 4분기 영업손실 합계 적자 2 / 최근 분기 적자 1, 올해 예상 영업적자 1 / 예상 감익 0.5.
  3점 이상 위험, 1.5점 이상 주의, 그 외 안정. 금융업은 부채비율·당좌비율 제외. 근거는 flags 에 남긴다.
- 현금흐름표·현금성자산은 이 자료원에 없어, 유동성은 당좌비율(현금화 쉬운 자산 ÷ 1년 안에 갚을 빚)과
  유보율(쌓아 둔 이익 ÷ 자본금)로 본다.
- 증권사 컨센서스 목표주가 평균(target)과 투자의견 평균(recomm, 5점 만점: 5 강력매수 · 4 매수 · 3 중립)도 함께 담는다.
- 결과: {"updated","items":[{name,code,sec,grade,flags,debt,quick,reserve,roe,per,pbr,annual,quarter,period,growth,turn,target,recomm,cur}]}
"""
import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_prices as up  # noqa: E402


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def table(code, kind):
    d = up.get_json("https://m.stock.naver.com/api/stock/%s/finance/%s" % (code, kind))
    info = d.get("financeInfo") or {}
    cols = [(t["key"], t["isConsensus"] == "Y") for t in info.get("trTitleList", [])]
    rows = {r["title"]: {k: num((r["columns"].get(k) or {}).get("value")) for k, _ in cols} for r in info.get("rowList", [])}
    return cols, rows


WR = "https://navercomp.wisereport.co.kr/v2/company/"
FC_ROWS = {"매출액": "매출액", "영업이익(발표기준)": "영업이익", "당기순이익": "당기순이익", "영업활동현금흐름": "영업현금흐름",
           "FCF": "FCF", "부채비율": "부채비율", "EPS(원)": "EPS", "PER(배)": "PER"}


def wise(code):
    """기업분석 주요재무정보(연간). 페이지에서 받은 토큰(encparam·id)과 쿠키로 표를 요청한다."""
    import http.cookiejar
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    ua = {"User-Agent": "Mozilla/5.0"}
    page = op.open(urllib.request.Request(WR + "c1010001.aspx?cmp_cd=" + code, headers=ua), timeout=20).read().decode("utf-8", "ignore")
    enc = re.search(r"encparam: *'([^']*)'", page)
    pid = re.search(r"id: *'([^']*)'", page)
    if not enc:
        return None
    url = WR + "ajax/cF1001.aspx?cmp_cd=%s&fin_typ=0&freq_typ=Y&encparam=%s&id=%s" % (code, enc.group(1), pid.group(1) if pid else "")
    hd = dict(ua, Referer=WR + "c1010001.aspx?cmp_cd=" + code)
    hd["X-Requested-With"] = "XMLHttpRequest"
    t = op.open(urllib.request.Request(url, headers=hd), timeout=20).read().decode("utf-8", "ignore")
    cell = lambda c: re.sub(r"<[^>]+>|\s+", " ", html.unescape(c)).strip()
    years, rows = [], {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        cs = [cell(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]
        if not cs:
            continue
        if not years and re.match(r"\d{4}/\d{2}", cs[0]):
            years = [c[:4] + ("E" if "(E)" in c else "") for c in cs]
        elif years and cs[0] in FC_ROWS and len(cs) == len(years) + 1:
            rows[FC_ROWS[cs[0]]] = [num(v) for v in cs[1:]]
    if not years or "매출액" not in rows:
        return None
    # 실적 3년 + 예상 연도만 남김
    act = [i for i, y in enumerate(years) if not y.endswith("E")][-3:]
    est = [i for i, y in enumerate(years) if y.endswith("E")]
    keep = act + est
    return {"years": [years[i] for i in keep], "rows": {k: [v[i] for i in keep] for k, v in rows.items()}}


def last_actual(cols, row):
    for k, e in reversed(cols):
        if not e and row.get(k) is not None:
            return k, row[k]
    return None, None


def series(cols, rows, title):
    return {(k + "E" if e else k): rows.get(title, {}).get(k) for k, e in cols}


def main(src, dst, tsrc=None):
    doc = json.load(open(src, encoding="utf-8"))
    codes = json.load(open(up.CODES, encoding="utf-8")) if os.path.exists(up.CODES) else {}
    stocks = [dict(h, watch=False) for h in doc["holdings"]]
    if tsrc:
        held = {up.norm(h["name"]) for h in stocks}
        for g in json.load(open(tsrc, encoding="utf-8")).get("items", []):
            if up.norm(g["name"]) not in held:
                stocks.append({"name": g["name"], "code": g.get("code"), "sec": g.get("sec"), "cur": g.get("cur"), "watch": True})
    items = []
    for h in stocks:
        if h.get("sec") == "ETF" or "KODEX" in h["name"] or "TIGER" in h["name"]:
            continue
        c = h.get("code") or codes.get(h["name"]) or up.lookup_code(h["name"])
        if not c:
            continue
        try:
            ac, ar = table(c, "annual")
            qc, qr = table(c, "quarter")
        except Exception:
            continue
        if not ar and not qr:
            continue
        fc = None
        try:
            fc = wise(c)
        except Exception:
            pass
        target = recomm = None
        try:
            ci = up.get_json("https://m.stock.naver.com/api/stock/%s/integration" % c).get("consensusInfo") or {}
            target, recomm = num(ci.get("priceTargetMean")), num(ci.get("recommMean"))
        except Exception:
            pass
        pk, debt = last_actual(qc, qr.get("부채비율", {}))
        _, quick = last_actual(qc, qr.get("당좌비율", {}))
        _, reserve = last_actual(qc, qr.get("유보율", {}))
        _, roe = last_actual(ac, ar.get("ROE", {}))
        annual = {t: series(ac, ar, t) for t in ("매출액", "영업이익", "당기순이익")}
        quarter = {t: series(qc, qr, t) for t in ("매출액", "영업이익")}
        ce = [k for k, e in ac if e]
        per = ar.get("PER", {}).get(ce[0]) if ce else None
        if per is None:
            per = last_actual(ac, ar.get("PER", {}))[1]
        pbr = last_actual(ac, ar.get("PBR", {}))[1]
        # 성장: 마지막 실적 연도 → 예상 연도 영업이익
        la, op_last = last_actual(ac, ar.get("영업이익", {}))
        op_e = ar.get("영업이익", {}).get(ce[0]) if ce else None
        growth, turn = None, None
        if op_last is not None and op_e is not None:
            if op_last > 0 and op_e > 0:
                growth = round((op_e / op_last - 1) * 100, 1)
            elif op_last <= 0 < op_e:
                turn = "흑자전환 예상"
            elif op_last > 0 >= op_e:
                turn = "적자전환 예상"
            else:
                turn = "적자 축소 예상" if op_e > op_last else "적자 확대 예상"
        qa = [qr.get("영업이익", {}).get(k) for k, e in qc if not e]
        qa = [x for x in qa if x is not None]
        last4 = sum(qa[-4:]) if len(qa) >= 4 else None
        # 신호마다 점수를 매겨 합산: 3점 이상 위험, 1.5점 이상 주의, 그 외 안정.
        # 증권·창투 등 금융업은 부채비율·당좌비율 구조가 달라 이 둘은 보지 않는다.
        fin = h.get("sec") == "금융" or any(w in h["name"] for w in ("증권", "투자", "금융", "은행", "보험"))
        flags, score = [], 0.0
        def add(pts, text):
            nonlocal score
            score += pts
            flags.append(text)
        if not fin and debt is not None:
            if debt >= 300:
                add(2, "부채비율 %.0f%% (300%% 이상)" % debt)
            elif debt >= 200:
                add(1, "부채비율 %.0f%% (200%% 이상)" % debt)
            elif debt >= 100:
                add(0.5, "부채비율 %.0f%% (100%% 이상)" % debt)
        if not fin and quick is not None:
            if quick < 30:
                add(2, "당좌비율 %.0f%% (단기 지급 여력 매우 부족)" % quick)
            elif quick < 50:
                add(1, "당좌비율 %.0f%% (단기 지급 여력 부족)" % quick)
            elif quick < 100:
                add(0.5, "당좌비율 %.0f%% (100%% 미만)" % quick)
        if last4 is not None and last4 < 0:
            add(2, "최근 4분기 영업손실 합계 %s억" % format(round(last4), ","))
        elif qa and qa[-1] < 0:
            add(1, "최근 분기 영업적자")
        if op_e is not None and op_e < 0:
            add(1, "올해 예상 영업이익 적자")
        elif growth is not None and growth < 0 and op_last and op_last > 0:
            add(0.5, "올해 예상 영업이익 %.0f%% 감소" % growth)
        if fc and not fin:
            yrs, fcf = fc["years"], fc["rows"].get("FCF") or []
            la_i = max((i for i, y in enumerate(yrs) if not y.endswith("E") and i < len(fcf) and fcf[i] is not None), default=None)
            if la_i is not None and fcf[la_i] < 0:
                add(0.5, "%s년 잉여현금흐름(FCF) %s억 적자" % (yrs[la_i], format(round(fcf[la_i]), ",")))
        if fin:
            flags.append("금융업이라 부채비율·당좌비율은 판단에서 제외")
        grade = "위험" if score >= 3 else "주의" if score >= 1.5 else "안정"
        if not flags:
            flags.append("부채·유동성·이익 모두 무난")
        items.append({"name": h["name"], "code": c, "sec": h.get("sec"), "grade": grade, "flags": flags,
                      "debt": debt, "quick": quick, "reserve": reserve, "roe": roe, "per": per, "pbr": pbr,
                      "period": pk, "annual": annual, "quarter": quarter, "growth": growth, "turn": turn, "score": score,
                      "target": target, "recomm": recomm, "cur": h.get("cur"), "watch": h["watch"], "fc": fc})
    order = {"위험": 0, "주의": 1, "안정": 2}
    items.sort(key=lambda x: (order[x["grade"]], -x["score"], -(x["debt"] or 0)))
    out = {"updated": datetime.now(up.KST).isoformat(timespec="seconds"), "items": items}
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    cnt = {g: sum(1 for x in items if x["grade"] == g) for g in order}
    print("%d종목(관심 %d) · 위험 %d · 주의 %d · 안정 %d · 예측 있는 종목 %d" % (len(items), sum(1 for x in items if x["watch"]), cnt["위험"], cnt["주의"], cnt["안정"],
          sum(1 for x in items if x["fc"] and any(y.endswith("E") and v is not None for y, v in zip(x["fc"]["years"], x["fc"]["rows"].get("영업이익", []))))))
    for x in items:
        if x["grade"] != "안정":
            print("  [%s] %s: %s" % (x["grade"], x["name"], " / ".join(x["flags"])))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    sys.exit(main(a[0], a[1], a[a.index("--targets") + 1] if "--targets" in a else None))
