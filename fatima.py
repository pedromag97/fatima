import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
import pandas as pd
import threading
import sys
import logging
import os
from dotenv import load_dotenv

import requests


# ==============================================================================
# 1. Configuração do Ambiente e Chaves API 🔑
# ==============================================================================

load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')

# ==============================================================================
# 2. Parâmetros do Bot
# ==============================================================================

# === CONFIGURAÇÃO: PAR-MOEDA ===
MOEDA = "BTC"
MOEDA_2 = "EUR"
PAR = MOEDA + MOEDA_2

# === GESTÃO DE RISCO: STOP-LOSS E TAKE-PROFIT ===
PERCENTAGEM_STOP_LOSS = 0.02   # 0.2% de perda máxima em relação ao preço de compra
PERCENTAGEM_TAKE_PROFIT = 0.006 # 0.6% de lucro desejado em relação ao preço de compra

# Variáveis globais para rastrear o estado da posição (já existem, mas vamos usá-las)

# === HISTORICO: QUANTIDADE ===
#QUANTIDADE = 0.2 #26.03.2025 - 0.2 BTC = 17500 USD
#QUANTIDADE = 0.16 #26.03.2025 - 0.16 BTC = 13800 USD
#QUANTIDADE = 0.0016 #05.04.2025 - 0.0016 BTC = 133 USD // 122 EUR
QUANTIDADE = 0.0012 #11.06.2025 - 0.0012 BTC = 130 USD // 113 EUR
QTD_INIT_BTC = 0.0001
MIN_RANGE = 0.00005
TIMEFRAME = "5m"

# === PARÂMETRO: EMA ===
MEDIA_RAPIDA = 9
MEDIA_LENTA = 21
# ===========================

# === PARÂMETRO: RSI ===
PERIODO_RSI = 14 # Período comum para o RSI (14 velas)
RSI_SOBRECOMPRA = 70 # Nível de sobrecompra do RSI
RSI_SOBREVENDA = 30  # Nível de sobrevenda do RSI
# ===========================


# ==============================================================================
# 3. Opções de Comportamento e Debug
# ==============================================================================

CONTINUACAO = 1
SIMULACAO = 0
DEBUG_ALL = 0
DEBUG_EMA = 0
DEBUG_SINAIS = 0
DEBUG_RSI = 0 # NOVO: Ativa o debug do RSI

# ==============================================================================
# 4. Variáveis Globais (Estado do Bot)
# ==============================================================================

delta_total = 0
delta_saldo_total = 0
delta_saldo = 0
contador = 0
n_trade = 0
posicao_aberta = False
preco_entrada_global = None
historico_trades = []
preco_stop_loss = None
preco_take_profit = None


# ==============================================================================
# 5. Funções de Logging
# ==============================================================================

