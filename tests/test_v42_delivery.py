import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import main_v3

class RevisionDeliveryTests(unittest.TestCase):
    def test_revision_dedup_is_distinct_from_normal_delivery(self):
        recorded = {"sent_dates": ["2026-10-24"], "revision_sent_dates": []}
        with patch.object(main_v3, "_load_state", return_value=recorded), \
             patch.object(main_v3, "make_email", return_value=("2026-10-24", "<html></html>", set(), [], 0, 0, {}, {"seen_ids":[]})), \
             patch.object(main_v3, "send") as smtp, \
             patch.object(main_v3, "_save_state") as save_state, \
             patch.object(main_v3, "save_seen"), \
             patch("sys.argv", ["main_v3.py", "--send-revision"]), \
             patch.object(main_v3, "ANTHROPIC_API_KEY", "test"), \
             patch.object(main_v3, "NAVER_USER", "test"), \
             patch.object(main_v3, "NAVER_PASS", "test"), \
             patch.object(main_v3, "MAIL_TO", "test"):
            # Files for status are created only inside GitHub runner / test temp dir.
            from tempfile import TemporaryDirectory
            from os import chdir, getcwd
            old = getcwd()
            with TemporaryDirectory() as td:
                try:
                    chdir(td)
                    with patch.object(main_v3, "STATE_PATH", main_v3.Path("v3_delivery_state.json")), \
                         patch.object(main_v3, "REPORT_DIR", main_v3.Path("reports")):
                        main_v3.main()
                finally:
                    chdir(old)
        smtp.assert_called_once()
        self.assertIn("2026-10-24", save_state.call_args[0][0]["revision_sent_dates"])
        self.assertEqual(save_state.call_args[0][0]["sent_dates"], ["2026-10-24"])

if __name__ == "__main__":
    unittest.main()
