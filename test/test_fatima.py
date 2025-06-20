import unittest
import pandas as pd
from importlib import reload

import fatima

class TestTradingSignals(unittest.TestCase):
    def setUp(self):
        # Reload module to reset globals between tests
        reload(fatima)
        fatima.posicao_aberta = False

    def test_compra_signal(self):
        df = pd.DataFrame({
            'EMA9': [10]*21 + [12],
            'EMA21': [11]*21 + [10],
            'RSI': [25]*21 + [35],
        })
        sinal = fatima.verificar_sinal(df)
        self.assertEqual(sinal, "COMPRA")

    def test_venda_signal(self):
        fatima.posicao_aberta = True
        df = pd.DataFrame({
            'EMA9': [12]*21 + [10],
            'EMA21': [10]*21 + [11],
            'RSI': [75]*21 + [65],
        })
        sinal = fatima.verificar_sinal(df)
        self.assertEqual(sinal, "VENDA")

if __name__ == '__main__':
    unittest.main()
