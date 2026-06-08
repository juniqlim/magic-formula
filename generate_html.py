"""index.html의 JS 데이터 배열을 DB 기반으로 재생성."""

import json
import os
import re
import sqlite3

from screener import load_stocks_from_db, rank_stocks, screen_dcf, DB_PATH
from ultra_screener import load_ultra_stocks_from_db, rank_ultra

TOP_N_ULTRA = 100
TOP_N_DCF = 100
TOP_N_MF = 100


def _pct(val):
    """숫자를 '12.3%' 문자열로. None이면 '-'."""
    if val is None:
        return "-"
    return f"{val * 100:.1f}%"


def _roe(per, pbr):
    """ROE = PBR / PER. 둘 중 하나라도 없거나 0이면 '-'."""
    if not per or not pbr or per <= 0:
        return "-"
    return f"{pbr / per * 100:.1f}%"


def _per_str(per):
    if not per or per <= 0:
        return "-"
    return f"{per:.1f}"


def _억(val):
    """원 단위 → 억 단위 정수."""
    return round(val / 1e8)


def build_mcap(bsns_year):
    """mcap25: {stock_code: market_cap_억}."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT stock_code, market_cap FROM financials WHERE bsns_year = ? AND market_cap > 0",
        (bsns_year,),
    ).fetchall()
    conn.close()
    return {code: _억(mcap) for code, mcap in rows}


def build_ultra(bsns_year, top_n=TOP_N_ULTRA):
    """ultra25: [[stock_code, name, f_score, rank_sum, 1/PER, 1/PBR, "GP/A%", "vol%", "PER", "ROE%"], ...]."""
    stocks = load_ultra_stocks_from_db(bsns_year)
    ranked = rank_ultra(stocks)
    rows = []
    for s in ranked[:top_n]:
        inv_per = round(s.get("inverse_per") or 0, 3)
        inv_pbr = round(s.get("inverse_pbr") or 0, 3)
        gpa = _pct(s.get("gpa"))
        vol = _pct(s.get("price_volatility")) if s.get("price_volatility") is not None else "N/A"
        per_s = _per_str(s.get("per"))
        roe_s = _roe(s.get("per"), s.get("pbr"))
        rows.append([
            s["stock_code"], s["name"], s["f_score"], s["ultra_rank"],
            inv_per, inv_pbr, gpa, vol, per_s, roe_s,
        ])
    return rows


def build_dcf(bsns_year, top_n=TOP_N_DCF):
    """dcf: [[stock_code, name, rev_억, op_억, fcf_억, fair_price, cur_price, "upside%", "PER", "ROE%"], ...]."""
    results = screen_dcf(bsns_year, top_n=top_n)
    # PER/ROE는 DB에서 직접 조회
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    per_map = {}
    for r in conn.execute(
        "SELECT stock_code, per, pbr FROM financials WHERE bsns_year = ?", (bsns_year,)
    ).fetchall():
        per_map[r["stock_code"]] = (r["per"], r["pbr"])
    conn.close()

    rows = []
    for r in results:
        per, pbr = per_map.get(r["stock_code"], (None, None))
        rows.append([
            r["stock_code"], r["name"],
            _억(r["revenue"]), _억(r["operating_income"]), _억(r["fcf"]),
            round(r["dcf_price"], 2), round(r["current_price"], 2),
            _pct(r["upside"]),
            _per_str(per), _roe(per, pbr),
        ])
    return rows


TOP_N_FCF = 100


def fcf_yield_map(records):
    """{stock_code: FCF/시총}. FCF>0, 시총>0 종목만."""
    out = {}
    for r in records:
        mcap = r.get("market_cap")
        ocf = r.get("ocf")
        capex = r.get("capex")
        if not mcap or mcap <= 0 or ocf is None or capex is None:
            continue
        fcf = ocf - capex
        if fcf <= 0:
            continue
        out[r["stock_code"]] = fcf / mcap
    return out


def fcf_rows_from_records(records, top_n=TOP_N_FCF, prev_yield=None):
    """FCF 수익률 순위 행 생성 (순수 함수, DB 비의존).

    records: [{stock_code, name, ocf, capex, market_cap, per, pbr}, ...]
    prev_yield: {stock_code: 전년도 FCF/시총} (옵션).
    반환: [[stock_code, name, fcf_억, mcap_억, "FCF/시총%", "FCF/시총(전년)%",
            "시총/FCF", "PER", "ROE%"], ...]
          FCF/시총 내림차순 정렬, 상위 top_n개.
    """
    prev_yield = prev_yield or {}
    out = []
    for r in records:
        mcap = r.get("market_cap")
        ocf = r.get("ocf")
        capex = r.get("capex")
        if not mcap or mcap <= 0 or ocf is None or capex is None:
            continue
        fcf = ocf - capex
        if fcf <= 0:
            continue
        fcf_yield = fcf / mcap
        prev = prev_yield.get(r["stock_code"])
        prev_str = f"{prev * 100:.1f}%" if prev is not None else "-"
        out.append({
            "yield": fcf_yield,
            "row": [
                r["stock_code"], r["name"], _억(fcf), _억(mcap),
                f"{fcf_yield * 100:.1f}%", prev_str, f"{1 / fcf_yield:.1f}",
                _per_str(r.get("per")), _roe(r.get("per"), r.get("pbr")),
            ],
        })
    out.sort(key=lambda x: x["yield"], reverse=True)
    return [x["row"] for x in out[:top_n]]


def _fcf_records(bsns_year):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT f.stock_code, c.corp_name AS name,
               f.operating_cash_flow AS ocf, f.capex, f.market_cap, f.per, f.pbr
        FROM financials f JOIN companies c ON c.stock_code = f.stock_code
        WHERE f.bsns_year = ?
        """,
        (bsns_year,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_fcf(bsns_year, prev_year=None, top_n=TOP_N_FCF):
    """fcf25: FCF/시총 상위 종목. 연말 기준. prev_year 전년도 FCF/시총 병기."""
    records = _fcf_records(bsns_year)
    prev = fcf_yield_map(_fcf_records(prev_year)) if prev_year else None
    return fcf_rows_from_records(records, top_n, prev_yield=prev)


def build_mf(bsns_year, top_n=TOP_N_MF):
    """mf: [[stock_code, name, rev_억, op_억, "ROIC%", "EY%", combined_rank, "PER", "ROE%"], ...]."""
    stocks = load_stocks_from_db(bsns_year)
    ranked = rank_stocks(stocks)
    # PER/ROE
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    per_map = {}
    for r in conn.execute(
        "SELECT stock_code, per, pbr FROM financials WHERE bsns_year = ?", (bsns_year,)
    ).fetchall():
        per_map[r["stock_code"]] = (r["per"], r["pbr"])
    conn.close()

    rows = []
    for s in ranked[:top_n]:
        per, pbr = per_map.get(s["stock_code"], (None, None))
        rows.append([
            s["stock_code"], s["name"],
            _억(s.get("revenue", 0)), _억(s["ebit"]),
            _pct(s["roic"]), _pct(s["earnings_yield"]),
            s["magic_rank"],
            _per_str(per), _roe(per, pbr),
        ])
    return rows


def to_js(name, data):
    """Python 데이터를 JS 변수 할당문으로 변환."""
    return f"const {name}={json.dumps(data, ensure_ascii=False)};"


def main():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, "r") as f:
        html = f.read()

    print("Building ultra25...")
    ultra25 = build_ultra("2025")
    print("Building ultra24...")
    ultra24 = build_ultra("2024")
    print("Building dcf25...")
    dcf25 = build_dcf("2025")
    print("Building dcf24...")
    dcf24 = build_dcf("2024")
    print("Building mf25...")
    mf25 = build_mf("2025")
    print("Building mf24...")
    mf24 = build_mf("2024")
    print("Building fcf25...")
    fcf25 = build_fcf("2025", prev_year="2024")
    print("Building mcap25...")
    mcap25 = build_mcap("2025")

    replacements = {
        "ultra25": ultra25,
        "ultra24": ultra24,
        "dcf25": dcf25,
        "dcf24": dcf24,
        "mf25": mf25,
        "mf24": mf24,
        "fcf25": fcf25,
        "mcap25": mcap25,
    }

    for name, data in replacements.items():
        pattern = re.compile(rf"^const {name}=.*?;$", re.MULTILINE)
        new_line = to_js(name, data)
        html, count = pattern.subn(new_line, html)
        if count == 0:
            print(f"WARNING: const {name}= not found in HTML!")
        else:
            print(f"  Replaced {name} ({count})")

    # Update "3분기 기준" → "사업보고서 기준" for 2025 tabs
    html = html.replace("2025년 3분기 기준", "2025년 사업보고서 기준")

    with open(html_path, "w") as f:
        f.write(html)
    print(f"Done. Updated {html_path}")


if __name__ == "__main__":
    main()
