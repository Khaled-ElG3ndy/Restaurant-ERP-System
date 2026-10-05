def format_currency_after_amount(env, value, currency=None, decimals=None, symbol=None):
    value = value or 0.0
    currency = currency or env.company.currency_id
    if currency and currency.is_zero(value):
        value = 0.0
    precision = decimals if decimals is not None else (currency.decimal_places if currency else 2)
    currency_symbol = symbol if symbol is not None else ((currency.symbol or currency.name) if currency else "")
    amount = "{:,.{prec}f}".format(abs(value), prec=precision)
    if value < 0:
        amount = "-%s" % amount
    return "%s %s" % (amount, currency_symbol) if currency_symbol else amount
