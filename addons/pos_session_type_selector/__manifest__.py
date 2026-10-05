# -*- coding: utf-8 -*-
{
    'name': 'POS Session Type Selector (Arabic)',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'Popup modal to select order type (سفري / محلي) when opening POS',
    'description': """
        Intercepts the POS startup and shows a professional Arabic modal overlay
        before the user reaches any screen.

        - سفري (Takeout)  → navigates to ProductScreen
        - محلي (Dine-in)  → navigates to FloorScreen (falls back to ProductScreen
                              if no floors are configured)

        Features
        --------
        * Pure OWL reactive approach — no sessionStorage, no polling
        * RTL layout + smooth entrance animation
        * Hover / active effects on selection cards
        * Safe fallback when pos_restaurant is not installed
        * Clean patch of PosStore + Chrome template extension
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': ['point_of_sale'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            # CSS first so it is available when the component mounts
            'pos_session_type_selector/static/src/css/session_type_selector.css',
            # Template before JS so the t-name is registered
            'pos_session_type_selector/static/src/xml/session_type_selector.xml',
            'pos_session_type_selector/static/src/js/session_type_selector.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
