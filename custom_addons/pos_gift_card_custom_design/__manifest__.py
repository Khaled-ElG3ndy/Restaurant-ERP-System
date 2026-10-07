# -*- coding: utf-8 -*-
{
    'name': 'POS Gift Card Custom Arabic Design',
    'version': '1.1',
    'category': 'Point of Sale',
    'summary': 'Premium Arabic gift card print layout for POS',
    'description': """
Premium Arabic Gift Card Design
===============================
Redesigns gift card print to premium RTL Arabic layout.
    """,
    'depends': ['point_of_sale', 'pos_loyalty', 'sale_loyalty', 'loyalty'],
    'data': [
        'reports/gift_card_report.xml',
        'data/mail_template.xml',
        'views/loyalty_card_views.xml',
        'data/discount_coupon_labels.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
