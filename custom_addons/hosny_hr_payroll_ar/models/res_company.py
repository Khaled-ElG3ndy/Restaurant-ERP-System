from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = "res.company"

    hosny_social_insurance_enabled = fields.Boolean(
        string="تفعيل احتساب التأمينات الاجتماعية",
        default=False,
    )
    hosny_social_insurance_employee_rate = fields.Float(
        string="نسبة اشتراك الموظف (%)",
        digits=(5, 2),
        default=0.0,
    )
    hosny_social_insurance_employer_rate = fields.Float(
        string="نسبة اشتراك جهة العمل (%)",
        digits=(5, 2),
        default=0.0,
    )
    hosny_social_insurance_minimum_base = fields.Monetary(
        string="الحد الأدنى للأجر التأميني",
        currency_field="currency_id",
        default=0.0,
    )
    hosny_social_insurance_maximum_base = fields.Monetary(
        string="الحد الأقصى للأجر التأميني",
        currency_field="currency_id",
        default=0.0,
        help="اتركه صفرًا إذا لم يوجد حد أقصى.",
    )

    @api.constrains(
        "hosny_social_insurance_employee_rate",
        "hosny_social_insurance_employer_rate",
        "hosny_social_insurance_minimum_base",
        "hosny_social_insurance_maximum_base",
    )
    def _check_hosny_social_insurance_configuration(self):
        for company in self:
            rates = (
                company.hosny_social_insurance_employee_rate,
                company.hosny_social_insurance_employer_rate,
            )
            if any(rate < 0 or rate > 100 for rate in rates):
                raise ValidationError(
                    _("يجب أن تكون نسب التأمينات الاجتماعية بين صفر و100.")
                )
            if (
                company.hosny_social_insurance_minimum_base < 0
                or company.hosny_social_insurance_maximum_base < 0
            ):
                raise ValidationError(
                    _("حدود الأجر التأميني لا يمكن أن تكون أقل من صفر.")
                )
            if (
                company.hosny_social_insurance_maximum_base
                and company.hosny_social_insurance_maximum_base
                < company.hosny_social_insurance_minimum_base
            ):
                raise ValidationError(
                    _("الحد الأقصى للأجر التأميني يجب ألا يقل عن الحد الأدنى.")
                )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hosny_social_insurance_enabled = fields.Boolean(
        related="company_id.hosny_social_insurance_enabled",
        readonly=False,
    )
    hosny_social_insurance_employee_rate = fields.Float(
        related="company_id.hosny_social_insurance_employee_rate",
        readonly=False,
    )
    hosny_social_insurance_employer_rate = fields.Float(
        related="company_id.hosny_social_insurance_employer_rate",
        readonly=False,
    )
    hosny_social_insurance_minimum_base = fields.Monetary(
        related="company_id.hosny_social_insurance_minimum_base",
        readonly=False,
        currency_field="company_currency_id",
    )
    hosny_social_insurance_maximum_base = fields.Monetary(
        related="company_id.hosny_social_insurance_maximum_base",
        readonly=False,
        currency_field="company_currency_id",
    )
