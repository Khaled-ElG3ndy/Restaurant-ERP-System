from datetime import date

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HosnyHrSalaryAdjustment(models.Model):
    _name = "hosny.hr.salary.adjustment"
    _description = "تعديل راتب"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="البيان",
        required=True,
        tracking=True,
    )
    employee_id = fields.Many2one(
        "hr.employee",
        string="الموظف",
        required=True,
        index=True,
        tracking=True,
        check_company=True,
        domain="[('company_id', '=', company_id)]",
    )
    version_id = fields.Many2one(
        "hr.version",
        string="نسخة عقد الموظف",
        required=True,
        index=True,
        tracking=True,
        check_company=True,
        domain="[('employee_id', '=', employee_id), ('company_id', '=', company_id)]",
        help="يربط التعديل بنسخة العقد الصحيحة حتى لا ينتقل إلى فترة عقد أخرى.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="الشركة",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="العملة",
        related="company_id.currency_id",
        readonly=True,
    )
    adjustment_type = fields.Selection(
        [
            ("addition", "إضافة"),
            ("deduction", "استقطاع"),
        ],
        string="نوع التعديل",
        required=True,
        default="addition",
        tracking=True,
    )
    category = fields.Selection(
        [
            ("bonus", "مكافأة"),
            ("commission", "عمولة"),
            ("overtime", "عمل إضافي"),
            ("allowance", "بدل إضافي"),
            ("penalty", "جزاء"),
            ("loan", "قسط سلفة"),
            ("other", "أخرى"),
        ],
        string="التصنيف",
        required=True,
        default="other",
        tracking=True,
    )
    amount = fields.Monetary(
        string="القيمة",
        required=True,
        currency_field="currency_id",
        tracking=True,
    )
    recurrence = fields.Selection(
        [
            ("once", "مرة واحدة"),
            ("monthly", "شهري"),
        ],
        string="التكرار",
        required=True,
        default="once",
        tracking=True,
    )
    date_start = fields.Date(
        string="تاريخ البداية",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    date_end = fields.Date(
        string="تاريخ النهاية",
        tracking=True,
        help="اتركه فارغًا للتعديل الشهري غير محدد النهاية.",
    )
    notes = fields.Text(
        string="ملاحظات",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "مسودة"),
            ("approved", "معتمد"),
            ("cancelled", "ملغي"),
        ],
        string="الحالة",
        required=True,
        default="draft",
        copy=False,
        tracking=True,
    )
    signed_amount = fields.Monetary(
        string="القيمة المؤثرة",
        compute="_compute_signed_amount",
        currency_field="currency_id",
    )
    is_effective = fields.Boolean(
        string="ساري حاليًا",
        compute="_compute_is_effective",
    )

    _amount_positive = models.Constraint(
        "CHECK(amount > 0)",
        "يجب أن تكون قيمة تعديل الراتب أكبر من صفر.",
    )

    @api.depends("adjustment_type", "amount")
    def _compute_signed_amount(self):
        for adjustment in self:
            adjustment.signed_amount = (
                adjustment.amount
                if adjustment.adjustment_type == "addition"
                else -adjustment.amount
            )

    @api.depends("state", "recurrence", "date_start", "date_end")
    def _compute_is_effective(self):
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        for adjustment in self:
            adjustment.is_effective = adjustment._is_effective_for_period(
                month_start, today
            )

    @api.constrains("date_start", "date_end", "recurrence")
    def _check_dates(self):
        for adjustment in self:
            if (
                adjustment.date_end
                and adjustment.date_start
                and adjustment.date_end < adjustment.date_start
            ):
                raise ValidationError(
                    _("تاريخ نهاية تعديل الراتب لا يمكن أن يسبق تاريخ البداية.")
                )
            if (
                adjustment.recurrence == "once"
                and adjustment.date_end
                and adjustment.date_end != adjustment.date_start
            ):
                raise ValidationError(
                    _("التعديل لمرة واحدة يجب أن يكون له تاريخ واحد فقط.")
                )

    @api.constrains("employee_id", "version_id", "company_id")
    def _check_employee_version(self):
        for adjustment in self:
            if adjustment.version_id.employee_id != adjustment.employee_id:
                raise ValidationError(
                    _("نسخة العقد المختارة لا تخص الموظف المحدد.")
                )
            if adjustment.employee_id.company_id != adjustment.company_id:
                raise ValidationError(
                    _("شركة التعديل يجب أن تطابق شركة الموظف.")
                )

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        for adjustment in self:
            if adjustment.employee_id:
                adjustment.company_id = adjustment.employee_id.company_id
                adjustment.version_id = adjustment.employee_id.version_id
            else:
                adjustment.version_id = False

    @api.onchange("recurrence", "date_start")
    def _onchange_recurrence(self):
        for adjustment in self:
            if adjustment.recurrence == "once":
                adjustment.date_end = adjustment.date_start

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            employee = self.env["hr.employee"].browse(vals.get("employee_id")).exists()
            if employee:
                vals.setdefault("company_id", employee.company_id.id)
                vals.setdefault("version_id", employee.version_id.id)
            if (
                vals.get("recurrence", "once") == "once"
                and vals.get("date_start")
                and not vals.get("date_end")
            ):
                vals["date_end"] = vals["date_start"]
        return super().create(vals_list)

    def write(self, vals):
        protected_fields = {
            "employee_id",
            "version_id",
            "company_id",
            "adjustment_type",
            "category",
            "amount",
            "recurrence",
            "date_start",
            "date_end",
        }
        if protected_fields.intersection(vals) and any(
            adjustment.state == "approved" for adjustment in self
        ):
            raise UserError(
                _(
                    "لا يمكن تعديل بيانات تعديل راتب معتمد. أعده إلى مسودة أولًا."
                )
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft_or_cancelled(self):
        if any(adjustment.state == "approved" for adjustment in self):
            raise UserError(
                _("لا يمكن حذف تعديل راتب معتمد. ألغِ اعتماده أولًا.")
            )

    def action_approve(self):
        for adjustment in self:
            if adjustment.state != "draft":
                raise UserError(_("يمكن اعتماد تعديلات الرواتب الموجودة في المسودة فقط."))
        self.write({"state": "approved"})
        return True

    def action_cancel(self):
        self.write({"state": "cancelled"})
        return True

    def action_reset_to_draft(self):
        self.write({"state": "draft"})
        return True

    def _is_effective_for_period(self, date_from, date_to):
        self.ensure_one()
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if self.state != "approved" or not date_from or not date_to:
            return False
        if self.recurrence == "once":
            return date_from <= self.date_start <= date_to
        effective_end = self.date_end or date.max
        return self.date_start <= date_to and effective_end >= date_from
