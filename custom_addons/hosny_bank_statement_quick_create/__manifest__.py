{
    "name": "Hosny Bank Statement Quick Create",
    "summary": "Create bank and cash transactions directly from the accounting dashboard",
    "version": "19.0.2.1.0",
    "category": "Accounting/Accounting",
    "author": "Custom",
    "license": "LGPL-3",
    "depends": ["account", "hosny_account_analytic_header"],
    "data": [
        "views/account_bank_statement_line_views.xml",
        "views/account_bank_statement_views.xml",
        "views/account_journal_dashboard_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_bank_statement_quick_create/static/src/js/bank_statement_workspace.js",
            "hosny_bank_statement_quick_create/static/src/xml/bank_statement_workspace.xml",
            "hosny_bank_statement_quick_create/static/src/scss/bank_statement_workspace.scss",
        ],
    },
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
