{
    "name": "Hosny POS Order Filters",
    "version": "19.0.1.0.0",
    "author": "Hosny",
    "category": "Point of Sale",
    "summary": "Filters on the POS orders screen (date, shift, payment method, type, user) and the payment method on every order",
    "depends": [
        "point_of_sale",
        "pos_restaurant",
        "hosny_pos_printer_matrix",
        "hosny_pos_receipt",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "hosny_pos_order_filters/static/src/js/order_filters.js",
            "hosny_pos_order_filters/static/src/xml/order_filters.xml",
            "hosny_pos_order_filters/static/src/css/order_filters.css",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
