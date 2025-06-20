import pandas as pd
import argparse

EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


def load_data(file_path: str) -> pd.DataFrame:
    """Load CSV data for backtesting."""
    df = pd.read_csv(file_path)
    if 'close' not in df.columns:
        raise ValueError("O ficheiro deve conter a coluna 'close'.")
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate EMA and RSI indicators."""
    df = df.copy()
    df['EMA_FAST'] = df['close'].ewm(span=EMA_FAST, adjust=False).mean()
    df['EMA_SLOW'] = df['close'].ewm(span=EMA_SLOW, adjust=False).mean()

    delta = df['close'].diff()
    gains = delta.where(delta > 0, 0)
    losses = -delta.where(delta < 0, 0)
    avg_gains = gains.ewm(span=RSI_PERIOD, adjust=False).mean()
    avg_losses = losses.ewm(span=RSI_PERIOD, adjust=False).mean()
    rs = avg_gains / avg_losses
    df['RSI'] = 100 - (100 / (1 + rs))
    return df


def sinal_ema(df: pd.DataFrame, i: int) -> str | None:
    if i == 0:
        return None
    if df['EMA_FAST'].iloc[i] > df['EMA_SLOW'].iloc[i] and df['EMA_FAST'].iloc[i-1] <= df['EMA_SLOW'].iloc[i-1]:
        return 'COMPRA'
    if df['EMA_FAST'].iloc[i] < df['EMA_SLOW'].iloc[i] and df['EMA_FAST'].iloc[i-1] >= df['EMA_SLOW'].iloc[i-1]:
        return 'VENDA'
    return None


def sinal_rsi(df: pd.DataFrame, i: int) -> str | None:
    if i == 0:
        return None
    rsi_atual = df['RSI'].iloc[i]
    rsi_anterior = df['RSI'].iloc[i-1]
    if rsi_anterior < RSI_OVERSOLD and rsi_atual > rsi_anterior:
        return 'COMPRA'
    if rsi_anterior > RSI_OVERBOUGHT and rsi_atual < rsi_anterior:
        return 'VENDA'
    return None


def backtest(df: pd.DataFrame, analysis: str = 'both') -> list:
    """Return list of operations with (index, type, price)."""
    operations = []
    for i in range(len(df)):
        signal = None
        if analysis in ('ema', 'both'):
            signal = sinal_ema(df, i)
        if signal is None and analysis in ('rsi', 'both'):
            signal = sinal_rsi(df, i)
        if signal:
            operations.append((i, signal, df['close'].iloc[i]))
    return operations


def main() -> None:
    parser = argparse.ArgumentParser(description='Backtest simples com EMA e RSI')
    parser.add_argument('ficheiro', help='Ficheiro CSV com dados (deve ter coluna close)')
    parser.add_argument('--analise', choices=['ema', 'rsi', 'both'], default='both', help='Tipo de análise')
    args = parser.parse_args()

    df = load_data(args.ficheiro)
    df = add_indicators(df)
    ops = backtest(df, args.analise)

    for idx, typ, price in ops:
        print(f"{idx}: {typ} @ {price}")


if __name__ == '__main__':
    main()