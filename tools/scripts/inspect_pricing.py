# فحص الأسعار في نقاط البيع — قراءة فقط، لا يغيّر شيئاً.
#
# يُشغَّل داخل odoo-bin shell (المتغير env موجود هناك).
#   HOSNY_PRODUCTS=عصير موز,ريش ضاني : أصناف للعرض (الافتراضي: أول 8 أصناف نقطة بيع).
#
# يعرض: إعداد قوائم الأسعار في كل نقطة بيع، قائمة أسعار عملاء التطبيقات، قوائم
# الأسعار وقواعدها، ثم سعر كل صنف كما يحسبه أودو بكل قائمة مستخدمة.
import os

APP_PARTNER_IDS = [1312, 1313, 1314, 1315, 1316, 1317]
names = [n.strip() for n in os.environ.get("HOSNY_PRODUCTS", "").split(",") if n.strip()]

configs = env["pos.config"].search([], order="id")
Pricelist = env["product.pricelist"].with_context(active_test=False)

print("══ نقاط البيع")
used = Pricelist.browse()
for c in configs:
    used |= c.pricelist_id | c.available_pricelist_ids
    print("  %s (id %s): قوائم الأسعار %s — الافتراضية: %s — المتاحة: %s" % (
        c.name, c.id, "مفعّلة" if c.use_pricelist else "مقفولة",
        c.pricelist_id.name or "—", "، ".join(c.available_pricelist_ids.mapped("name")) or "—"))

print("\n══ عملاء التطبيقات")
for partner in env["res.partner"].browse(APP_PARTNER_IDS).exists():
    for company in configs.company_id:
        pl = partner.with_company(company).property_product_pricelist
        used |= pl
        print("  %s [%s]: %s" % (partner.name, company.name, pl.name or "—"))

print("\n══ قوائم الأسعار")
for pl in Pricelist.search([], order="id"):
    rules = []
    for item in pl.item_ids:
        if item.compute_price == "percentage":
            rules.append("%s%% على %s" % (-item.percent_price, item.applied_on))
        elif item.compute_price == "fixed":
            rules.append("سعر ثابت %s على %s" % (item.fixed_price, item.applied_on))
        else:
            rules.append("معادلة على %s" % item.applied_on)
    print("  %s (id %s)%s: %s" % (
        pl.name, pl.id, "" if pl.active else " [مؤرشفة]", "، ".join(rules) or "بلا قواعد = سعر الصنف كما هو"))

Product = env["product.product"]
if names:
    products = Product.browse()
    for name in names:
        products |= Product.search([("available_in_pos", "=", True), ("name", "ilike", name)], limit=8)
else:
    products = Product.search([("available_in_pos", "=", True), ("list_price", ">", 0)], limit=8, order="id")

print("\n══ أسعار الأصناف (قبل الضريبة)")
pricelists = used.filtered("id")
for product in products:
    parts = ["سعر البيع %.2f" % product.lst_price]
    for pl in pricelists:
        price = pl._get_product_price(product, 1.0)
        mark = "" if abs(price - product.lst_price) < 0.005 else "  ← مختلف"
        parts.append("%s: %.2f%s" % (pl.name, price, mark))
    print("  %s — %s" % (product.display_name, " | ".join(parts)))

print("\nقراءة فقط — لم يتغير شيء.")
