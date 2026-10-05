{
    "name": "Hosny POS Send Order",
    "version": "19.0.2.1.0",
    "category": "Point of Sale",
    "summary": "Persistent restaurant send order workflow with sent timers",
    "depends": ["point_of_sale", "pos_restaurant", "pos_entry_selector"],
    "data": [
        "views/pos_order_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "hosny_pos_send_order/static/src/app/store/order_send_state.js",
            "hosny_pos_send_order/static/src/app/floor_screen/table_timer.js",
            ("after", "pos_entry_selector/static/src/xml/floor_table_ui.xml", "hosny_pos_send_order/static/src/xml/order_send_templates.xml"),
            ("after", "pos_entry_selector/static/src/css/floor_table_ui.css", "hosny_pos_send_order/static/src/scss/order_send.scss"),
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
