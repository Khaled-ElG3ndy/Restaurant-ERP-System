{
    "name": "Hosny Purchase Agreement Name",
    "version": "19.0.1.4.6",
    "category": "Purchases",
    "summary": "Use the user agreement name instead of the generated purchase agreement reference",
    "depends": ["purchase_requisition", "purchase_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/purchase_requisition_views.xml",
        "views/purchase_price_history_wizard_views.xml",
        "views/purchase_order_views.xml",
        "views/stock_warehouse_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_purchase_requisition_name/static/src/views/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
    "license": "LGPL-3",
    "installable": True,
}
