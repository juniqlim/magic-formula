"""generate_html FCF 순위 로직 단위 테스트 (DB 비의존)."""

from generate_html import fcf_rows_from_records, fcf_yield_map


def _rec(code, name, ocf, capex, mcap, per=None, pbr=None):
    return {"stock_code": code, "name": name, "ocf": ocf, "capex": capex,
            "market_cap": mcap, "per": per, "pbr": pbr}


def test_sorts_by_fcf_yield_desc():
    records = [
        _rec("A", "에이", ocf=100, capex=0, mcap=1000),   # yield 10%
        _rec("B", "비", ocf=300, capex=0, mcap=1000),      # yield 30%
        _rec("C", "씨", ocf=200, capex=0, mcap=1000),      # yield 20%
    ]
    rows = fcf_rows_from_records(records)
    assert [r[0] for r in rows] == ["B", "C", "A"]


def test_excludes_nonpositive_fcf_and_bad_mcap():
    records = [
        _rec("A", "에이", ocf=100, capex=200, mcap=1000),  # FCF<0 제외
        _rec("B", "비", ocf=100, capex=0, mcap=0),         # 시총0 제외
        _rec("C", "씨", ocf=100, capex=None, mcap=1000),   # capex None 제외
        _rec("D", "디", ocf=100, capex=0, mcap=1000),      # 유효
    ]
    rows = fcf_rows_from_records(records)
    assert [r[0] for r in rows] == ["D"]


def test_row_format_and_ratios():
    # FCF = 200-50 = 150, 시총 1000 → FCF/시총 15.0%, 시총/FCF 6.7
    records = [_rec("A", "에이", ocf=200, capex=50, mcap=1000, per=5.0, pbr=1.0)]
    row = fcf_rows_from_records(records)[0]
    # [code, name, fcf억, 시총억, "FCF/시총%", "FCF/시총(전년)%", "시총/FCF", "PER", "ROE%"]
    assert row[0] == "A"
    assert row[4] == "15.0%"
    assert row[5] == "-"            # 전년 없음
    assert row[6] == "6.7"
    assert row[7] == "5.0"          # PER
    assert row[8] == "20.0%"        # ROE = pbr/per = 1/5 = 20%


def test_prev_year_yield_column():
    records = [_rec("A", "에이", ocf=200, capex=0, mcap=1000)]   # 20%
    prev = {"A": 0.35}
    row = fcf_rows_from_records(records, prev_yield=prev)[0]
    assert row[4] == "20.0%"
    assert row[5] == "35.0%"


def test_top_n_limit():
    records = [_rec(str(i), str(i), ocf=i + 1, capex=0, mcap=1000) for i in range(10)]
    rows = fcf_rows_from_records(records, top_n=3)
    assert len(rows) == 3


def test_fcf_yield_map_filters():
    records = [
        _rec("A", "에이", ocf=300, capex=100, mcap=1000),  # 20%
        _rec("B", "비", ocf=100, capex=200, mcap=1000),    # 제외
    ]
    m = fcf_yield_map(records)
    assert m == {"A": 0.2}
