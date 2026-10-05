from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHosnyHrPayrollAr(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "موظف اختبار الرواتب",
                "company_id": cls.env.company.id,
                "wage": 10_000,
            }
        )
        cls.leave_type = cls.env["hr.leave.type"].create(
            {
                "name": "إجازة سنوية للاختبار",
                "requires_allocation": True,
                "request_unit": "day",
                "unpaid": False,
                "allocation_validation_type": "no_validation",
                "company_id": cls.env.company.id,
                "work_entry_type_id": cls.env.ref(
                    "hr_work_entry.work_entry_type_legal_leave"
                ).id,
            }
        )

    def test_salary_totals_and_effective_adjustments(self):
        self.employee.write(
            {
                "hosny_housing_allowance": 2_000,
                "hosny_transport_allowance": 500,
                "hosny_other_allowance": 250,
                "hosny_social_insurance_reference": 8_000,
            }
        )
        adjustment = self.env["hosny.hr.salary.adjustment"].create(
            {
                "name": "مكافأة شهرية",
                "employee_id": self.employee.id,
                "adjustment_type": "addition",
                "category": "bonus",
                "amount": 1_000,
                "recurrence": "monthly",
                "date_start": date.today().replace(day=1),
            }
        )
        adjustment.action_approve()

        components = self.employee._hosny_get_payroll_components(
            date.today().replace(day=1), date.today()
        )
        self.assertEqual(components["total_allowances"], 2_750)
        self.assertEqual(components["fixed_compensation"], 12_750)
        self.assertEqual(components["additions"], 1_000)
        self.assertEqual(components["net_before_tax_and_insurance"], 13_750)

    def test_approved_adjustment_must_be_reset_before_edit(self):
        adjustment = self.env["hosny.hr.salary.adjustment"].create(
            {
                "name": "استقطاع اختبار",
                "employee_id": self.employee.id,
                "adjustment_type": "deduction",
                "amount": 100,
                "date_start": date.today(),
            }
        )
        adjustment.action_approve()
        with self.assertRaises(UserError):
            adjustment.amount = 200
        adjustment.action_reset_to_draft()
        adjustment.amount = 200
        self.assertEqual(adjustment.amount, 200)

    def test_annual_leave_creates_real_allocation(self):
        self.employee.write(
            {
                "hosny_annual_leave_type_id": self.leave_type.id,
                "hosny_annual_leave_days": 21,
            }
        )
        action = self.employee.action_hosny_sync_annual_leave()
        allocation = self.env["hr.leave.allocation"].browse(action["res_id"])

        self.assertEqual(allocation.employee_id, self.employee)
        self.assertEqual(allocation.holiday_status_id, self.leave_type)
        self.assertEqual(allocation.number_of_days, 21)
        self.assertEqual(
            allocation.hosny_contract_version_id, self.employee.version_id
        )
        self.assertEqual(allocation.state, "validate")
        self.assertEqual(self.employee.hosny_allocated_annual_leave_days, 21)

        self.employee.hosny_annual_leave_days = 25
        self.employee.action_hosny_sync_annual_leave()
        self.assertEqual(allocation.number_of_days, 25)

    def test_negative_payroll_values_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.employee.hosny_housing_allowance = -1

    def test_contract_template_copies_payroll_values(self):
        fields_to_copy = self.env["hr.version"]._get_whitelist_fields_from_template()
        self.assertIn("hosny_housing_allowance", fields_to_copy)
        self.assertIn("hosny_annual_leave_days", fields_to_copy)
        self.assertIn("struct_id", fields_to_copy)

        structure = self.env.ref(
            "hosny_hr_payroll_ar.hosny_payroll_structure_ar"
        )
        template = self.env["hr.version"].create(
            {
                "name": "قالب عقد اختبار الرواتب",
                "company_id": self.env.company.id,
                "employee_id": False,
                "date_version": date.today(),
                "wage": 7_500,
                "struct_id": structure.id,
                "hosny_housing_allowance": 1_500,
                "hosny_transport_allowance": 400,
                "hosny_annual_leave_type_id": self.leave_type.id,
                "hosny_annual_leave_days": 24,
                "resource_calendar_id": self.env.company.resource_calendar_id.id,
            }
        )
        employee = self.env["hr.employee"].create(
            {
                "name": "موظف اختبار قالب العقد",
                "company_id": self.env.company.id,
                "contract_template_id": template.id,
            }
        )
        self.assertEqual(employee.wage, 7_500)
        self.assertEqual(employee.struct_id, structure)
        self.assertEqual(employee.hosny_housing_allowance, 1_500)
        self.assertEqual(employee.hosny_transport_allowance, 400)
        self.assertEqual(employee.hosny_annual_leave_days, 24)

    def test_new_employee_contract_salary_and_work_entries(self):
        contract_start = date(2026, 7, 1)
        contract_end = date(2026, 7, 31)
        employee = self.env["hr.employee"].create(
            {
                "name": "موظف اختبار التكامل",
                "company_id": self.env.company.id,
                "date_version": contract_start,
                "contract_date_start": contract_start,
                "contract_date_end": contract_end,
                "resource_calendar_id": self.env.company.resource_calendar_id.id,
                "wage": 8_000,
                "hosny_housing_allowance": 1_500,
                "hosny_transport_allowance": 500,
            }
        )

        self.assertEqual(employee.contract_date_start, contract_start)
        self.assertEqual(employee.hosny_estimated_monthly_wage, 8_000)
        self.assertEqual(employee.hosny_total_allowances, 2_000)
        self.assertEqual(employee.hosny_total_fixed_compensation, 10_000)

        employee.wage = 9_000
        self.assertEqual(employee.hosny_estimated_monthly_wage, 9_000)
        self.assertEqual(employee.hosny_total_fixed_compensation, 11_000)

        work_entries = employee.generate_work_entries(
            contract_start, date(2026, 7, 7), force=True
        )
        self.assertTrue(work_entries)
        self.assertTrue(
            all(entry.version_id == employee.version_id for entry in work_entries)
        )

    def test_payslip_engine_availability_is_explicit(self):
        self.assertIn("hr.payslip", self.env.registry)
        self.assertIn("hr.payroll.structure", self.env.registry)
        self.assertIn("hr.salary.rule", self.env.registry)
        self.assertIn("hr.payslip.run", self.env.registry)

    def test_full_payroll_flow_and_no_duplicate_consumption(self):
        structure = self.env.ref(
            "hosny_hr_payroll_ar.hosny_payroll_structure_ar"
        )
        self.env.company.write(
            {
                "hosny_social_insurance_enabled": True,
                "hosny_social_insurance_employee_rate": 10,
                "hosny_social_insurance_employer_rate": 15,
                "hosny_social_insurance_minimum_base": 0,
                "hosny_social_insurance_maximum_base": 0,
            }
        )
        employee = self.env["hr.employee"].create(
            {
                "name": "موظف اختبار دورة الرواتب الكاملة",
                "company_id": self.env.company.id,
                "date_version": date(2026, 7, 1),
                "contract_date_start": date(2026, 7, 1),
                "resource_calendar_id": self.env.company.resource_calendar_id.id,
                "wage": 10_000,
                "struct_id": structure.id,
                "hosny_housing_allowance": 2_000,
                "hosny_transport_allowance": 500,
                "hosny_other_allowance": 250,
                "hosny_social_insurance_reference": 8_000,
                "hosny_annual_leave_type_id": self.leave_type.id,
                "hosny_annual_leave_days": 21,
            }
        )
        allocation_action = employee.action_hosny_sync_annual_leave()
        allocation = self.env["hr.leave.allocation"].browse(
            allocation_action["res_id"]
        )
        self.assertEqual(allocation.state, "validate")
        self.assertEqual(allocation.number_of_days, 21)

        addition = self.env["hosny.hr.salary.adjustment"].create(
            {
                "name": "مكافأة شهرية للاختبار",
                "employee_id": employee.id,
                "version_id": employee.version_id.id,
                "adjustment_type": "addition",
                "category": "bonus",
                "amount": 1_000,
                "recurrence": "monthly",
                "date_start": date(2026, 7, 1),
            }
        )
        deduction = self.env["hosny.hr.salary.adjustment"].create(
            {
                "name": "استقطاع لمرة واحدة للاختبار",
                "employee_id": employee.id,
                "version_id": employee.version_id.id,
                "adjustment_type": "deduction",
                "category": "penalty",
                "amount": 200,
                "recurrence": "once",
                "date_start": date(2026, 7, 15),
            }
        )
        (addition | deduction).action_approve()

        payslip = self.env["hr.payslip"].create(
            {
                "name": "قسيمة يوليو 2026 للاختبار",
                "employee_id": employee.id,
                "contract_id": employee.version_id.id,
                "struct_id": structure.id,
                "date_from": date(2026, 7, 1),
                "date_to": date(2026, 7, 31),
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        totals = {
            line.code: line.total
            for line in payslip.line_ids
        }
        self.assertEqual(totals["BASIC"], 10_000)
        self.assertEqual(totals["HOSNY_HOUSING"], 2_000)
        self.assertEqual(totals["HOSNY_TRANSPORT"], 500)
        self.assertEqual(totals["HOSNY_OTHER"], 250)
        self.assertEqual(totals["HOSNY_ADD"], 1_000)
        self.assertEqual(totals["GROSS"], 13_750)
        self.assertEqual(totals["HOSNY_DED"], -200)
        self.assertEqual(totals["HOSNY_INS_EMP"], -800)
        self.assertEqual(totals["NET"], 12_750)
        self.assertEqual(totals["HOSNY_INS_COMP"], 1_200)
        self.assertTrue(payslip.hosny_work_entry_ids)
        self.assertEqual(
            set(payslip.hosny_adjustment_ids.ids),
            {addition.id, deduction.id},
        )

        payslip.action_payslip_done()
        self.assertEqual(payslip.state, "done")
        self.assertTrue(
            all(
                work_entry.state == "validated"
                for work_entry in payslip.hosny_work_entry_ids
            )
        )

        duplicate = self.env["hr.payslip"].create(
            {
                "name": "قسيمة مكررة يوليو 2026",
                "employee_id": employee.id,
                "contract_id": employee.version_id.id,
                "struct_id": structure.id,
                "date_from": date(2026, 7, 1),
                "date_to": date(2026, 7, 31),
                "company_id": self.env.company.id,
            }
        )
        self.assertFalse(duplicate._hosny_get_period_adjustments())
        with self.assertRaises(UserError):
            duplicate.compute_sheet()

        future_version = employee.create_version(
            {
                "date_version": date(2026, 8, 1),
                "wage": 12_000,
            }
        )
        self.assertEqual(future_version.struct_id, structure)
        future_payslip = self.env["hr.payslip"].create(
            {
                "name": "قسيمة أغسطس 2026 للاختبار",
                "employee_id": employee.id,
                "contract_id": future_version.id,
                "struct_id": future_version.struct_id.id,
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 31),
                "company_id": self.env.company.id,
            }
        )
        future_payslip.compute_sheet()
        future_totals = {
            line.code: line.total
            for line in future_payslip.line_ids
        }
        self.assertEqual(future_totals["BASIC"], 12_000)
        self.assertEqual(future_totals["HOSNY_ADD"], 0)
        self.assertEqual(future_totals["HOSNY_DED"], 0)
        future_payslip.action_payslip_done()
        self.assertEqual(future_payslip.state, "done")

    def test_english_master_names_are_changed_to_arabic(self):
        structure_type = self.env["hr.payroll.structure.type"].create(
            {"name": "Employee"}
        )
        calendar = self.env["resource.calendar"].create(
            {
                "name": "Standard 40 hours/week",
                "company_id": self.env.company.id,
            }
        )

        self.env[
            "hr.payroll.structure.type"
        ]._hosny_apply_arabic_names()
        self.env["resource.calendar"]._hosny_apply_arabic_names()

        self.assertEqual(structure_type.name, "الموظف")
        self.assertEqual(calendar.name, "دوام قياسي 40 ساعة/أسبوع")
