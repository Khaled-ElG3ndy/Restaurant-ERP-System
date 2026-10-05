{
    'name': 'Hosny POS Home',
    'version': '19.0.1.0.0',
    'category': 'Point of Sale',
    'summary': 'الشاشة الرئيسية لنقطة البيع: الفرع، الكاشير، ملخص اليوم والاختصارات',
    'description': """
الشاشة الرئيسية (على طريقة FERP): أول ما يظهر عند فتح نقطة البيع بدل بطاقة
«إلغاء قفل الكاشير». تعرض الفرع والساعة والتاريخ الهجري، الكاشير والوردية،
مبيعات اليوم وعدد الطلبات والطلبات المفتوحة، آخر الطلبات وطرق الدفع، واختصارات:
المبيعات، الطاولات، الطلبات، إيداع / سحب، تقرير الوردية، إغلاق الوردية.

يعمل فقط مع «الكاشير أولاً» (pos_entry_selector) وبلا pos_hr. لا حقول مخزنة؛
الملخص قراءة فقط من pos.session.hosny_home_summary.
""",
    'author': 'Hosny',
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_entry_selector', 'hosny_pos_skin'],
    'assets': {
        'point_of_sale._assets_pos': [
            'hosny_pos_home/static/src/js/home_screen.js',
            'hosny_pos_home/static/src/xml/home_screen.xml',
            'hosny_pos_home/static/src/css/home_screen.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
