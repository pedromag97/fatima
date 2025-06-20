class Client:
    def __init__(self, *args, **kwargs):
        pass
    def get_server_time(self):
        return {'serverTime': 0}
    def get_symbol_ticker(self, symbol):
        return {'price': 0}
    def get_symbol_info(self, symbol):
        return {'filters':[{'filterType':'LOT_SIZE','minQty':'0.0001'}]}
    def get_account(self):
        return {'balances': []}
    def order_market_buy(self, symbol, quantity):
        return {'symbol': symbol, 'executedQty': quantity}
    def order_market_sell(self, symbol, quantity):
        return {'symbol': symbol, 'executedQty': quantity}
 