# Funcao para configurar ficheiro de LOGs
def setup_logger():
    # Define o diretório para os logs na pasta do utilizador
    #log_directory = os.path.expanduser("~/trading_bot_logs")
    log_filename = os.path.join("trading.txt")

    try:
        # Tenta criar o diretório se ele não existir
        #os.makedirs(log_directory, exist_ok=True)
        #print(f"DEBUG: Diretório de log verificado/criado em: {log_directory}") # Debug temporário

        # Se o ficheiro já existir, remove-o para criar um novo a cada execucao
        if os.path.exists(log_filename):
            os.remove(log_filename)
            print(f"DEBUG: Arquivo de log existente removido: {log_filename}") # Debug temporário

        logging.basicConfig(
            filename=log_filename,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        print(f"INFO: Arquivo de log '{log_filename}' configurado com sucesso.") # Mensagem de sucesso
        # É importante não usar log_event() aqui, pois logging.basicConfig só surte efeito depois
        # e log_event() depende dele.
    except Exception as e:
        # Imprime no console se houver um erro na configuração do logger
        print(f"ERRO CRÍTICO: Falha ao configurar o logger! Erro: {e}")
        sys.exit("Erro fatal na configuração do log. Encerrando.")


# Funcao para fazer LOGs
def log_event(event_type, message):

    log_message = f"{event_type}: {message}"
    logging.info(log_message)
    print(log_message)  # Opcional: tambem imprime no terminal


# ==============================================================================
# 6. Conexão com a Binance
# ==============================================================================
def conexao_binance(client):
    try:
        client = Client(API_KEY, API_SECRET)
        client.timestamp_offset = client.get_server_time()['serverTime'] - int(time.time() * 1100)
        client.get_server_time()  # Usar para calcular diferença e ajustar timestamps
        log_event("INFO", "Conexão com a Binance estabelecida com sucesso.")
    except BinanceAPIException as e:
        log_event("ERRO", f"Falha na conexão com a API da Binance. Status: {e.status_code}, Mensagem: {e.message}, Resposta Bruta: {e.response.text}")
        sys.exit("Erro fatal: Não foi possível conectar à Binance.")
    except Exception as e:
        log_event("ERRO", f"Ocorreu um erro inesperado ao conectar à Binance: {e}")
        sys.exit("Erro fatal: Não foi possível conectar à Binance.")

# ==============================================================================
# 7. Funções de Obtenção e Cálculo de Dados
# ==============================================================================

# Funcao para obter dados da BINANCE/Conta
def obter_dados():
    if DEBUG_ALL: print("7.1- Obter dados")
    try:
        # Aumentar o limite para garantir dados suficientes para o RSI (PERIODO_RSI) e EMAs
        klines = client.get_klines(symbol=PAR, interval=TIMEFRAME, limit=max(50, PERIODO_RSI + MEDIA_LENTA + 5)) # Adiciona uma margem
        df = pd.DataFrame(klines, columns=['time', 'open', 'high', 'low', 'close', 'volume',
                                           'close_time', 'quote_asset_volume', 'number_of_trades',
                                           'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['close'] = df['close'].astype(float)
        return df
    except BinanceAPIException as e:
        log_event("ERRO", f"Falha ao obter klines da Binance. Status: {e.status_code}, Mensagem: {e.message}")
        return pd.DataFrame()
    except Exception as e:
        log_event("ERRO", f"Ocorreu um erro inesperado ao obter dados: {e}")
        return pd.DataFrame()

# Funcao para calcular as medias EMA9 e EMA21 e o RSI
def calcular_medias_e_rsi(df): 
    """
    Calcula as Médias Móveis Exponenciais (EMA) e o RSI no DataFrame.

    Args:
        df (pd.DataFrame): DataFrame com os dados de preço de fechamento.

    Returns:
        pd.DataFrame: DataFrame com as colunas 'EMA9', 'EMA21' e 'RSI' adicionadas.
    """
    
    if DEBUG_ALL: log_event("DEBUG", "7.2- Calcular EMAs e RSI.")
    if df.empty:
        log_event("ALERTA", "DataFrame vazio ao calcular médias e RSI. Pulando o cálculo.")
        return df

    # Calcular EMAs
    df["EMA9"] = df["close"].ewm(span=MEDIA_RAPIDA, adjust=False).mean()
    df["EMA21"] = df["close"].ewm(span=MEDIA_LENTA, adjust=False).mean()

    # ===================== CÁLCULO DO RSI =====================
    # Calcula a diferença de preço entre velas consecutivas
    delta = df['close'].diff()

    # Separa ganhos (ups) e perdas (downs)
    ganhos = delta.where(delta > 0, 0)
    perdas = -delta.where(delta < 0, 0) # Perdas são valores positivos

    # Calcula a média móvel exponencial de ganhos e perdas
    avg_ganhos = ganhos.ewm(span=PERIODO_RSI, adjust=False).mean()
    avg_perdas = perdas.ewm(span=PERIODO_RSI, adjust=False).mean()

    # Calcula o Relative Strength (RS)
    # Evita divisão por zero para perdas nulas
    rs = avg_ganhos / avg_perdas
    rs = rs.fillna(0) # Trata NaN resultantes de divisão por zero

    # Calcula o RSI
    df['RSI'] = 100 - (100 / (1 + rs))
    # ==========================================================

    if DEBUG_EMA:
        log_event("DEBUG_EMA", f"EMA9(Atual) = {df['EMA9'].iloc[-1]:.2f} | EMA21(Atual) = {df['EMA21'].iloc[-1]:.2f} | Diferença = {(df['EMA9'].iloc[-1]-df['EMA21'].iloc[-1]):.2f}")
        log_event("DEBUG_EMA", f"EMA9(Anterior) = {df['EMA9'].iloc[-2]:.2f} | EMA21(Anterior) = {df['EMA21'].iloc[-2]:.2f} | Diferença = {(df['EMA9'].iloc[-2]-df['EMA21'].iloc[-2]):.2f}")
        if len(df) >= 3:
            log_event("DEBUG_EMA", f"EMA9(2x Anterior) = {df['EMA9'].iloc[-3]:.2f} | EMA21(2x Anterior) = {df['EMA21'].iloc[-3]:.2f} | Diferença = {(df['EMA9'].iloc[-3]-df['EMA21'].iloc[-3]):.2f}")

    if DEBUG_RSI:
        if not df['RSI'].empty:
            log_event("DEBUG_RSI", f"RSI(Atual) = {df['RSI'].iloc[-1]:.2f}")
            if len(df) >= 2:
                log_event("DEBUG_RSI", f"RSI(Anterior) = {df['RSI'].iloc[-2]:.2f}")
    return df

# Funcao para verificar sinais atraves das EMAs e RSI
def verificar_sinal(df):
    """
    Verifica os sinais de compra/venda com base no cruzamento das EMAs e nas condições do RSI.

    Args:
        df (pd.DataFrame): DataFrame com as colunas 'EMA9', 'EMA21' e 'RSI'.

    Returns:
        str or None: "COMPRA", "VENDA" ou None se nenhum sinal for detectado.
    """
    if DEBUG_ALL: log_event("DEBUG", "3- Verificar Sinais com EMA e RSI.")
    global posicao_aberta

    # Garante que há dados suficientes para as EMAs e RSI
    if df.empty or len(df) < max(MEDIA_LENTA, PERIODO_RSI) + 1:
        log_event("ALERTA", "Dados insuficientes para verificar sinais (EMA/RSI).")
        return None

    ema9_atual = df["EMA9"].iloc[-1]
    ema21_atual = df["EMA21"].iloc[-1]
    ema9_anterior = df["EMA9"].iloc[-2]
    ema21_anterior = df["EMA21"].iloc[-2]

    rsi_atual = df["RSI"].iloc[-1]
    rsi_anterior = df["RSI"].iloc[-2] # Para verificar a "virada" do RSI

    # === LÓGICA DE COMPRA (EMA + RSI) ===
    # Sinal de Compra: EMA9 cruza acima da EMA21 E RSI está em sobrevenda e começando a subir
    if (ema9_atual > ema21_atual) and \
       (ema9_anterior <= ema21_anterior) and \
       (rsi_atual < RSI_SOBRECOMPRA) and \
       (rsi_atual > rsi_anterior) and \
       (rsi_anterior < RSI_SOBREVENDA + 10): # Adiciona uma margem de movimento do RSI para sair da sobrevenda
        if not posicao_aberta:
            posicao_aberta = True
            log_event("SINAL", f"(1.1) Sinal de COMPRA! EMA cruzou para cima e RSI ({rsi_atual:.2f}) confirmou.")
            return "COMPRA"

    # === LÓGICA DE VENDA (EMA + RSI) ===
    # Sinal de Venda: EMA9 cruza abaixo da EMA21 E RSI está em sobrecompra e começando a cair
    elif (ema9_atual < ema21_atual) and \
         (ema9_anterior >= ema21_anterior) and \
         (rsi_atual > RSI_SOBREVENDA) and \
         (rsi_atual < rsi_anterior) and \
         (rsi_anterior > RSI_SOBRECOMPRA - 10): # Adiciona uma margem de movimento do RSI para sair da sobrecompra
        if posicao_aberta:
            posicao_aberta = False
            log_event("SINAL", f"(2.1) Sinal de VENDA! EMA cruzou para baixo e RSI ({rsi_atual:.2f}) confirmou.")
            return "VENDA"

    # === Lógica de Continuação (opcional, com RSI como filtro extra) ===
    # Se CONTINUACAO estiver habilitado e as EMAs continuam em tendência de alta E RSI não está sobrecomprado
    elif CONTINUACAO and \
         (ema9_atual > ema21_atual) and \
         (ema9_anterior > ema21_anterior) and \
         (rsi_atual < RSI_SOBRECOMPRA): # Não compra se o RSI já estiver muito alto na continuação
        if len(df) >= 3:
            ema9_anterior_2x = df["EMA9"].iloc[-3]
            ema21_anterior_2x = df["EMA21"].iloc[-3]
            if (ema9_anterior_2x > ema21_anterior_2x):
                if not posicao_aberta:
                    posicao_aberta = True
                    log_event("SINAL", f"(1.2) Sinal de COMPRA! Continuação de alta e RSI ({rsi_atual:.2f}) não sobrecomprado.")
                    return "COMPRA"

    # Se CONTINUACAO estiver habilitado e as EMAs continuam em tendência de baixa E RSI não está sobrevendido
    elif CONTINUACAO and \
         (ema9_atual < ema21_atual) and \
         (ema9_anterior < ema21_anterior) and \
         (rsi_atual > RSI_SOBREVENDA): # Não vende se o RSI já estiver muito baixo na continuação
        if posicao_aberta:
            posicao_aberta = False
            log_event("SINAL", f"(2.2) Sinal de VENDA! Continuação de baixa e RSI ({rsi_atual:.2f}) não sobrevendido.")
            return "VENDA"

    return None


# ==============================================================================
# 8. Funções de Execução de Ordens
# ==============================================================================

# Funcao para executar COMPRA/VENDA de ordens
def executar_ordem(tipo, quantidade):
    if DEBUG_ALL: print("4- Executar Ordem")

    if tipo == "BUY":
        try:
            ordem = client.order_market_buy(symbol=PAR, quantity=quantidade)
        except BinanceAPIException as e:
            print("STATUS CODE:", e.status_code)
            print("RESPONSE TEXT:", e.message)
            print("RAW RESPONSE:", e.response.text)
            exit()
    else:
        try:
            ordem = client.order_market_sell(symbol=PAR, quantity=quantidade)
        except BinanceAPIException as e:
            print("STATUS CODE:", e.status_code)
            print("RESPONSE TEXT:", e.message)
            print("RAW RESPONSE:", e.response.text)
            exit()
    return ordem

# ==============================================================================
# 9. Funções de Registo e Saldo
# ==============================================================================

# Funcao para registar TRADE no log
def registar_trade(preco_entrada, preco_saida):
    global delta_total
    global delta_saldo_total
    global n_trade
    global saldo_entrada

    lucro_preco = (preco_saida - preco_entrada) * QUANTIDADE
    n_trade += 1
    
    saldo_1 = float(next((b['free'] for b in client.get_account()['balances'] if b['asset'] == MOEDA), 0))
    saldo_2 = float(next((b['free'] for b in client.get_account()['balances'] if b['asset'] == MOEDA_2), 0))
    delta_saldo = saldo_2-saldo_entrada
    delta_total += lucro_preco
    delta_saldo_total += delta_saldo

    log_event("TRADE", f"--- TRADE #{n_trade} ---")
    log_event("TRADE", f"  Entrada: {preco_entrada:.2f} {MOEDA_2} | Saída: {preco_saida:.2f} {MOEDA_2} | Qtd: {QUANTIDADE} {MOEDA}")
    log_event("TRADE", f"  Lucro (Preço): {lucro_preco:.2f} {MOEDA_2}")
    log_event("TRADE", f"  Saldo Atual: {MOEDA_2}: {saldo_2:.2f} | {MOEDA}: {saldo_1:.5f}")
    log_event("TRADE", f"  Delta (Saldo Real): {delta_saldo:.2f} {MOEDA_2}")
    log_event("TRADE", f"  Total Acumulado (Preço): {delta_total:.2f} {MOEDA_2}")
    log_event("TRADE", f"  Total Acumulado (Saldo Real): {delta_saldo_total:.2f} {MOEDA_2}")
    log_event("TRADE", f"--------------------")

# Funcao para imprimir saldo
def exibir_saldo():
    
    try:    
        info = client.get_account()
    except BinanceAPIException as e:
        log_event("ERRO", f"Falha ao obter informações da conta. Status: {e.status_code}, Mensagem: {e.message}")
        return
    except Exception as e:
        log_event("ERRO", f"Ocorreu um erro inesperado ao exibir saldo: {e}")
        return
    
    for asset in info['balances']:
        saldo = float(asset['free'])
        if contador == 0:
            if saldo > 0:
                log_event("SALDO", f"🔹 {asset['asset']}: {saldo:.7f} disponivel")
            #if asset['asset'] == MOEDA:
            #    if saldo < (QTD_INIT_BTC-MIN_RANGE):
            #        print(f"SALDO INICIAL: 1 - {saldo}")
            #        #executar_ordem("BUY", round(float(QTD_INIT_BTC)-saldo, 5))
            #    elif saldo > (QTD_INIT_BTC+MIN_RANGE):
            #        print(f"SALDO INICIAL: 2 - {saldo}")
            #       #executar_ordem("SELL", round(saldo-float(QTD_INIT_BTC), 5))

        else:
            if asset['asset'] == MOEDA or asset['asset'] == MOEDA_2:
                log_event("SALDO", f"🔹 {asset['asset']}: {saldo:.7f} disponivel")


####### LOOP PRINCIPAL #######

# ==============================================================================
# 10. Loop Principal do Bot
# ==============================================================================

#if __name__ == "__main__":


setup_logger()
    
log_event("INFO", "O bot de trading foi iniciado.")
log_event("INFO", f"Par de Trading: {PAR}, Quantidade por Trade: {QUANTIDADE} {MOEDA}, Timeframe: {TIMEFRAME}")
log_event("INFO", f"Estratégia: EMA Rápida ({MEDIA_RAPIDA}), EMA Lenta ({MEDIA_LENTA}), RSI Período ({PERIODO_RSI})")
log_event("INFO", f"RSI Níveis: Sobrecompra {RSI_SOBRECOMPRA}, Sobrevenda {RSI_SOBREVENDA}")
#log_event("INFO", f"Stop Loss Configurado: {STOP_LOSS} {MOEDA_2}")

client = Client(API_KEY, API_SECRET)
conexao_binance(client)

preco_stop_loss = 0.0
preco_take_profit = 0.0

while True:
    #exibir_saldo_paper_trading()
    exibir_saldo()
    try:
        df = obter_dados()
            
        if df.empty:
            log_event("ALERTA", "Não foi possível obter dados de mercado. Tentando novamente na próxima iteração.")
            time.sleep(5)
            continue

        contador += 1
        preco_atual = float(client.get_symbol_ticker(symbol=PAR)['price'])
        log_event("INFO", f" *** Iteracao = {contador} || VALOR BTC = {preco_atual:.2f} EUR ***")


        # Verifica se já existe uma posição aberta - STOP LOSS e TAKE PROFIT
        if posicao_aberta and preco_entrada_global is not None:
            if preco_atual <= preco_stop_loss:
                log_event("STOP_LOSS", f"🔴 STOP-LOSS ativado! Preco atual ({preco_atual:.2f}) atingiu ou ultrapassou SL ({preco_stop_loss:.2f}).")
                # Lógica para vender tudo
                qtd_moeda_disponivel = float(next((b['free'] for b in client.get_account()['balances'] if b['asset'] == MOEDA), 0))
                quantidade_a_vender = min(QUANTIDADE, qtd_moeda_disponivel)

                # Verifica a quantidade mínima para o par antes de tentar vender
                # Adaptação para pegar a quantidade mínima do filtro 'LOT_SIZE'
                symbol_info = client.get_symbol_info(PAR)
                min_qty_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                min_qty = float(min_qty_filter['minQty']) if min_qty_filter else 0.0
                if quantidade_a_vender >= min_qty:
                    ordem_venda = executar_ordem("SELL", qtd_moeda_disponivel)
                    if ordem_venda:
                        registar_trade(preco_entrada_global, preco_atual) # Registar a venda de SL
                        log_event("VENDA", f"VENDA por STOP-LOSS: => PRECO DE VENDA = {preco_atual:.2f} {MOEDA_2} || Quantidade = {qtd_moeda_disponivel} {MOEDA} || Valor vendido = {(qtd_moeda_disponivel*preco_atual):.2f} {MOEDA_2}")
                        posicao_aberta = False
                        preco_entrada_global = None
                        preco_stop_loss = None
                        preco_take_profit = None
                    else:
                        log_event("ERRO", "Ordem de venda STOP-LOSS falhou.")
                else:
                    log_event("ALERTA", f"Não há {MOEDA} suficiente para vender via STOP-LOSS. Qtd disponível: {qtd_moeda_disponivel}")
                    posicao_aberta = False # Se não tem para vender, assume que a posição não está mais aberta
                    preco_entrada_global = None
                    preco_stop_loss = None
                    preco_take_profit = None

            elif preco_atual >= preco_take_profit:
                log_event("TAKE_PROFIT", f"🟢 TAKE-PROFIT ativado! Preco atual ({preco_atual:.2f}) atingiu ou ultrapassou TP ({preco_take_profit:.2f}).")
                # Lógica para vender tudo
                qtd_moeda_disponivel = float(next((b['free'] for b in client.get_account()['balances'] if b['asset'] == MOEDA), 0))
                quantidade_a_vender = min(QUANTIDADE, qtd_moeda_disponivel)

                # Verifica a quantidade mínima para o par antes de tentar vender
                # Adaptação para pegar a quantidade mínima do filtro 'LOT_SIZE'
                symbol_info = client.get_symbol_info(PAR)
                min_qty_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                min_qty = float(min_qty_filter['minQty']) if min_qty_filter else 0.0
                if quantidade_a_vender >= min_qty:
                    ordem_venda = executar_ordem("SELL", qtd_moeda_disponivel)
                    if ordem_venda:
                        registar_trade(preco_entrada_global, preco_atual) # Registar a venda de TP
                        log_event("VENDA", f"VENDA por TAKE-PROFIT: => PRECO DE VENDA = {preco_atual:.2f} {MOEDA_2} || Quantidade = {qtd_moeda_disponivel} {MOEDA} || Valor vendido = {(qtd_moeda_disponivel*preco_atual):.2f} {MOEDA_2}")
                        posicao_aberta = False
                        preco_entrada_global = None
                        preco_stop_loss = None
                        preco_take_profit = None
                    else:
                        log_event("ERRO", "Ordem de venda TAKE-PROFIT falhou.")
                else:
                    log_event("ALERTA", f"Não há {MOEDA} suficiente para vender via TAKE-PROFIT. Qtd disponível: {qtd_moeda_disponivel}")
                    posicao_aberta = False # Se não tem para vender, assume que a posição não está mais aberta
                    preco_entrada_global = None
                    preco_stop_loss = None
                    preco_take_profit = None
            

        df = calcular_medias_e_rsi(df)

        sinal = verificar_sinal(df)
        
        if sinal == "COMPRA":
            log_event("COMPRA", "📈 Sinal de COMPRA! Executando ordem...")
            preco_entrada_global = float(client.get_symbol_ticker(symbol=PAR)['price'])
            saldo_entrada = float(next((b['free'] for b in client.get_account()['balances'] if b['asset'] == MOEDA_2), 0))

            ordem_compra = executar_ordem("BUY", QUANTIDADE)
            if ordem_compra:
                    preco_stop_loss = preco_entrada_global * (1 - PERCENTAGEM_STOP_LOSS)
                    preco_take_profit = preco_entrada_global * (1 + PERCENTAGEM_TAKE_PROFIT)

                    log_event("INFO", f"Configurado STOP-LOSS em {preco_stop_loss:.2f} {MOEDA_2} ({-PERCENTAGEM_STOP_LOSS*100:.2f}%)")
                    log_event("INFO", f"Configurado TAKE-PROFIT em {preco_take_profit:.2f} {MOEDA_2} ({PERCENTAGEM_TAKE_PROFIT*100:.2f}%)")

                    log_event("COMPRA", f"=> PRECO DE COMPRA = {preco_entrada_global:.2f} {MOEDA_2} || Quantidade = {QUANTIDADE} {MOEDA} || Valor gasto = {(QUANTIDADE*preco_entrada_global):.2f} {MOEDA_2}")
            else:
                log_event("ERRO", "Ordem de compra falhou. Mantendo a posição 'fechada' ou tratando o erro.")
                posicao_aberta = False
        
        elif sinal == "VENDA": #and preco_entrada_global is not None:
            log_event("VENDA", "📉 Sinal de VENDA! Executando ordem...")
            
            preco_venda = preco_atual

            qtd_moeda_disponivel = float(next((b['free'] for b in client.get_account()['balances'] if b['asset'] == MOEDA), 0))
            quantidade_a_vender = min(QUANTIDADE, qtd_moeda_disponivel)

            # Verifica a quantidade mínima para o par antes de tentar vender
            # Adaptação para pegar a quantidade mínima do filtro 'LOT_SIZE'
            symbol_info = client.get_symbol_info(PAR)
            min_qty_filter = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
            min_qty = float(min_qty_filter['minQty']) if min_qty_filter else 0.0

            if quantidade_a_vender >= min_qty:
                ordem_venda = executar_ordem("SELL", quantidade_a_vender)
                if ordem_venda:
                    registar_trade(preco_entrada_global, preco_venda)
                    log_event("VENDA", f"=> PRECO DE VENDA = {preco_venda:.2f} {MOEDA_2} || Quantidade = {quantidade_a_vender} {MOEDA} || Valor vendido = {(quantidade_a_vender*preco_venda):.2f} {MOEDA_2}")
                    preco_entrada_global = None
                else:
                    log_event("ERRO", "Ordem de venda falhou. Mantendo a posição 'aberta' ou tratando o erro.")
                    posicao_aberta = True
            else:
                log_event("ALERTA", f"Quantidade de {MOEDA} ({qtd_moeda_disponivel:.5f}) insuficiente para venda. Mínimo para {PAR}: {min_qty}")
                posicao_aberta = False
            
            preco_entrada_global = None


        # STOP LOSS
        
        time.sleep(5)
    
    except KeyboardInterrupt:
        log_event("INFO", "Bot interrompido manualmente (Ctrl+C).")
        break
    except BinanceAPIException as e:
        log_event("ERRO_GERAL", f"Erro da API da Binance no loop principal. Status: {e.status_code}, Mensagem: {e.message}")
        time.sleep(10)
    except Exception as e:
        log_event("ERRO_GERAL", f"Ocorreu um erro inesperado no loop principal: {e}")
        time.sleep(10)