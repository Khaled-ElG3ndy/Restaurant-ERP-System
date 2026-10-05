# -*- coding: utf-8 -*-
{
    "name": "Hosny POS Table Merge",
    "version": "19.0.3.0.0",
    "category": "Point of Sale",
    "summary": "Modern restaurant table merge flow for Odoo POS",
    "depends": ["point_of_sale", "pos_restaurant", "hosny_pos_controls"],
    "assets": {
        "point_of_sale._assets_pos": [
            "hosny_pos_table_merge/static/src/js/merge_handler.js",
            "hosny_pos_table_merge/static/src/js/merge_popup.js",
            "hosny_pos_table_merge/static/src/js/pos_table_merge.js",
            "hosny_pos_table_merge/static/src/xml/merge_popup.xml",
            "hosny_pos_table_merge/static/src/scss/merge_popup.scss",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
