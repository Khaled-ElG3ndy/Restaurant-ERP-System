{
    "name": "POS Multi Payment Reconciliation",
    "version": "19.0.1.4.0",
    "summary": "Multi-payment method cash in/out reconciliation for POS sessions",
    "category": "Point of Sale",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "account",
        "point_of_sale",
    ],
    "data": [
        "views/account_move_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_multi_payment_reconciliation/static/src/app/navbar/multi_cash_move_popup/multi_cash_move_receipt.js",
            "pos_multi_payment_reconciliation/static/src/app/navbar/multi_cash_move_popup/multi_cash_move_popup.js",
            "pos_multi_payment_reconciliation/static/src/overrides/navbar.js",
            "pos_multi_payment_reconciliation/static/src/app/navbar/multi_cash_move_popup/multi_cash_move_receipt.xml",
            "pos_multi_payment_reconciliation/static/src/app/navbar/multi_cash_move_popup/multi_cash_move_popup.xml",
            "pos_multi_payment_reconciliation/static/src/scss/multi_cash_move_popup.scss",
        ],
    },
    "installable": True,
    "application": False,
}
