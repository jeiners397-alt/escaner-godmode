import os
import time
import threading
import requests
import numpy as np
import pandas as pd
from flask import Flask

# Servidor Flask para mantener activo el Web Service gratuito de Render
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Escáner GodMode activo 24/7 en Render"

# ==========================================
# CONFIGURACIÓN DE TELEGRAM Y BINANCE
# ==========================================
TELEGRAM_BOT_TOKEN = "8597480784:AAHXTurxutKMXTRMaQYpsPQaZERc0-ZDHGI"
TELEGRAM_CHAT_ID = "8542123837"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "ZECUSDT", "XRPUSDT", "BTWUSDT", 
    "SUIUSDT", "LINKUSDT", "BNBUSDT", "DOGEUSDT", "PUMPUSDT", "AVAXUSDT", 
    "NEARUSDT", "RLCUSDT", "MINAUSDT", "PROMUSDT", "ONGUSDT", "LYNUSDT", 
    "BRUSDT", "USUSDT", "ORCAUSDT", "HYPEUSDT"
]

TIMEFRAME = "15m"
MIN_WIN_PROB = 10.0  # <--- Mantenlo en 10.0 para hacer la prueba de fuego de inmediato. Una vez que te lleguen alertas a Telegram, edítalo y ponlo en 75.0

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error al enviar mensaje a Telegram: {e}")

def fetch_klines(symbol, interval="15m", limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_vol', 'trades', 'tb_base_vol', 'tb_quote_vol', 'ignore'
        ])
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception as e:
        print(f"Error al obtener datos de {symbol}: {e}")
        return None

def calculate_crsi(close_prices):
    rsi3 = pd.Series(close_prices).diff()
    up = rsi3.clip(lower=0)
    down = -1 * rsi3.clip(upper=0)
    ma_up = up.rolling(3).mean()
    ma_down = down.rolling(3).mean()
    rsi_val = 100 - (100 / (1 + (ma_up / (ma_down + 1e-9))))
    return rsi_val.iloc[-1]

def analyze_symbol(symbol):
    df = fetch_klines(symbol, interval=TIMEFRAME, limit=60)
    if df is None or len(df) < 50:
        return

    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values

    curr_close = close[-1]
    curr_high = high[-1]
    curr_low = low[-1]

    # Z-Score de Volumen
    vol_mean = np.mean(volume[-20:])
    vol_std = np.std(volume[-20:])
    vol_zscore = (volume[-1] - vol_mean) / vol_std if vol_std > 0 else 0
    has_vol_spike = vol_zscore > 1.2

    # CVD Sintético
    rng = curr_high - curr_low
    delta_frac = ((curr_close - curr_low) - (curr_high - curr_close)) / rng if rng > 0 else 0
    vol_delta = volume[-1] * delta_frac
    has_cvd_bull = vol_delta > 0 and has_vol_spike
    has_cvd_bear = vol_delta < 0 and has_vol_spike

    atr = np.mean(df['high'].values[-14:] - df['low'].values[-14:])
    ema20 = pd.Series(close).ewm(span=20).mean().iloc[-1]
    crsi_val = calculate_crsi(close)

    fvg_bull = (low[-1] > high[-3]) and has_vol_spike
    fvg_bear = (high[-1] < low[-3]) and has_vol_spike

    score_long = 0.0
    score_short = 0.0

    if fvg_bull or curr_close > ema20:
        score_long += 3.0
    if fvg_bear or curr_close < ema20:
        score_short += 3.0

    if has_cvd_bull:
        score_long += 2.5
    if has_cvd_bear:
        score_short += 2.5

    if curr_close > ema20:
        score_long += 2.5
    else:
        score_short += 2.5

    if crsi_val < 35:
        score_long += 2.0
    elif crsi_val > 65:
        score_short += 2.0

    score_long += 2.0
    score_short += 2.0

    prob_long = min(max((score_long / 12.0) * 100.0, 5.0), 98.0)
    prob_short = min(max((score_short / 12.0) * 100.0, 5.0), 98.0)

    if prob_long >= MIN_WIN_PROB or prob_short >= MIN_WIN_PROB:
        action = "LONG 🚀" if prob_long > prob_short else "SHORT 🔻"
        win_prob = max(prob_long, prob_short)
        
        sl = curr_close - (atr * 1.5) if action == "LONG 🚀" else curr_close + (atr * 1.5)
        risk_dist = abs(curr_close - sl)
        tp2 = curr_close + (risk_dist * 2.0) if action == "LONG 🚀" else curr_close - (risk_dist * 2.0)

        msg = (
            f"🚀 *¡ALERTA GODMODE FAST ENGINE!*\n"
            f"───────────────────────\n"
            f"📊 *Par:* {symbol}.P\n"
            f"📈 *Acción:* {action}\n"
            f"🔥 *Win Prob:* {win_prob:.1f}%\n"
            f"🔹 *Entrada:* {curr_close:.5f}\n"
            f"🛑 *Stop Loss:* {sl:.5f}\n"
            f"🎯 *Take Profit (TP2):* {tp2:.5f}\n"
            f"───────────────────────\n"
            f"⚡ _Ejecutar en Binance Futures_"
        )
        print(f"[ALERTA DETECTADA] {symbol}: {action} ({win_prob:.1f}%)")
        send_telegram_alert(msg)

def run_scanner():
    print("🤖 Escáner GodMode Activo. Rastreando Binance Futures...")
    while True:
        for symbol in SYMBOLS:
            analyze_symbol(symbol)
            time.sleep(0.2)
        print("✅ Ciclo de escaneo completado. Reevaluando en 15 minutos...")
        time.sleep(900)

# Inicia el escáner de Binance en segundo plano
threading.Thread(target=run_scanner, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
