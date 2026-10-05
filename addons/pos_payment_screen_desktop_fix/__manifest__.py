{
    "name": "POS Payment Screen Desktop Fix",
    "version": "19.0.1.0.0",
    "summary": "Move payment numpad under summary safely",
    "category": "Point of Sale",
    "author": "TelNova",
    "license": "LGPL-3",
    "depends": ["point_of_sale", "pos_restaurant"],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_payment_screen_desktop_fix/static/src/js/payment_screen_desktop_fix.js",
            "pos_payment_screen_desktop_fix/static/src/css/payment_screen_desktop_fix.css"
        ]
    },
    "installable": True,
    "application": False
}
