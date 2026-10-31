#!/usr/bin/env python3
"""보유 종목 재무 상태를 정리한다 ('재무' 탭 재료).

사용법: python3 stocks/financials.py <portfolio.json> <out.json>
- 네이버 종목 재무(연간·분기, 컨센서스 포함)에서 부채비율·당좌비율·유보율, 매출·영업이익·순이익,
  ROE·PER·PBR 을 모은다. 금액은 억원. 컨센서스(예상) 열은 키 끝에 "E" 를 붙인다.
- 등급: 신호별 점수 합산 — 부채비율(300%↑ 2, 200%↑ 1, 100%↑ 0.5), 당좌비율(30%↓ 2, 50%↓ 1, 100%↓ 0.5),
  최근 4분기 영업손실 합계 적자 2 / 최근 분기 적자 1, 올해 예상 영업적자 1 / 예상 감익 0.5.
  3점 이상 위험, 1.5점 이상 주의, 그 외 안정. 금융업은 부채비율·당좌비율 제외. 근거는 flags 에 남긴다.
- 현금흐름표·현금성자산은 이 자료원에 없어, 유동성은 당좌비율(현금화 쉬운 자산 ÷ 1년 안에 갚을 빚)과
  유보율(쌓아 둔 이익 ÷ 자본금)로 본다.
- 결과: {"updated","items":[{name,code,sec,grade,flags,debt,quick,reserve,roe,per,pbr,annual,quarter,period,growth}]}
"""
import json
import os
import sys
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


def last_actual(cols, row):
    for k, e in reversed(cols):
        if not e and row.get(k) is not None:
            return k, row[k]
    return None, None


def series(cols, rows, title):
    return {(k + "E" if e else k): rows.get(title, {}).get(k) for k, e in cols}


def main(src, dst):
    doc = json.load(open(src, encoding="utf-8"))
    codes = json.load(open(up.CODES, encoding="utf-8")) if os.path.exists(up.CODES) else {}
    items = []
    for h in doc["holdings"]:
        if h.get("sec") == "ETF" or "KODEX" in h["name"] or "TIGER" in h["name"]:
            continue
        c = codes.get(h["name"]) or up.lookup_code(h["name"])
        if not c:
            continue
        try:
            ac, ar = table(c, "annual")
            qc, qr = table(c, "quarter")
        except Exception:
            continue
        if not ar and not qr:
            continue
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
        if fin:
            flags.append("금융업이라 부채비율·당좌비율은 판단에서 제외")
        grade = "위험" if score >= 3 else "주의" if score >= 1.5 else "안정"
        if not flags:
            flags.append("부채·유동성·이익 모두 무난")
        items.append({"name": h["name"], "code": c, "sec": h.get("sec"), "grade": grade, "flags": flags,
                      "debt": debt, "quick": quick, "reserve": reserve, "roe": roe, "per": per, "pbr": pbr,
                      "period": pk, "annual": annual, "quarter": quarter, "growth": growth, "turn": turn, "score": score})
    order = {"위험": 0, "주의": 1, "안정": 2}
    items.sort(key=lambda x: (order[x["grade"]], -x["score"], -(x["debt"] or 0)))
    out = {"updated": datetime.now(up.KST).isoformat(timespec="seconds"), "items": items}
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    cnt = {g: sum(1 for x in items if x["grade"] == g) for g in order}
    print("%d종목 · 위험 %d · 주의 %d · 안정 %d" % (len(items), cnt["위험"], cnt["주의"], cnt["안정"]))
    for x in items:
        if x["grade"] != "안정":
            print("  [%s] %s: %s" % (x["grade"], x["name"], " / ".join(x["flags"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
