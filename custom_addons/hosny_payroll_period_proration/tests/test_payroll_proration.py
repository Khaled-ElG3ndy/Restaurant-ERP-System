from calendar import monthrange
from datetime import date

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHosnyPayrollPeriodProration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.structure = cls.env.ref(
            "hosny_hr_payroll_ar.hosny_payroll_structure_ar"
        )
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Hosny payroll proration daily calendar",
                "company_id": cls.env.company.id,
                "tz": "UTC",
                "attendance_ids": [
                    fields.Command.create(
                        {
                            "name": f"Day {day}",
                            "dayofweek": str(day),
                            "hour_from": 8.0,
                            "hour_to": 16.0,
                            "day_period": "morning",
                        }
                    )
                    for day in range(7)
                ],
            }
        )
        cls.unpaid_leave_type = cls.env["hr.leave.type"].create(
            {
                "name": "Hosny proration unpaid leave",
                "company_id": cls.env.company.id,
                "requires_allocation": False,
                "request_unit": "day",
                "unpaid": True,
                "leave_validation_type": "hr",
                "work_entry_type_id": cls.env.ref(
                    "hr_work_entry.work_entry_type_unpaid_leave"
                ).id,
            }
        )

    def _create_employee(self, name, contract_start, contract_end=False):
        return self.env["hr.employee"].create(
            {
                "name": name,
                "company_id": self.env.company.id,
                "date_version": contract_start,
                "contract_date_start": contract_start,
                "contract_date_end": contract_end,
                "resource_calendar_id": self.calendar.id,
                "wage": 31_000,
                "struct_id": self.structure.id,
                "hosny_housing_allowance": 6_200,
                "hosny_transport_allowance": 3_100,
                "hosny_other_allowance": 1_550,
            }
        )

    def _compute_payslip(self, employee, date_from, date_to):
        payslip = self.env["hr.payslip"].create(
            {
                "name": f"Proration {employee.name} {date_from} {date_to}",
                "employee_id": employee.id,
                "contract_id": employee.version_id.id,
                "struct_id": self.structure.id,
                "date_from": date_from,
                "date_to": date_to,
                "company_id": self.env.company.id,
            }
        )
        payslip.compute_sheet()
        totals = {line.code: line.total for line in payslip.line_ids}
        return payslip, totals

    def _assert_fixed_components(self, totals, factor):
        expected = {
            "BASIC": 31_000,
            "HOSNY_HOUSING": 6_200,
            "HOSNY_TRANSPORT": 3_100,
            "HOSNY_OTHER": 1_550,
        }
        for code, monthly_amount in expected.items():
            self.assertAlmostEqual(
                totals[code], monthly_amount * factor, places=2, msg=code
            )

    def test_full_half_and_twenty_day_periods(self):
        periods = [
            ("full", date(2026, 8, 1), date(2026, 8, 31), 31 / 31),
            ("half", date(2026, 8, 1), date(2026, 8, 15), 15 / 31),
            ("twenty", date(2026, 8, 1), date(2026, 8, 20), 20 / 31),
        ]
        for label, date_from, date_to, factor in periods:
            employee = self._create_employee(
                f"Proration period {label}", date(2026, 8, 1)
            )
            _payslip, totals = self._compute_payslip(
                employee, date_from, date_to
            )
            self._assert_fixed_components(totals, factor)

    def test_calendar_month_lengths_28_29_30_and_31(self):
        months = [(2025, 2), (2024, 2), (2026, 4), (2026, 8)]
        for year, month in months:
            days = monthrange(year, month)[1]
            employee = self._create_employee(
                f"Proration month {year}-{month}", date(year, month, 1)
            )
            _payslip, totals = self._compute_payslip(
                employee, date(year, month, 1), date(year, month, days // 2)
            )
            self._assert_fixed_components(totals, (days // 2) / days)

    def test_contract_start_and_end_inside_month(self):
        starter = self._create_employee(
            "Proration mid-month starter", date(2026, 8, 16)
        )
        _payslip, totals = self._compute_payslip(
            starter, date(2026, 8, 1), date(2026, 8, 31)
        )
        self._assert_fixed_components(totals, 16 / 31)

        leaver = self._create_employee(
            "Proration mid-month leaver", date(2026, 8, 1), date(2026, 8, 20)
        )
        _payslip, totals = self._compute_payslip(
            leaver, date(2026, 8, 1), date(2026, 8, 31)
        )
        self._assert_fixed_components(totals, 20 / 31)

    def test_unpaid_leave_is_deducted_once(self):
        employee = self._create_employee(
            "Proration unpaid leave", date(2026, 8, 1)
        )
        leave = self.env["hr.leave"].create(
            {
                "name": "Three unpaid days",
                "employee_id": employee.id,
                "holiday_status_id": self.unpaid_leave_type.id,
                "request_date_from": date(2026, 8, 10),
                "request_date_to": date(2026, 8, 12),
            }
        )
        leave.action_approve()

        payslip, totals = self._compute_payslip(
            employee, date(2026, 8, 1), date(2026, 8, 31)
        )
        unpaid_hours = sum(
            payslip.hosny_work_entry_ids.filtered(
                lambda entry: entry.leave_id == leave
            ).mapped("duration")
        )
        self.assertEqual(unpaid_hours, 24.0)
        self._assert_fixed_components(totals, 28 / 31)

    def test_calls_without_a_payslip_keep_monthly_values(self):
        employee = self._create_employee(
            "Proration direct component call", date(2026, 8, 1)
        )
        version = employee.version_id
        self.assertEqual(version._hosny_get_salary_rule_amount("base"), 31_000)
        self.assertEqual(
            version._hosny_get_salary_rule_amount("housing"), 6_200
        )

