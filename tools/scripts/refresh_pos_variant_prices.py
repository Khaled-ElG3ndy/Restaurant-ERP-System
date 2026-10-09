# أسعار الأحجام/المتغيرات تظهر صفراً في نقطة البيع والوردية مفتوحة.
#
# السبب: نقطة البيع لا تعيد تحميل كل الأصناف عند فتحها؛ تطلب من السيرفر فقط
# ما تغيّر تاريخ تعديله (write_date) بعد آخر تحميل. سعر الحجم يأتي من «السعر
# الإضافي» لقيمة الخاصية (ربع كيلو +46…)، وتعديله لا يلمس تاريخ تعديل الصنف
# نفسه، فيبقى المتصفح على السعر القديم (صفر).
#
# هذا السكربت يلمس تاريخ تعديل أصناف نقطة البيع ذات المتغيرات فيعيد المتصفح
# تحميلها عند فتح نقطة البيع بـ ?from_backend=True. لا يغيّر أي سعر.
#
# يُشغَّل داخل odoo-bin shell (المتغير env موجود هناك).
#   HOSNY_MODE=check (الافتراضي): يعرض الأصناف المعنية — لا يغيّر شيئاً.
#   HOSNY_MODE=apply : يلمس تاريخ التعديل.
#   HOSNY_PRODUCT=كبدة : صنف معيّن فقط (الافتراضي: كل أصناف نقطة البيع ذات المتغيرات).
import os

MODE = os.environ.get("HOSNY_MODE", "check")
NAME = os.environ.get("HOSNY_PRODUCT", "").strip()

Template = env["product.template"]
domain = [("available_in_pos", "=", True), ("product_variant_count", ">", 1)]
if NAME:
    domain.append(("name", "ilike", NAME))
templates = Template.search(domain)
variants = templates.product_variant_ids

print("أصناف نقطة البيع ذات المتغيرات: %s صنف، %s متغير" % (len(templates), len(variants)))
for template in templates[:30]:
    prices = "، ".join(
        "%s %.2f" % (", ".join(v.product_template_attribute_value_ids.mapped("name")) or v.display_name, v.lst_price)
        for v in template.product_variant_ids
    )
    print("  %s — %s" % (template.name, prices))
if len(templates) > 30:
    print("  … و%s صنف آخر" % (len(templates) - 30))

if MODE == "apply" and templates:
    env.cr.execute("UPDATE product_template SET write_date = now() at time zone 'UTC' WHERE id IN %s", [tuple(templates.ids)])
    env.cr.execute("UPDATE product_product SET write_date = now() at time zone 'UTC' WHERE id IN %s", [tuple(variants.ids)])
    env.cr.execute(
        "UPDATE product_template_attribute_value SET write_date = now() at time zone 'UTC' WHERE product_tmpl_id IN %s",
        [tuple(templates.ids)],
    )
    env.cr.commit()
    print("\nتم. افتح نقطة البيع من الرابط بـ ?from_backend=True ثم Ctrl+Shift+R على كل جهاز.")
else:
    print("\nمعاينة فقط — لم يتغير شيء. للتنفيذ: HOSNY_MODE=apply")
