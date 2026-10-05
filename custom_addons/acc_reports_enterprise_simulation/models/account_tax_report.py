from odoo import api, fields, models


class AccountTaxReportWizard(models.TransientModel):
    _inherit = "account.tax.report.wizard"

    tax_report_type = fields.Selection(
        [
            ("general", "التقرير الضريبي العام"),
            ("by_account_tax", "التجميع حسب: الحساب < الضريبة"),
            ("by_tax_account", "التجميع حسب: الضريبة < الحساب"),
            ("eg_vat_return", "إقرار ضريبة القيمة المضافة (EG)"),
            ("eg_withholding", "ضرائب خصم المنبع (EG)"),
            ("eg_schedule", "ضرائب الجدول (EG)"),
            ("eg_other", "ضرائب أخرى (EG)"),
        ],
        string="Tax Report Type",
        required=True,
        default="eg_vat_return",
    )
    currency_unit = fields.Selection(
        [
            ("base_decimal", "Currency with decimals"),
            ("base", "Currency"),
            ("thousand", "Thousands"),
            ("million", "Millions"),
        ],
        string="Currency Unit",
        required=True,
        default="base_decimal",
    )

    def check_report(self):
        action = super().check_report()
        form = (action.get("data") or {}).get("form") or {}
        form.update(self.read(["tax_report_type", "currency_unit"])[0])
        currency_code = self.company_id.currency_id.name or self.company_id.currency_id.symbol
        form["currency_unit_options"] = [
            {"value": "base_decimal", "label": "في %s." % currency_code},
            {"value": "base", "label": "في %s" % currency_code},
            {"value": "thousand", "label": "في K%s" % currency_code},
            {"value": "million", "label": "في M%s" % currency_code},
        ]
        form["currency_label"] = next(
            option["label"]
            for option in form["currency_unit_options"]
            if option["value"] == form["currency_unit"]
        )
        form["tax_report_type_options"] = [
            {"value": key, "label": label}
            for key, label in self._fields["tax_report_type"].selection
        ]
        form["tax_report_type_label"] = dict(self._fields["tax_report_type"].selection).get(
            self.tax_report_type,
            self.tax_report_type,
        )
        return action
