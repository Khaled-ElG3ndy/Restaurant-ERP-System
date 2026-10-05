from odoo import fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    # بيانات رأس فاتورة العميل (تصميم FERP). كل فرع نقطة بيع على نفس الشركة،
    # فبيانات الفرع تُحفظ هنا لا على الشركة؛ الفارغ منها يرجع لبيانات الشركة.
    hosny_receipt_title = fields.Char(
        "اسم المطعم على الفاتورة",
        help="السطر الكبير تحت الشعار، ويُكتب أيضاً كاسم البائع في رمز QR الضريبي.",
    )
    hosny_receipt_vat = fields.Char(
        "الرقم الضريبي على الفاتورة",
        help="يُطبع بجانب «الرقم الضريبي» ويُكتب في رمز QR. فارغ = الرقم الضريبي للشركة.",
    )
    hosny_receipt_address = fields.Char("العنوان على الفاتورة")
    hosny_receipt_phone = fields.Char(
        "الجوال على الفاتورة", help="يُطبع في آخر الفاتورة بعد «الجوال:»."
    )
