from odoo import api, fields, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    # كود قاعدة صافي الراتب المستخدم في عرض الملخص.
    HOSNY_NET_CODE = "NET"

    hosny_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        string="العملة",
        readonly=True,
    )
    hosny_is_computed = fields.Boolean(
        string="محتسبة",
        compute="_compute_hosny_summary",
        store=True,
        help="تصبح صحيحة بمجرد وجود بنود محتسبة للقسيمة.",
    )
    hosny_line_count = fields.Integer(
        string="عدد البنود المحتسبة",
        compute="_compute_hosny_summary",
        store=True,
    )
    hosny_net_amount = fields.Monetary(
        string="صافي الراتب",
        compute="_compute_hosny_summary",
        store=True,
        currency_field="hosny_currency_id",
    )

    @api.depends("line_ids", "line_ids.total", "line_ids.code")
    def _compute_hosny_summary(self):
        for payslip in self:
            lines = payslip.line_ids
            payslip.hosny_line_count = len(lines)
            payslip.hosny_is_computed = bool(lines)
            payslip.hosny_net_amount = sum(
                lines.filtered(
                    lambda line: line.code == payslip.HOSNY_NET_CODE
                ).mapped("total")
            )

    def action_hosny_compute_sheet(self):
        """احتساب القسيمة من الواجهة مع تحديث تلقائي للقيم المعروضة.

        دالة منفصلة عن ``compute_sheet`` عمدًا: النداءات البرمجية
        (الاعتماد، ومعالج إنشاء القسائم للموظفين) تستدعي ``compute_sheet``
        مباشرةً ولا يجوز أن تتأثر بسلوك مخصص للواجهة.

        الإرجاع هنا **قيمة عادية وليس action**، وهذا مقصود: عندما لا يُرجع
        الزر أي action يستبدله عميل الويب تلقائيًا بـ ``act_window_close``
        الذي يستدعي ``onClose`` فيُعيد تحميل السجل. أما إرجاع إشعار
        ``display_notification`` فيجعل إعادة التحميل مرهونة بتسلسل ``next``،
        وقد لا تحدث. المؤشرات المعروضة على النموذج (شارة «محتسبة»، وتبدّل
        الزر، وصافي الراتب) هي التأكيد المرئي، وتظهر فور إعادة التحميل.
        """
        self.compute_sheet()
        return True
