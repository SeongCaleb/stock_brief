import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from v3_market_data import collect_snapshot, _get_csv_latest

class MarketDataTests(unittest.TestCase):
    def test_fred_csv(self):
        session = Mock()
        response = Mock()
        response.text = "observation_date,VIXCLS\n2026-10-20,27.2\n2026-10-21,.\n"
        session.get.return_value = response
        item = _get_csv_latest("VIXCLS", session, datetime(2026, 10, 23, tzinfo=timezone.utc))
        self.assertEqual(item["value"], 27.2)
        self.assertEqual(item["as_of"][:10], "2026-10-20")
    def test_missing_provider_is_safe(self):
        session = Mock()
        session.get.side_effect = TimeoutError("unavailable")
        finance = Mock()
        finance.Ticker.side_effect = ValueError("unavailable")
        item = collect_snapshot(session=session, finance=finance, watchlist=["JNJ"])
        self.assertEqual(item["assets"], {})
        self.assertEqual(item["asset_classes"], [])
        self.assertGreater(len(item["collection_warnings"]), 1)
    def test_stock_candidate_without_sec_header(self):
        session = Mock()
        session.get.side_effect = TimeoutError("FRED is temporarily unavailable")
        quote = {"as_of": "2026-10-23T00:00:00+00:00",
                 "source_url": "https://finance.yahoo.com/quote/V/",
                 "price": 100.0,
                 "return_3m_pct": 4.0,
                 "ma200_gap_pct": 2.0}
        date = datetime(2026, 10, 23, 16, tzinfo=timezone.utc)
        with patch.dict("os.environ", {"SEC_USER_AGENT": ""}), \
                patch("v3_market_data._history", side_effect=lambda yf, symbol, now: (symbol, dict(quote))), \
                patch("v3_market_data._safe_info", return_value={"forwardPE": 19, "shortName": "Test"}), \
                patch("v3_market_data._future_growth", return_value=14):
            snapshot = collect_snapshot(now=date, session=session, finance=Mock(), watchlist=["V"])
        self.assertIn("V", snapshot["assets"])
        self.assertEqual(snapshot["assets"]["V"]["financials"]["kind"], "vendor_estimates")
        self.assertIsNone(snapshot["assets"]["V"]["sec_filing"])
        self.assertEqual(snapshot["assets"]["V"]["candidate_status"], "매수 조건 검토")

    def test_invalid_tickers_filtered(self):
        session = Mock()
        session.get.side_effect = TimeoutError("offline")
        finance = Mock()
        finance.Ticker.side_effect = ValueError("offline")
        item = collect_snapshot(session=session, finance=finance, watchlist=["BAD/../../", "V"])
        self.assertEqual(item["assets"], {})

if __name__ == "__main__":
    unittest.main()
