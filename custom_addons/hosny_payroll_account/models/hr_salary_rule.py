from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    account_debit = fields.Many2one(
        "account.account",
        string="الحساب المدين",
        help=(
            "الحساب الذي تُسجَّل فيه قيمة القاعدة في الجانب المدين. "
            "إذا كانت قيمة القاعدة سالبة (استقطاع) فسيُقلب الطرف تلقائيًا "
            "وتُسجَّل في الجانب الدائن."
        ),
    )
    account_credit = fields.Many2one(
        "account.account",
        string="الحساب الدائن",
        help=(
            "الحساب الذي تُسجَّل فيه قيمة القاعدة في الجانب الدائن. "
            "إذا كانت قيمة القاعدة سالبة فسيُقلب الطرف تلقائيًا."
        ),
    )

    @api.constrains("account_debit", "account_credit", "company_id")
    def _check_hosny_account_company(self):
        """الحسابات المرتبطة بالقاعدة يجب أن تخص نفس شركة القاعدة."""
        for rule in self:
            if not rule.company_id:
                continue
            for account in (rule.account_debit, rule.account_credit):
                if not account:
                    continue
                if not account.with_company(rule.company_id).code:
                    raise ValidationError(
                        _(
                            "الحساب %(account)s غير معرَّف في شركة قاعدة الراتب %(rule)s.",
                            account=account.display_name,
                            rule=rule.display_name,
                        )
                    )
