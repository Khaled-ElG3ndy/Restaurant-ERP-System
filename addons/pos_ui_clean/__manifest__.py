{
    'name': 'POS UI Clean',
    'version': '1.0',
    'summary': 'Hide unwanted POS buttons',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_loyalty', 'pos_modern_ui'],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_ui_clean/static/src/xml/hide_buttons.xml',
            'pos_ui_clean/static/src/app/control_buttons/new_invoice_button.xml',
            'pos_ui_clean/static/src/js/service_worker_guard.js',
            'pos_ui_clean/static/src/app/control_buttons/new_invoice_button.js',
            'pos_ui_clean/static/src/js/navbar_button.js',
            'pos_ui_clean/static/src/css/hide.css',
            'pos_ui_clean/static/src/css/payment_buttons_horizontal.css',
            'pos_modern_ui/static/src/css/pos_responsive_guard.css',
        ],
    },
    'installable': True,
    'application': False,
}
