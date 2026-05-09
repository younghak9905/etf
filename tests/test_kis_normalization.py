from __future__ import annotations

import sys
import types
from unittest import TestCase

sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(AsyncClient=object, HTTPError=Exception),
)

from datetime import date

from app.clients.kis import (
    _payload_rows,
    _payload_summary,
    _quote_from_candles,
    _to_float,
    _to_str,
)
from app.models.market import Candle


class KISNormalizationTest(TestCase):
    def test_to_float_uses_first_available_alias(self) -> None:
        self.assertEqual(_to_float({"base": "88.12"}, "last", "base"), 88.12)

    def test_to_float_raises_with_available_fields(self) -> None:
        with self.assertRaisesRegex(KeyError, "available fields: base"):
            _to_float({"base": "88.12"}, "last")

    def test_quote_from_candles_uses_latest_daily_bar(self) -> None:
        quote = _quote_from_candles(
            [
                Candle(date(2026, 5, 7), open=10, high=11, low=9, close=10.5, volume=100),
                Candle(date(2026, 5, 8), open=11, high=12, low=10, close=11.5, volume=200),
            ]
        )

        self.assertEqual(quote["current_price"], 11.5)
        self.assertEqual(quote["prev_close"], 10.5)
        self.assertEqual(quote["day_high"], 12)
        self.assertEqual(quote["day_low"], 10)
        self.assertEqual(quote["volume"], 200)

    def test_quote_from_candles_can_use_intraday_price_without_daily_rows(self) -> None:
        quote = _quote_from_candles([], current_price=88.5)

        self.assertEqual(quote["current_price"], 88.5)
        self.assertEqual(quote["day_high"], 88.5)
        self.assertEqual(quote["day_low"], 88.5)
        self.assertEqual(quote["volume"], 0.0)

    def test_payload_rows_accepts_output_alias(self) -> None:
        self.assertEqual(_payload_rows({"output": [{"xymd": "20260508"}]}, "output2", "output"), [{"xymd": "20260508"}])

    def test_payload_rows_accepts_dict_alias(self) -> None:
        self.assertEqual(_payload_rows({"output1": {"xymd": "20260508"}}, "output2", "output1"), [{"xymd": "20260508"}])

    def test_payload_summary_includes_nested_shape(self) -> None:
        self.assertIn(
            "output2=list(len=0)",
            _payload_summary({"output1": {"rsym": "DNASQLD"}, "output2": []}),
        )

    def test_to_str_uses_first_available_alias(self) -> None:
        self.assertEqual(_to_str({"stck_bsop_date": "20260508"}, "xymd", "stck_bsop_date"), "20260508")
