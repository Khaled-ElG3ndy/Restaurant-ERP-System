from markupsafe import Markup, escape

from odoo import api, fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    # ملاحظات الفاتورة (عملاء الأجل وشركات التوصيل): تُكتب من نقطة البيع قبل
    # الإغلاق، وتُطبع على فاتورة العميل وتُنسخ إلى فاتورة المحاسبة.  حقل منفصل
    # عن general_customer_note عن قصد: ذاك ملاحظة للمطبخ، يعدّه أودو تغييراً
    # يُرسل للتحضير ويطبعه على تذاكر المطبخ.
    hosny_invoice_note = fields.Text(
        "ملاحظات الفاتورة",
        copy=False,
        help="تُطبع على فاتورة العميل وتُنسخ إلى ملاحظات فاتورة المحاسبة، ولا تُرسل للمطبخ.",
    )

    def _hosny_invoice_note_html(self):
        orders = self.filtered(lambda o: (o.hosny_invoice_note or "").strip())
        if not orders:
            return False
        paragraphs = []
        for order in orders:
            text = escape(order.hosny_invoice_note.strip()).replace("\n", Markup("<br/>"))
            if len(self) > 1:
                text = Markup("<strong>%s:</strong> %s") % (order.name, text)
            paragraphs.append(Markup("<p>%s</p>") % text)
        return Markup("").join(paragraphs)

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        note = self._hosny_invoice_note_html()
        if note:
            vals["narration"] = note
        return vals

    @api.model
    def _hosny_clean_invoice_note(self, note):
        return (note or "").strip()[:1000] or False

    def hosny_set_invoice_note(self, note):
        """تعديل الملاحظة بعد الدفع (من شاشة الإيصال): الطلب وفاتورته معاً."""
        note = self._hosny_clean_invoice_note(note)
        for order in self:
            order.hosny_invoice_note = note
            if order.account_move:
                # The invoice may be posted and the cashier has no accounting
                # rights; only its notes change, never an amount or a line.
                order.account_move.sudo().narration = order.account_move.pos_order_ids._hosny_invoice_note_html()
        return note or ""
