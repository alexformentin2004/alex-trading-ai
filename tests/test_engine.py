import unittest
from engine import backtest, demo_prices


class EngineTests(unittest.TestCase):
    def test_reproducible(self):
        self.assertEqual(demo_prices(), demo_prices())

    def test_no_trade_on_flat_prices(self):
        result = backtest([100.0]*100)
        self.assertAlmostEqual(result['ending_equity'], 50.0)

    def test_no_future_data_leak(self):
        prices = demo_prices(150)
        first = backtest(prices[:100])
        changed_future = prices[:100]+[100000.0]*50
        other = backtest(changed_future[:100])
        self.assertEqual(first, other)

    def test_invalid_parameters(self):
        with self.assertRaises(ValueError):
            backtest([100.]*100, fast=50, slow=20)


if __name__ == '__main__':
    unittest.main()
