import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from v5_decision import classify_market, allocation, scenarios, evaluate_candidate, \
    build_decisions, observed_performance, update_history
from v5_email import render_v5


def metric(value, date="2026-10-27"):
    return {"value": value, "as_of": date+"T00:00:00+00:00",
            "source_url":"https://fred.stlouisfed.org/series/VIXCLS"}


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,27,6,tzinfo=timezone.utc)
        self.snapshot = {"macro": {
            "vix":metric(16), "high_yield_spread_pct":metric(2.7),
            "us_10y_yield_pct":metric(4.1), "spy_200dma_gap_pct":metric(4)
        }, "asset_classes":[{"ticker":"VOO","price":600,"return_3m_pct":5,
            "as_of":"2026-10-26T00:00:00+00:00"}],
           "watchlist":[], "assets":{}, "collection_warnings":[]}
        self.candidate = {
            "ticker":"XYZ", "name":"Example", "sector":"Technology",
            "market_info":{"price":200,"return_3m_pct":7,"below_52w_high_pct":-6},
            "valuation_info":{"forward_pe":18,"peer_forward_pe_median":22,
                              "expected_earnings_growth_pct":35},
            "detail":{"revenue_growth_yoy_pct":20,"operating_margin_pct":28,
                      "fcf_yield_pct":6},
            "quote_date":"2026-10-26","risk_tags":[], "sources":["https://finance.yahoo.com/quote/XYZ/"]
        }

    def test_regime_four_states_and_missing(self):
        s=self.snapshot
        self.assertEqual(classify_market(s,self.now)["code"],"risk_on")
        s["macro"]["vix"]["value"]=34
        s["macro"]["high_yield_spread_pct"]["value"]=6
        self.assertEqual(classify_market(s,self.now)["code"],"stress")
        s["macro"]["vix"]["value"]=29
        s["macro"]["high_yield_spread_pct"]["value"]=4.5
        self.assertEqual(classify_market(s,self.now)["code"],"risk_off")
        s["macro"]["vix"]["value"]=24
        s["macro"]["high_yield_spread_pct"]["value"]=3.8
        self.assertEqual(classify_market(s,self.now)["code"],"neutral")
        del s["macro"]["vix"]
        self.assertEqual(classify_market(s,self.now)["code"],"unknown")

    def test_scenario_math_and_no_fabricated_prices(self):
        x=scenarios(self.candidate)
        self.assertEqual(x["anchor_price"],200)
        self.assertEqual(x["cases"]["base"]["price"],200)
        self.assertLess(x["cases"]["bear"]["price"],200)
        self.assertGreater(x["cases"]["bull"]["price"],200)
        item=dict(self.candidate)
        item["valuation_info"]={}
        self.assertIsNone(scenarios(item))

    def test_allocation_sum_and_daily_limit(self):
        neutral={"cash_short":45,"us_index":25,"international":15,"single_stocks":10,"gold":5}
        alloc=allocation({"code":"stress"},neutral)
        self.assertEqual(sum(alloc["weights"].values()),100)
        self.assertTrue(all(abs(v-neutral[k])<=5 for k,v in alloc["weights"].items()))
        self.assertFalse(alloc["investable"])

    def test_unknown_market_never_buy_now(self):
        result=evaluate_candidate(self.candidate,{"code":"unknown"})
        self.assertNotEqual(result["action_v5"],"분할 매수 검토")
        self.assertIn("score_v5",result)

    def test_track_buy_wait_and_excess_return(self):
        s=self.snapshot
        s["assets"]["XYZ"]={"market":{"price":220}}
        risk=classify_market(s,self.now)
        decisions,all_decisions=build_decisions(s,risk,[self.candidate])
        alloc=allocation(risk)
        history,changes=update_history({},all_decisions,s,risk,alloc,self.now)
        self.assertEqual(len(history["observations"]),1)
        self.assertIn("action",history["observations"][0])
        self.assertEqual(changes,[])
        s["assets"]["XYZ"]["market"]["price"]=242
        s["asset_classes"][0]["price"]=630
        outcomes=observed_performance(history,s)
        self.assertEqual(len(outcomes),1)
        self.assertAlmostEqual(outcomes[0]["price_return_pct"],10.0)
        self.assertAlmostEqual(outcomes[0]["benchmark_price_return_pct"],5)
        self.assertEqual(outcomes[0]["excess_pct"],5)
        self.assertIn("observed_max_pct",outcomes[0])

    def test_report_full_sections(self):
        market=classify_market(self.snapshot,self.now)
        alloc=allocation(market)
        candidate=evaluate_candidate(self.candidate,market)
        day,html=render_v5([],self.snapshot,market,alloc,[candidate],[candidate],
                         {},[],[],self.now)
        self.assertIn("V5",html)
        self.assertIn("매수",html)
        self.assertIn("가격 민감도",html)
        self.assertIn("추천과",html)
        self.assertIn("신용",html)
        self.assertEqual(day,"2026-10-27")

if __name__=="__main__":
    unittest.main()
