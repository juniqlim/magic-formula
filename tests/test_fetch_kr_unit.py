import math
import sqlite3

import pytest

from fetch_kr import (
    _calc_growth_rate,
    _income_current_and_yoy_base,
    init_db,
    resolve_period_config,
    save_companies,
    save_market_caps,
    _to_int_amount,
)


class TestToIntAmount:
    def test_parses_numeric_string(self):
        assert _to_int_amount("1,234,567") == 1234567

    def test_invalid_returns_zero(self):
        assert _to_int_amount(None) == 0
        assert _to_int_amount("") == 0
        assert _to_int_amount("N/A") == 0


class TestGrowthRate:
    def test_basic_growth(self):
        result = _calc_growth_rate(120, 100)
        assert pytest.approx(result, rel=1e-6) == 0.2

    def test_zero_base_returns_none(self):
        assert _calc_growth_rate(120, 0) is None
        assert _calc_growth_rate(120, None) is None


class TestIncomeCurrentAndYoyBase:
    def test_annual_uses_thstrm_and_frmtrm(self):
        row = {
            "thstrm_amount": "200",
            "frmtrm_amount": "160",
        }
        current, yoy_base = _income_current_and_yoy_base(row)
        assert current == 200
        assert yoy_base == 160

    def test_quarterly_prefers_frmtrm_q_amount(self):
        row = {
            "thstrm_amount": "300",
            "frmtrm_q_amount": "240",
            "frmtrm_amount": "999",  # should be ignored when frmtrm_q exists
        }
        current, yoy_base = _income_current_and_yoy_base(row)
        assert current == 300
        assert yoy_base == 240


class TestResolvePeriodConfig:
    def test_annual_period_uses_business_report(self):
        config = resolve_period_config("2024")
        assert config == {
            "storage_key": "2024",
            "bsns_year": 2024,
            "reprt_code": "11011",
            "market_date": "20241230",
            "shares_year": "2024",
            "label": "2024년 사업보고서",
        }

    def test_q1_period_uses_first_quarter_report(self):
        config = resolve_period_config("2026Q1")
        assert config == {
            "storage_key": "2026Q1",
            "bsns_year": 2026,
            "reprt_code": "11013",
            "market_date": "20260331",
            "shares_year": "2026",
            "label": "2026년 1분기",
        }


class _FakeCompaniesDf:
    def __init__(self, rows):
        self._rows = rows

    def __len__(self):
        return len(self._rows)

    def iterrows(self):
        for idx, row in enumerate(self._rows):
            yield idx, row


class TestAuditTimestamps:
    def test_save_companies_stores_inserted_and_updated_at(self, tmp_path, monkeypatch):
        db_path = tmp_path / "audit.db"
        conn = init_db(str(db_path))

        timestamps = iter(["2026-05-10 18:00:01", "2026-05-10 18:00:02"])
        monkeypatch.setattr("fetch_kr._db_now", lambda: next(timestamps))

        save_companies(conn, _FakeCompaniesDf([
            {"stock_code": "005930", "corp_code": "00126380", "corp_name": "삼성전자"}
        ]))
        save_companies(conn, _FakeCompaniesDf([
            {"stock_code": "005930", "corp_code": "00126380", "corp_name": "삼성전자우"}
        ]))

        row = conn.execute("""
            SELECT corp_name, inserted_at, updated_at
            FROM companies
            WHERE stock_code = '005930'
        """).fetchone()
        conn.close()

        assert row == (
            "삼성전자우",
            "2026-05-10 18:00:01",
            "2026-05-10 18:00:02",
        )

    def test_save_market_caps_updates_updated_at_only(self, tmp_path, monkeypatch):
        db_path = tmp_path / "audit.db"
        conn = init_db(str(db_path))

        timestamps = iter(["2026-05-10 18:10:01", "2026-05-10 18:10:02"])
        monkeypatch.setattr("fetch_kr._db_now", lambda: next(timestamps))

        save_market_caps(conn, "2025", {"005930": 1000})
        save_market_caps(conn, "2025", {"005930": 2000})

        row = conn.execute("""
            SELECT market_cap, inserted_at, updated_at
            FROM financials
            WHERE stock_code = '005930' AND bsns_year = '2025'
        """).fetchone()
        conn.close()

        assert row == (
            2000,
            "2026-05-10 18:10:01",
            "2026-05-10 18:10:02",
        )
