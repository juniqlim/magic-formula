"""generate_html FCF 순위 로직 단위 테스트 (DB 비의존)."""

from generate_html import fcf_rows_from_records, fcf_yield_map, is_fcf_distorted


def _rec(code, name, ocf, capex, mcap, per=None, pbr=None, net_income=1):
    return {"stock_code": code, "name": name, "ocf": ocf, "capex": capex,
            "market_cap": mcap, "per": per, "pbr": pbr, "net_income": net_income}


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


def test_excludes_loss_making():
    records = [
        _rec("A", "에이", ocf=200, capex=0, mcap=1000, net_income=10),   # 흑자 유지
        _rec("B", "비", ocf=300, capex=0, mcap=1000, net_income=-5),     # 적자 제외
        _rec("C", "씨", ocf=200, capex=0, mcap=1000, net_income=0),      # 손익0 제외
        _rec("D", "디", ocf=200, capex=0, mcap=1000, net_income=None),   # 순익없음 제외
    ]
    rows = fcf_rows_from_records(records)
    assert [r[0] for r in rows] == ["A"]


def test_top_n_limit():
    records = [_rec(str(i), str(i), ocf=i + 1, capex=0, mcap=1000) for i in range(10)]
    rows = fcf_rows_from_records(records, top_n=3)
    assert len(rows) == 3


def test_is_fcf_distorted():
    # 금융: OCF에 자금흐름 섞임
    assert is_fcf_distorted("상상인저축은행")
    assert is_fcf_distorted("미래에셋증권")
    assert is_fcf_distorted("삼성생명보험")
    assert is_fcf_distorted("한국캐피탈")
    # 유통: 리스 착시
    assert is_fcf_distorted("롯데하이마트")
    assert is_fcf_distorted("현대백화점")
    assert is_fcf_distorted("GS홈쇼핑")
    # 정상 제조/서비스는 통과
    assert not is_fcf_distorted("일지테크")
    assert not is_fcf_distorted("서한")
    assert not is_fcf_distorted("HS화성")


def test_distorted_excluded_from_rows():
    records = [
        _rec("A", "일지테크", ocf=200, capex=0, mcap=1000),
        _rec("B", "롯데하이마트", ocf=500, capex=0, mcap=1000),
        _rec("C", "상상인저축은행", ocf=900, capex=0, mcap=1000),
    ]
    rows = fcf_rows_from_records(records)
    assert [r[0] for r in rows] == ["A"]


def test_fcf_yield_map_filters():
    records = [
        _rec("A", "에이", ocf=300, capex=100, mcap=1000),  # 20%
        _rec("B", "비", ocf=100, capex=200, mcap=1000),    # 제외
    ]
    m = fcf_yield_map(records)
    assert m == {"A": 0.2}
