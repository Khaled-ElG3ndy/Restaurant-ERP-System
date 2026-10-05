{
    'name': 'Hosny POS Home',
    'version': '19.0.1.2.0',
    'category': 'Point of Sale',
    'summary': 'الشاشة الرئيسية لنقطة البيع على طريقة FERP: الوقت، الفرع، المزامنة والأزرار',
    'description': """
الشاشة الرئيسية (على طريقة FERP): أول ما يظهر عند فتح نقطة البيع بدل بطاقة
«إلغاء قفل الكاشير». خلفية زرقاء بنقش، واسم المطعم، ولوحة فيها ثلاث خانات
(الوقت والتاريخ، نقطة البيع والفرع، مزامنة السيرفر) وتحتها أزرار مربعة: المبيعات،
الطاولات، الطلبات والفواتير، إيداع / سحب، تقرير الوردية، الإعدادات (للمدير)،
إغلاق الوردية.

وشاشة الطاولات بنفس الألوان على خلفية فاتحة (static/src/css/floor_screen.css).

يعمل فقط مع «الكاشير أولاً» (pos_entry_selector) وبلا pos_hr. لا حقول مخزنة؛
تقرير الوردية قراءة فقط من pos.session.hosny_home_summary.
""",
    'author': 'Hosny',
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_entry_selector', 'hosny_pos_skin'],
    'data': [
        'views/pos_settings_action.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hosny_pos_home/static/src/js/home_screen.js',
            'hosny_pos_home/static/src/xml/home_screen.xml',
            'hosny_pos_home/static/src/css/home_screen.css',
            'hosny_pos_home/static/src/css/floor_screen.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
