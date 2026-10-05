{
    "name": "Hosny Stock Report Quantity Sync",
    "version": "19.0.1.0.10",
    "summary": "Keep stock report quantities and unit costs aligned with warehouse stock",
    "category": "Inventory/Inventory",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["web", "stock", "stock_account"],
    "data": [
        "views/product_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_stock_report_quant_sync/static/src/js/stock_search_panel.js",
            "hosny_stock_report_quant_sync/static/src/xml/stock_search_panel.xml",
            "hosny_stock_report_quant_sync/static/src/css/stock_search_panel.css",
        ],
    },
    "installable": True,
    "application": False,
}
