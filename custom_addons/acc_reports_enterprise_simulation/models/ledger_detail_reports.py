from odoo import fields, models


class AccountReportPartnerLedger(models.TransientModel):
    _inherit = "account.report.partner.ledger"

    unfold_all = fields.Boolean(string="التفاصيل", default=True)

    def _get_report_data(self, data):
        data = super()._get_report_data(data)
        data["form"].update(self.read(["unfold_all"])[0])
        return data


class AccountReportGeneralLedger(models.TransientModel):
    _inherit = "account.report.general.ledger"

    unfold_all = fields.Boolean(string="التفاصيل", default=False)

    def _get_report_data(self, data):
        records, data = super()._get_report_data(data)
        data["form"].update(self.read(["unfold_all"])[0])
        return records, data
