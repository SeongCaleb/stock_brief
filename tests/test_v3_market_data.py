import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
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
    def test_invalid_tickers_filtered(self):
        session = Mock()
        session.get.side_effect = TimeoutError("offline")
        finance = Mock()
        finance.Ticker.side_effect = ValueError("offline")
        item = collect_snapshot(session=session, finance=finance, watchlist=["BAD/../../", "V"])
        self.assertEqual(item["assets"], {})

if __name__ == "__main__":
    unittest.main()
