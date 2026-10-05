{
    'name': 'Hosny POS Theme',
    'version': '19.0.1.0.1',
    'category': 'Point of Sale',
    'summary': 'Toast-like modern POS UI — Arabic first, Hosny brand colors',
    'depends': ['point_of_sale', 'pos_restaurant'],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_entry_selector/static/src/css/entry_selector.css',
            'pos_entry_selector/static/src/css/floor_table_ui.css',
            'pos_entry_selector/static/src/css/payment_screen_layout.css',
            'hosny_pos_theme/static/src/xml/product_configurator_popup_override.xml',
            'hosny_pos_theme/static/src/css/theme.css',
            'hosny_pos_theme/static/src/css/product_configurator_layout.css',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
