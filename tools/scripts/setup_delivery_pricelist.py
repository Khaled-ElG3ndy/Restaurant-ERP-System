# أسعار تطبيقات التوصيل: كل منتج +15% بالضبط (بدون تقريب) لطلبات عملاء التطبيقات.
#
# يُشغَّل داخل odoo-bin shell (المتغير env موجود هناك).
#   HOSNY_MODE=apply (الافتراضي): ينشئ/يحدّث الإعداد ويحفظ.
#   HOSNY_MODE=undo : يرجع نقاط البيع والعملاء كما كانوا (قوائم الأسعار تبقى مؤرشفة).
#
# الطريقة (أودو نفسه، بلا كود في نقطة البيع):
#   • «أسعار المطعم»: قائمة بلا قواعد = سعر المنتج كما هو. تصبح الافتراضية.
#   • «تطبيقات التوصيل +15%»: قاعدة واحدة على كل المنتجات، النسبة -15 (= +15%)
#     من سعر البيع، بلا تقريب: 52.00 ← 59.80.
#   • القائمتان متاحتان في كل نقاط البيع، و«قائمة الأسعار» لعملاء التطبيقات هي
#     قائمة التطبيقات. عند اختيار العميل في الكاشير تتغيّر أسعار الأصناف تلقائياً
#     (updatePricelistAndFiscalPosition)، والرسوم المكتوبة يدوياً لا تتغيّر.
import os

MODE = os.environ.get("HOSNY_MODE", "apply")
MARKUP = 15.0
BASE_NAME = "أسعار المطعم"
APPS_NAME = "تطبيقات التوصيل +15%"
# من نتيجة inspect_delivery_apps.py. «شركات التوصيل» (1311) و«ذا شفز مستحقات»
# (1318) ليسا تطبيقات يُطلب منها، فلا يدخلان.
APP_PARTNER_IDS = [1312, 1313, 1314, 1315, 1316, 1317]

Pricelist = env["product.pricelist"].with_context(active_test=False)
configs = env["pos.config"].search([])
companies = configs.company_id
partners = env["res.partner"].browse(APP_PARTNER_IDS).exists()


def find(name):
    return Pricelist.search([("name", "=", name)], limit=1)


if MODE == "undo":
    configs.write({"use_pricelist": False, "pricelist_id": False, "available_pricelist_ids": [(5, 0, 0)]})
    for company in companies:
        for partner in partners:
            partner.with_company(company).property_product_pricelist = False
    find(APPS_NAME).active = False
    env.cr.commit()
    print("تم الرجوع: نقاط البيع بلا قوائم أسعار، وعملاء التطبيقات على القائمة الافتراضية.")
else:
    currencies = configs.currency_id
    if len(currencies) != 1:
        raise SystemExit("نقاط البيع بعملات مختلفة: %s — لم يتم تغيير شيء." % currencies.mapped("name"))
    currency = currencies

    base = find(BASE_NAME)
    if not base:
        base = Pricelist.create({"name": BASE_NAME, "currency_id": currency.id, "company_id": False})
    base.write({"active": True, "item_ids": [(5, 0, 0)]})

    apps = find(APPS_NAME)
    if not apps:
        apps = Pricelist.create({"name": APPS_NAME, "currency_id": currency.id, "company_id": False})
    apps.write({
        "active": True,
        "item_ids": [(5, 0, 0), (0, 0, {
            "applied_on": "3_global",
            "compute_price": "percentage",
            "base": "list_price",
            "percent_price": -MARKUP,
        })],
    })

    configs.write({
        "use_pricelist": True,
        "pricelist_id": base.id,
        "available_pricelist_ids": [(6, 0, [base.id, apps.id])],
    })
    for company in companies:
        for partner in partners:
            partner.with_company(company).property_product_pricelist = apps
    env.cr.commit()

    print("\n========== تم ==========")
    print("القائمة الافتراضية: %s (id %s)" % (base.name, base.id))
    print("قائمة التطبيقات: %s (id %s) — %s" % (apps.name, apps.id, apps.item_ids.price))
    for c in configs:
        print("نقطة %s: قوائم الأسعار مفعلة=%s | الافتراضية=%s | المتاحة=%s" % (
            c.name, c.use_pricelist, c.pricelist_id.name, ", ".join(c.available_pricelist_ids.mapped("name"))))
    print("\nعملاء التطبيقات:")
    for partner in partners:
        print("  %s: %s" % (partner.name, ", ".join(
            "%s=%s" % (company.name, partner.with_company(company).property_product_pricelist.name)
            for company in companies)))

    print("\nأمثلة أسعار (سعر المطعم ← سعر التطبيقات):")
    products = env["product.product"].search(
        [("available_in_pos", "=", True), ("list_price", ">", 0)], limit=8, order="list_price desc")
    for product in products:
        normal = base._get_product_price(product, 1.0)
        app = apps._get_product_price(product, 1.0)
        print("  %s: %.2f ← %.2f" % (product.display_name, normal, app))
    print("\nحدّث صفحة نقطة البيع (Ctrl+Shift+R) لتظهر الأسعار الجديدة.")
