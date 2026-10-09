# نفس الصنف مرة ثانية في نقطة البيع ← تزيد الكمية بدل سطر جديد.
#
# أودو لا يدمج السطرين إلا إذا كانت وحدة قياس الصنف مفعّلاً عليها
# «Group Products in POS» (uom.uom.is_pos_groupable). أودو يفعّله لـ«Units» و«kg»
# فقط؛ الوحدات المضافة يدوياً («حبة»، «كوب»، «صحن»…) تبقى بدونه، فيُضاف كل ضغط
# في سطر منفصل.
#
# يُشغَّل داخل odoo-bin shell (المتغير env موجود هناك).
#   HOSNY_MODE=check (الافتراضي): يعرض وحدات أصناف نقطة البيع وحالة الدمج — لا يغيّر شيئاً.
#   HOSNY_MODE=apply : يفعّل الدمج على كل وحدة تستخدمها أصناف نقطة البيع.
#   HOSNY_PRODUCT=عصير موز : يعرض وحدة صنف معيّن للتأكد.
import os

MODE = os.environ.get("HOSNY_MODE", "check")
NAME = os.environ.get("HOSNY_PRODUCT", "").strip()

Product = env["product.product"].with_context(active_test=False)
products = Product.search([("available_in_pos", "=", True)])
by_uom = {}
for product in products:
    by_uom.setdefault(product.uom_id, []).append(product)

print("وحدات أصناف نقطة البيع:")
off = env["uom.uom"]
for uom, items in sorted(by_uom.items(), key=lambda kv: -len(kv[1])):
    flag = "✓ يدمج" if uom.is_pos_groupable else "✗ لا يدمج"
    print("  %-22s (id %s): %s صنف — %s" % (uom.name, uom.id, len(items), flag))
    if not uom.is_pos_groupable:
        off |= uom
        sample = "، ".join(p.display_name for p in items[:5])
        print("      مثل: %s%s" % (sample, " …" if len(items) > 5 else ""))

if NAME:
    for product in products.filtered(lambda p: NAME in (p.display_name or "")):
        print("\n«%s»: الوحدة %s — %s" % (
            product.display_name, product.uom_id.name,
            "يدمج" if product.uom_id.is_pos_groupable else "لا يدمج (هذا سبب السطر المنفصل)"))

if MODE == "apply":
    if off:
        off.sudo().write({"is_pos_groupable": True})
        env.cr.commit()
        print("\nفُعّل الدمج على: %s" % "، ".join(off.mapped("name")))
    else:
        print("\nكل الوحدات تدمج بالفعل — لا شيء للتغيير.")
    print("افتح نقطة البيع من «متابعة البيع» (أو ?from_backend=True) حتى يقرأ المتصفح الإعداد الجديد.")
else:
    print("\nمعاينة فقط — لم يتغير شيء. للتفعيل: HOSNY_MODE=apply")
