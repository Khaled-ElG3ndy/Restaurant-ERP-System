from odoo import api, models


class HrPayrollStructureType(models.Model):
    _inherit = "hr.payroll.structure.type"

    @api.model
    def _hosny_apply_arabic_names(self):
        name_mapping = {
            "Employee": "الموظف",
            "Worker": "العامل",
        }
        records = self.with_context(active_test=False)
        for english_name, arabic_name in name_mapping.items():
            records.search([("name", "=", english_name)]).write(
                {"name": arabic_name}
            )
        return True


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    @api.model
    def _hosny_apply_arabic_names(self):
        name_mapping = {
            "Standard 40 hours/week": "دوام قياسي 40 ساعة/أسبوع",
            "Opening time": "ساعات العمل",
        }
        records = self.with_context(active_test=False)
        for english_name, arabic_name in name_mapping.items():
            records.search([("name", "=", english_name)]).write(
                {"name": arabic_name}
            )
        return True

