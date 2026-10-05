"""بيانات رأس الفاتورة من فاتورة FERP المصوَّرة (فرع المدينة، 10/2/2026).

لا نكتب فوق قيمة موجودة. فرعا جدة والرياض يأخذان الاسم على نفس نمط FERP
فقط؛ رقمهما الضريبي وعنوانهما وجوالهما غير معروفة هنا وتُكتب من الإعدادات.
"""

MADINAH = {
    "hosny_receipt_title": "مطاعم حسنى - المدينة",
    "hosny_receipt_vat": "302120759500003",
    "hosny_receipt_address": "حى العريض المدينة المنورة",
    "hosny_receipt_phone": "0501037666",
}
TITLES = {"جدة": "مطاعم حسنى - جدة", "الرياض": "مطاعم حسنى - الرياض"}


def migrate(cr, version):
    cr.execute("SELECT id, name FROM pos_config")
    for config_id, name in cr.fetchall():
        values = {}
        if "المدينة" in (name or ""):
            values = MADINAH
        else:
            for city, title in TITLES.items():
                if city in (name or ""):
                    values = {"hosny_receipt_title": title}
        for field, value in values.items():
            cr.execute(
                f"UPDATE pos_config SET {field} = %s WHERE id = %s AND COALESCE({field}, '') = ''",
                (value, config_id),
            )
