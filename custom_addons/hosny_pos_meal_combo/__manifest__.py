{
    "name": "Hosny POS Meal Combo",
    "version": "19.0.1.1.16",
    "author": "Hosny",
    "category": "Point of Sale",
    "summary": "Restaurant meal bundles with parent revenue and component stock deduction",
    "depends": [
        "point_of_sale",
        "pos_restaurant",
        "stock_account",
        "mrp_account",
        "account",
        "product",
        "pos_auto_mrp",
        "hosny_pos_controls",
        "hosny_pos_receipt",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/product_meal_component_views.xml",
        "views/pos_order_views.xml",
        "views/pos_additional_cost_breakdown_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_pos_meal_combo/static/src/js/additional_cost_field.js",
            "hosny_pos_meal_combo/static/src/xml/additional_cost_field.xml",
            "hosny_pos_meal_combo/static/src/scss/pos_order_cost_breakdown.scss",
        ],
        "point_of_sale._assets_pos": [
            "hosny_pos_meal_combo/static/src/js/meal_combo.js",
            "hosny_pos_meal_combo/static/src/scss/meal_combo.scss",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
