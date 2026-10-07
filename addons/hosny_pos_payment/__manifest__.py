{
    'name': 'Hosny POS Payment',
    'version': '19.0.1.9.1',
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

«تسديد الفواتير» بتقسيمة شاشة FERP: فلاتر (من/إلى تاريخ، النوع، الرقم، حالة
الدفع، الطاولة) وجدول فواتير الفرع من الخادم، مع طباعة فورية وعرض وتسديد
للمفتوحة وتصدير Excel.

اختيار العميل بتقسيمة FERP وبالعربية فقط: بحث بالجوال/الاسم/الكود، جدول مرقّم
يُفتح فيه عنوان العميل، ولوحة للعميل المحدد وطلباته والمفضلة.

«نقل الطلبات» بتقسيمة FERP خلف زر «تحويل»: جدول الأصناف (تحديد الكل =
تحويل كلي، بعضها أو جزء من الكمية = جزئي) ثم اختيار الدور والطاولة؛ الطاولة
المشغولة يُضاف المنقول إلى طلبها. يغني عن زرّي «تحويل جزئي» و«دمج الطاولات».

«مردود المبيعات» بتقسيمة FERP خلف «استرداد الأموال»: اختيار الفاتورة من نافذة
بحث، بطاقات الأصناف (المباعة والمتبقية) و«اختيار الكل»، جدول بكمية المردود
وسبب الإلغاء لكل صنف، سبب الاسترجاع، وملخص المردود. الحفظ يبني طلب الإرجاع
بطريقة أودو ويفتح الدفع بالطريقة المختارة، والأسهم تتصفح المرتجعات السابقة.
""",
    'author': 'Hosny',
    # hosny_pos_controls: شاشة «تسديد الفواتير» وزرّها منه، وهنا يُستبدل قالبها
    'depends': ['point_of_sale', 'pos_restaurant', 'hosny_pos_skin', 'pos_modern_ui', 'hosny_pos_controls'],
    'data': [
        'data/fee_products.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hosny_pos_payment/static/src/js/payment_screen.js',
            'hosny_pos_payment/static/src/xml/payment_screen.xml',
            'hosny_pos_payment/static/src/css/payment_screen.css',
            'hosny_pos_payment/static/src/js/payment_actions.js',
            'hosny_pos_payment/static/src/xml/payment_actions.xml',
            'hosny_pos_payment/static/src/css/payment_actions.css',
            'hosny_pos_payment/static/src/js/invoices_screen.js',
            'hosny_pos_payment/static/src/xml/invoices_screen.xml',
            'hosny_pos_payment/static/src/css/invoices_screen.css',
            'hosny_pos_payment/static/src/js/partner_list.js',
            'hosny_pos_payment/static/src/xml/partner_list.xml',
            'hosny_pos_payment/static/src/css/partner_list.css',
            'hosny_pos_payment/static/src/js/transfer_dialog.js',
            'hosny_pos_payment/static/src/xml/transfer_dialog.xml',
            'hosny_pos_payment/static/src/css/transfer_dialog.css',
            'hosny_pos_payment/static/src/js/returns_screen.js',
            'hosny_pos_payment/static/src/xml/returns_screen.xml',
            'hosny_pos_payment/static/src/css/returns_screen.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
