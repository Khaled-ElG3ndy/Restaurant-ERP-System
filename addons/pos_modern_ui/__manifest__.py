{
    'name': 'POS Modern UI',
    'version': '19.0.1.1.8',
    'summary': 'Modern UI enhancements for Odoo POS',
    'category': 'Point of Sale',
    'author': 'Custom',
    'depends': ['point_of_sale'],
    'assets': {
       'point_of_sale._assets_pos': [
            'pos_modern_ui/static/src/css/pos_modern_ui.css',
            'pos_modern_ui/static/src/css/pos_responsive_guard.css',
            'pos_modern_ui/static/src/css/partner_list.css',
            'pos_modern_ui/static/src/js/pos_modern_ui.js',
            'pos_modern_ui/static/src/js/numpad_toggle.js',
            'pos_modern_ui/static/src/js/partner_list.js',
            'pos_modern_ui/static/src/xml/navbar.xml',
            'pos_modern_ui/static/src/xml/partner_list.xml',
            'pos_modern_ui/static/src/xml/product_price_fix.xml',
            #'pos_modern_ui/static/src/xml/numpad_toggle.xml',
            #'pos_modern_ui/static/src/xml/category_search.xml',
        ],
        'web.assets_backend': [
            'pos_modern_ui/static/src/css/pos_modern_ui.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
