from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = "hr.department"

    hosny_payroll_expense_account_id = fields.Many2one(
        "account.account",
        string="حساب مصروف الرواتب",
        check_company=True,
        domain="[('account_type', 'like', 'expense')]",
        help=(
            "عند تحديده، تُرحَّل مصروفات رواتب موظفي هذا القسم إلى هذا الحساب "
            "بدلًا من الحساب الافتراضي المعرَّف في قاعدة الراتب. "
            "يؤثر فقط على البنود ذات الطبيعة المصروفية، ولا يمس حسابات "
            "الاستقطاعات أو التأمينات أو المستحق للموظفين."
        ),
    )
