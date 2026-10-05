{
    'name': 'Hosny POS Payment',
    'version': '19.0.1.0.0',
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
لا حقول ولا بيانات.
""",
    'author': 'Hosny',
    'depends': ['point_of_sale', 'pos_restaurant', 'hosny_pos_skin'],
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
