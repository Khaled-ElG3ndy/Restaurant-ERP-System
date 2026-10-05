{
    "name": "Hosny Payroll RTL Forms",
    "version": "19.0.1.0.2",
    "category": "Human Resources/Payroll",
    "summary": "Natural right-to-left layout for payroll configuration forms",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": [
        "bi_hr_payroll",
    ],
    "data": [
        "views/payroll_rtl_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_payroll_rtl/static/src/scss/payroll_rtl.scss",
        ],
    },
    "installable": True,
    "application": False,
}
