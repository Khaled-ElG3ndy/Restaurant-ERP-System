{
    "name": "POS MRP Smart Filter",
    "version": "19.0.1.0.0",
    "summary": "Hide POS products that cannot be sold or manufactured from available stock",
    "category": "Point of Sale",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "mrp",
        "stock",
    ],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_mrp_smart_filter/static/src/js/pos_product_filter.js",
        ],
    },
    "installable": True,
    "application": False,
}
