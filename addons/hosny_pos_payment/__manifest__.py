{
    'name': 'Hosny POS Payment',
    'version': '19.0.1.1.0',
    'category': 'Point of Sale',
    'summary': 'شاشة الدفع بتقسيمة FERP: ملخص الفاتورة، الدفع، والإجراءات والأرقام',
    'description': """
شاشة الدفع بنفس تقسيمة شاشة FERP وبشكل عصري، ثلاثة أعمدة:

* ملخص الفاتورة: عودة، عرض الفاتورة، القيمة والضريبة والخصم والإجمالي،
  ملاحظات الفاتورة، رقم الفاتورة والتاريخ والمستخدم، وطباعة.
* الدفع: الإجمالي والمدفوع والمتبقي، وسائل الدفع، أسطر الدفع، وإغلاق الفاتورة.
* الإجراءات: العميل، الفاتورة الضريبية، الكوبون، تقسيم الفاتورة، فئات النقد
  والأرقام.

القالب كله جديد (PaymentScreen.template) بأسماء أصناف خاصة به، فلا تمسه
تنسيقات شاشة الدفع القديمة في الموديولات الأخرى، بينما يبقى منطق أودو وكل
ما أضافته الموديولات الأخرى لسلوك الشاشة (الأجل، السفري، الملاحظات…) كما هو.
الخدمات والتوصيل وتسليم السائق تُكتب من ملخص الفاتورة: كل واحدة سطر بمنتج
خدمة خاص (data/fee_products.xml) يُحمَّل دائماً ولا يظهر في شبكة الأصناف
ولا يصل للمطبخ.
""",
    'author': 'Hosny',
    'depends': ['point_of_sale', 'pos_restaurant', 'hosny_pos_skin'],
    'data': [
        'data/fee_products.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hosny_pos_payment/static/src/js/payment_screen.js',
            'hosny_pos_payment/static/src/xml/payment_screen.xml',
            'hosny_pos_payment/static/src/css/payment_screen.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
