{
    "name": "Hosny Tax and Zakat Dashboard",
    "summary": "Live tax and explicitly configured Zakat movements from original journal items",
    "version": "19.0.1.0.5",
    "category": "Accounting/Accounting",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": [
        "account",
        "l10n_sa",
        "point_of_sale",
    ],
    "data": [
        "views/account_move_line_views.xml",
        "views/account_journal_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_tax_zakat_dashboard/static/src/scss/account_dashboard_amounts.scss",
        ],
    },
    "installable": True,
    "application": False,
}
