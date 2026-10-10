{
    "name": "Hosny POS Shift Close",
    "version": "19.0.1.1.0",
    "author": "Hosny",
    "category": "Point of Sale",
    "summary": "Every shift starts from zero: counted cash is handed to the branch safe at close; "
               "أجل count, discount coupons, discounts and hospitality on the closing screen; shift reports",
    "depends": [
        "point_of_sale",
        "pos_restaurant",
        "pos_loyalty",
        "hosny_pos_controls",
        "hosny_pos_skin",
        "pos_multi_payment_reconciliation",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/pos_config_views.xml",
        "views/pos_session_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "hosny_pos_shift_close/static/src/js/shift_close.js",
            "hosny_pos_shift_close/static/src/xml/shift_close.xml",
            "hosny_pos_shift_close/static/src/css/shift_close.css",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
