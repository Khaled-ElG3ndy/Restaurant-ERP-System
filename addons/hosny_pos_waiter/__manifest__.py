{
    "name": "Hosny POS Waiter",
    "version": "19.0.1.1.0",
    "category": "Point of Sale",
    "summary": "حساب «المتر»: طلبات محلي على الطاولات فقط — بلا سفري ولا دفع ولا تسديد",
    "description": """
حساب المتر (طلب 2026-10-09)
===========================

علامة «متر» على المستخدم، بجانب «نقاط البيع المسموحة» (hosny_pos_branch_access):

* يفتح نقطة بيع فرعه فقط، وعلى وردية فتحها الكاشير — لا يفتح وردية ولا يغلقها.
* يعمل طلبات محلي على الطاولات ويرسلها للمطبخ؛ السفري لا يظهر عنده أصلاً.
* لا دفع، ولا تسديد فواتير، ولا استرداد، ولا تقسيم، ولا إيداع / سحب.

القيود على الخادم أيضاً (pos.order و pos.payment و pos.session)، فلا يكفي
تعديل الشاشة لتجاوزها. المدير ومسؤول النظام لا تنطبق عليهم العلامة.
""",
    "author": "Hosny",
    "depends": [
        "point_of_sale",
        "pos_restaurant",
        "pos_hr",
        "hosny_pos_branch_access",
        "hosny_pos_printer_matrix",
        "pos_entry_selector",
        "hosny_pos_home",
        "hosny_pos_controls",
    ],
    "data": [
        "views/res_users_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "hosny_pos_waiter/static/src/js/waiter.js",
            "hosny_pos_waiter/static/src/xml/waiter.xml",
            "hosny_pos_waiter/static/src/css/waiter.css",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
