{
    "name": "Hosny POS Partial Transfer",
    "version": "19.0.1.1.0",
    "category": "Point of Sale",
    "summary": "Restaurant POS partial table transfer for selected order lines",
    "description": """
19.0.1.1.0 (2026-10-02) — التحويل يعمل على أودو 19:
  • التحويل إلى طاولة فارغة كان يفشل («reading 'is_company'») لأي طلب بلا عميل.
  • «+» كان ينقل 0.0001 (دقة الوحدة في 19)؛ صار قطعة كاملة.
  • طلب الوجهة يُنشأ على الطاولة (محلي)، لا طلب سفري عائم.
  • ما أُرسل للمطبخ ينتقل مع الصنف: لا طباعة مكررة ولا «إلغاء» للصنف نفسه.
  • عنوان النافذة وعدد الأصناف بالعربية الصحيحة؛ الشكل في hosny_pos_skin (قسم 40).
""",
    "depends": ["point_of_sale", "pos_restaurant", "hosny_pos_controls"],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "hosny_pos_partial_transfer/static/src/js/partial_transfer_button.js",
            "hosny_pos_partial_transfer/static/src/js/partial_transfer_popup.js",
            "hosny_pos_partial_transfer/static/src/js/partial_transfer_pos_store.js",
            "hosny_pos_partial_transfer/static/src/js/partial_transfer_product_screen.js",
            "hosny_pos_partial_transfer/static/src/xml/partial_transfer_button.xml",
            "hosny_pos_partial_transfer/static/src/xml/partial_transfer_popup.xml",
            "hosny_pos_partial_transfer/static/src/scss/partial_transfer.scss",
        ],
    },
    "installable": True,
    "license": "LGPL-3",
}
