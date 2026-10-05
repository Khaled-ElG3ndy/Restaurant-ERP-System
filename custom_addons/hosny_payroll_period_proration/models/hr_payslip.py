from odoo import api, models


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    @api.model
    def _get_payslip_lines(self, contract_ids, payslip_id):
        contextual_self = self.with_context(
            hosny_proration_payslip_id=payslip_id,
            hosny_proration_cache={},
        )
        return super(HrPayslip, contextual_self)._get_payslip_lines(
            contract_ids, payslip_id
        )

