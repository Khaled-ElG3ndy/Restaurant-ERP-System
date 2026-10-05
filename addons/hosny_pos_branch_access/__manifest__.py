{
    "name": "Hosny POS Branch Access",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "summary": "Limit a point of sale user to the branches they actually work in",
    "description": """
Branch access for point of sale users
=====================================

A point of sale user normally sees every point of sale in the company, with all
of its sessions, orders and payments. This module adds an *Allowed Points of
Sale* list on the user: leave it empty and nothing changes, fill it in and the
user can only reach those points of sale and the records that belong to them.
""",
    "depends": [
        "point_of_sale",
        "pos_restaurant",
        "pos_sale",
        "contacts",
        "hr",
        "mail",
        "calendar",
        "spreadsheet_dashboard",
    ],
    "data": [
        "security/pos_branch_rules.xml",
        "security/cashier_menus.xml",
        "views/res_users_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_pos_branch_access/static/src/js/branch_cashier_ui.js",
            "hosny_pos_branch_access/static/src/scss/branch_cashier_ui.scss",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
