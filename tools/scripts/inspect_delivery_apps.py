# فحص تطبيقات التوصيل في نقطة البيع — قراءة فقط، لا يغيّر أي بيانات.
# يُشغَّل داخل: odoo-bin shell (المتغير env موجود هناك)
from datetime import timedelta

from odoo import fields

TERMS = [
    "هنقر", "هنجر", "hunger", "كيتا", "keeta", "جاهز", "jahez", "مرسول", "mrsool",
    "تويو", "toyou", "طلبات", "talabat", "شفز", "chefz", "نينجا", "ninja", "كريم",
    "careem", "تطبيق", "توصيل", "delivery",
]
since = fields.Datetime.now() - timedelta(days=90)


def any_name(model, terms=TERMS):
    domain = ["|"] * (len(terms) - 1) + [("name", "ilike", t) for t in terms]
    return env[model].with_context(active_test=False).search(domain)


def line(*parts):
    print(" | ".join(str(p) for p in parts))


print("\n========== 1) نقاط البيع وقوائم الأسعار ==========")
for c in env["pos.config"].search([]):
    line(
        "نقطة %s: %s" % (c.id, c.name),
        "قوائم الأسعار مفعلة: %s" % c.use_pricelist,
        "الافتراضية: %s" % (c.pricelist_id.display_name or "-"),
        "المتاحة: %s" % (", ".join(c.available_pricelist_ids.mapped("display_name")) or "-"),
        "Presets: %s %s" % (c.use_presets, ", ".join(c.available_preset_ids.mapped("name"))),
    )

print("\n========== 2) قوائم الأسعار الموجودة ==========")
for pl in env["product.pricelist"].with_context(active_test=False).search([]):
    line(
        "قائمة %s: %s" % (pl.id, pl.display_name),
        "نشطة" if pl.active else "مؤرشفة",
        "عدد القواعد: %s" % len(pl.item_ids),
        "; ".join("%s → %s" % (i.name, i.price) for i in pl.item_ids[:5]),
    )

print("\n========== 3) أنواع الفواتير (آخر 90 يوم) ==========")
if "pos.order.type" in env:
    for t in env["pos.order.type"].with_context(active_test=False).search([]):
        n = env["pos.order"].search_count([("order_type_id", "=", t.id), ("date_order", ">=", since)])
        line("نوع %s: %s" % (t.id, t.name), "كود: %s" % t.code, "نشط" if t.active else "مؤرشف", "طلبات: %s" % n)
else:
    print("لا يوجد موديول أنواع الفواتير")

print("\n========== 4) Presets أودو ==========")
for p in env["pos.preset"].with_context(active_test=False).search([]):
    line("preset %s: %s" % (p.id, p.name), "قائمة أسعار: %s" % (p.pricelist_id.display_name or "-"))

print("\n========== 5) عملاء أسماؤهم تشبه تطبيقات التوصيل ==========")
for p in any_name("res.partner"):
    orders = env["pos.order"].search([("partner_id", "=", p.id), ("date_order", ">=", since)])
    line(
        "عميل %s: %s" % (p.id, p.name),
        "جوال: %s" % (p.phone or "-"),
        "طلبات 90 يوم: %s" % len(orders),
        "إجمالي: %.2f" % sum(orders.mapped("amount_total")),
        "قائمة أسعاره: %s" % (p.property_product_pricelist.display_name or "-"),
        "نشط" if p.active else "مؤرشف",
    )

print("\n========== 6) أكثر 15 عميل طلبات في نقطة البيع (90 يوم) ==========")
for partner, count, total in env["pos.order"]._read_group(
    [("date_order", ">=", since), ("partner_id", "!=", False)],
    ["partner_id"], ["__count", "amount_total:sum"], order="__count desc", limit=15,
):
    line("عميل %s: %s" % (partner.id, partner.name), "طلبات: %s" % count, "إجمالي: %.2f" % (total or 0))

print("\n========== 7) طرق الدفع (90 يوم) ==========")
usage = {
    method.id: (count, total)
    for method, count, total in env["pos.payment"]._read_group(
        [("payment_date", ">=", since)], ["payment_method_id"], ["__count", "amount:sum"]
    )
}
for m in env["pos.payment.method"].with_context(active_test=False).search([]):
    count, total = usage.get(m.id, (0, 0))
    line(
        "طريقة %s: %s" % (m.id, m.name),
        "نوع: %s" % m.type,
        "مدفوعات: %s" % count,
        "إجمالي: %.2f" % (total or 0),
        "نقاط البيع: %s" % (", ".join(m.config_ids.mapped("name")) or "-"),
    )

print("\n========== 8) عدد المنتجات في نقطة البيع ==========")
print(env["product.template"].search_count([("available_in_pos", "=", True)]))
print("\nانتهى — لم يتم تغيير أي شيء.")
