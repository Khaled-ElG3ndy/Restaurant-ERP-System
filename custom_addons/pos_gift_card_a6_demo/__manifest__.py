# -*- coding: utf-8 -*-
{
    'name': 'POS Gift Card A6 Demo Design',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Experimental A6 Arabic discount coupon print layout',
    'description': """
Experimental A6 Discount Coupon Design
======================================
Adds a separate A6 landscape QWeb/PDF report for reviewing a new Arabic
discount coupon design without replacing the production gift card report.
    """,
    'depends': ['pos_gift_card_custom_design'],
    'data': [
        'reports/gift_card_a6_demo_report.xml',
        'views/loyalty_card_a6_demo_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}

