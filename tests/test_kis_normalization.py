from __future__ import annotations

import sys
import types
from unittest import TestCase

sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(AsyncClient=object, HTTPError=Exception),
)

from app.clients.kis import _to_float


class KISNormalizationTest(TestCase):
    def test_to_float_uses_first_available_alias(self) -> None:
        self.assertEqual(_to_float({"base": "88.12"}, "last", "base"), 88.12)

    def test_to_float_raises_with_available_fields(self) -> None:
        with self.assertRaisesRegex(KeyError, "available fields: base"):
            _to_float({"base": "88.12"}, "last")
