from odoo import fields, models


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"

    hosny_contract_version_id = fields.Many2one(
        "hr.version",
        string="نسخة عقد الموظف",
        index=True,
        copy=False,
        ondelete="set null",
        help="نسخة بيانات الموظف التي أنشأت منها استحقاقات الإجازة السنوية.",
    )
