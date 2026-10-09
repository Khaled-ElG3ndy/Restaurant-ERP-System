{
    "name": "Hosny POS Printer Matrix",
    "version": "19.0.7.9.1",
    "category": "Point of Sale",
    "summary": "Per-printer routing by order type, copy count, receipt template, chief printer",
    "description": """
مصفوفة إعدادات طابعات التحضير — مكافئ شاشة «تعريف الطابعات» في FERP:
  • أنواع الفواتير (سفري / محلي / تيك أواي / عضو استبيان) لكل طابعة
  • عدد النسخ لكل نوع
  • اسم التقرير (قالب التذكرة) لكل نوع — الافتراضي «نسخة المطبخ» بتصميم FERP
  • Bundeled Receipt — تذكرة مجمّعة بكل المحطات
  • Is Chief — طابعة رئيسية تستقبل كل الأقسام
  • نوع الفاتورة على الطلب: السفري بلا طاولة والطاولة تعني محلي (شاشة وخادم)
  • ملاحظات المطبخ: ملاحظة الصنف في مربع بارز، وملاحظة الطلب داخل تذكرة
    الأصناف الجديدة، ولكل محطة تحضّر من الطلب حين تتغيّر أو تُحذف وحدها
""",
    "author": "STRX",
    "depends": ["point_of_sale", "pos_restaurant"],
    "data": [
        "security/ir.model.access.csv",
        "data/pos_order_type_data.xml",
        "data/ir_asset_data.xml",
        "views/pos_order_type_views.xml",
        "views/pos_printer_views.xml",
        "views/pos_order_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hosny_pos_printer_matrix/static/src/scss/printer_form.scss",
        ],
        "point_of_sale._assets_pos": [
            "hosny_pos_printer_matrix/static/src/app/product_routing.js",
            "hosny_pos_printer_matrix/static/src/app/render_lock.js",
            "hosny_pos_printer_matrix/static/src/app/printer_matrix.js",
            "hosny_pos_printer_matrix/static/src/app/order_type_rules.js",
            "hosny_pos_printer_matrix/static/src/app/order_type_button.js",
            "hosny_pos_printer_matrix/static/src/app/kitchen_ticket.js",
            "hosny_pos_printer_matrix/static/src/xml/order_type.xml",
            "hosny_pos_printer_matrix/static/src/xml/kitchen_ticket.xml",
            "hosny_pos_printer_matrix/static/src/scss/order_type.scss",
            "hosny_pos_printer_matrix/static/src/css/kitchen_ticket.css",
            "hosny_pos_printer_matrix/static/src/css/order_type_chip.css",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "license": "LGPL-3",
}
