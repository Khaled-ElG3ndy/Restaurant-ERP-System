from datetime import date

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHosnyPayrollComputeFeedback(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.structure = cls.env.ref(
            "hosny_hr_payroll_ar.hosny_payroll_structure_ar",
            raise_if_not_found=False,
        )
        cls.calendar = cls.env["resource.calendar"].create({
            "name": "Compute feedback calendar",
            "company_id": cls.env.company.id,
            "tz": "UTC",
            "attendance_ids": [
                fields.Command.create({
                    "name": f"D{day}", "dayofweek": str(day),
                    "hour_from": 8.0, "hour_to": 16.0, "day_period": "morning",
                }) for day in range(7)
            ],
        })

    def _payslip(self):
        employee = self.env["hr.employee"].create({
            "name": "Compute feedback employee",
            "company_id": self.env.company.id,
            "date_version": date(2026, 1, 1),
            "contract_date_start": date(2026, 1, 1),
            "resource_calendar_id": self.calendar.id,
            "wage": 3000.0,
            "struct_id": self.structure.id,
        })
        return self.env["hr.payslip"].create({
            "name": "Compute feedback slip",
            "employee_id": employee.id,
            "contract_id": employee.current_version_id.id,
            "struct_id": self.structure.id,
            "date_from": date(2026, 3, 1),
            "date_to": date(2026, 3, 31),
            "company_id": self.env.company.id,
        })

    def test_indicators_start_empty(self):
        slip = self._payslip()
        self.assertFalse(slip.hosny_is_computed)
        self.assertEqual(slip.hosny_line_count, 0)
        self.assertEqual(slip.hosny_net_amount, 0.0)

    def test_button_returns_no_action_so_form_reloads(self):
        """إرجاع قيمة عادية يجعل عميل الويب يُعيد تحميل السجل تلقائيًا.

        لو أُرجع action (إشعار مثلًا) لأصبحت إعادة التحميل مرهونة بتسلسل
        ``next`` وقد لا تحدث، فتبقى القيم قديمة على الشاشة.
        """
        slip = self._payslip()
        result = slip.action_hosny_compute_sheet()
        self.assertNotIsInstance(
            result, dict,
            "يجب ألا يُرجع الزر action حتى يضمن عميل الويب إعادة التحميل",
        )

    def test_name_and_work_location_are_separated_in_title(self):
        view = self.env.ref("bi_hr_payroll.view_hr_payslip_form")
        arch = self.env["hr.payslip"].get_view(view.id, "form")["arch"]
        self.assertIn(
            "work_location_id", arch,
            "موقع العمل يجب أن يظل معروضًا في العنوان",
        )
        # الفاصل يُدرَج قبل حقل موقع العمل مباشرةً
        location_at = arch.index('name="work_location_id"')
        separator_at = arch.rindex("mx-2", 0, location_at)
        self.assertGreater(
            separator_at, arch.index('name="employee_id"'),
            "الفاصل يجب أن يقع بين اسم الموظف وموقع العمل",
        )

    def test_indicators_update_after_compute(self):
        slip = self._payslip()
        slip.action_hosny_compute_sheet()
        self.assertTrue(slip.hosny_is_computed)
        self.assertGreater(slip.hosny_line_count, 0)
        net = sum(slip.line_ids.filtered(lambda l: l.code == "NET").mapped("total"))
        self.assertAlmostEqual(slip.hosny_net_amount, net, places=2)

    def test_recompute_does_not_duplicate_lines(self):
        slip = self._payslip()
        slip.action_hosny_compute_sheet()
        count = slip.hosny_line_count
        slip.action_hosny_compute_sheet()
        self.assertEqual(slip.hosny_line_count, count)

    def test_compute_sheet_return_value_unchanged(self):
        """النداء البرمجي يجب أن يبقى كما هو حتى لا ينكسر الاعتماد والمعالج."""
        slip = self._payslip()
        self.assertIs(slip.compute_sheet(), True)
