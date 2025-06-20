class BinanceAPIException(Exception):
    def __init__(self, status_code=0, message='', response=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.response = response or type('Response', (), {'text': ''})()