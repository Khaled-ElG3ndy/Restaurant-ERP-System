{
    "name": "Hosny Payroll Rule Ordering",
    "version": "19.0.1.0.2",
    "category": "Human Resources/Payroll",
    "summary": "Move salary rules up or down from the payroll structure",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": [
        "bi_hr_payroll",
    ],
    "data": [
        "views/hr_payroll_structure_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_payroll_rule_order/static/src/scss/payroll_rule_order.scss",
        ],
    },
    "installable": True,
    "application": False,
}
