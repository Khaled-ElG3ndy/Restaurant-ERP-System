{
    "name": "Hosny Account Analytic Header",
    "version": "19.0.1.0.1",
    "category": "Accounting",
    "summary": "Move analytic account selection from journal lines to the invoice/journal header",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": ["account", "analytic", "point_of_sale"],
    "data": [
        "views/account_move_views.xml",
        "views/pos_config_views.xml",
    ],
    "installable": True,
    "application": False,
}
