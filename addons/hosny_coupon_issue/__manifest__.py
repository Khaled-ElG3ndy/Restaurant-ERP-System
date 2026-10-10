{
    "name": "Hosny Coupon Issue",
    "version": "19.0.1.0.0",
    "author": "Hosny",
    "category": "Sales",
    "summary": "إصدار كوبونات الخصم المدفوعة من المبيعات: فاتورة على حساب «كوبونات» (التزام) ودفع نقدي/بنك/أجل، "
               "والاستخدام في نقطة البيع يقفل نفس الالتزام",
    "depends": ["sale_management", "account", "loyalty", "point_of_sale", "pos_loyalty", "hosny_pos_controls"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "report/coupon_report.xml",
        "views/coupon_issue_views.xml",
        "views/pos_config_views.xml",
        "views/loyalty_card_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "license": "LGPL-3",
}
