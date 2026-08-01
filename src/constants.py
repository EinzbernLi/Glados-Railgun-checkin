DEFAULT_DOMAINS = ("glados.cloud", "railgun.info")
EXCHANGE_PLANS = {
    "plan100": (100, 10),
    "plan200": (200, 30),
    "plan500": (500, 100),
}
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
PUSHDEER_URL = "https://api2.pushdeer.com/message/push"
PUSHPLUS_URL = "https://www.pushplus.plus/send"
TELEGRAM_URL_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
