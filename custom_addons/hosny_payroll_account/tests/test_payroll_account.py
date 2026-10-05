from datetime import date

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHosnyPayrollAccount(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.structure = cls.env.ref("hosny_hr_payroll_ar.hosny_payroll_structure_ar")
        cls.company._hosny_setup_payroll_accounting()
        cls.journal = cls.company.hosny_payroll_journal_id

        # الحساب التحليلي إلزامي على قيود اليومية في هذا النظام
        # (hosny_account_analytic_header)، فنضبط افتراضيًا للشركة.
        if "analytic_account_id" in cls.env["account.move"]._fields:
            analytic = cls.env["account.analytic.account"].search([
                ("company_id", "in", [False, cls.company.id]),
            ], limit=1)
            if not analytic:
                plan = cls.env["account.analytic.plan"].search([], limit=1) or \
                    cls.env["account.analytic.plan"].create({"name": "Test plan"})
                analytic = cls.env["account.analytic.account"].create({
                    "name": "Hosny payroll test analytic",
                    "plan_id": plan.id,
                    "company_id": cls.company.id,
                })
            cls.company.hosny_payroll_analytic_account_id = analytic
            cls.analytic_account = analytic

        cls.calendar = cls.env["resource.calendar"].create({
            "name": "Hosny payroll account calendar",
            "company_id": cls.company.id,
            "tz": "UTC",
            "attendance_ids": [
                fields.Command.create({
                    "name": f"Day {day}",
                    "dayofweek": str(day),
                    "hour_from": 8.0,
                    "hour_to": 16.0,
                    "day_period": "morning",
                })
                for day in range(7)
            ],
        })

    def _create_employee(self, name="Hosny payroll account employee", **version_values):
        values = {
            "name": name,
            "company_id": self.company.id,
            "date_version": date(2026, 1, 1),
            "contract_date_start": date(2026, 1, 1),
            "resource_calendar_id": self.calendar.id,
            "wage": 2000.0,
            "struct_id": self.structure.id,
            "hosny_housing_allowance": 500.0,
        }
        values.update(version_values)
        return self.env["hr.employee"].create(values)

    def _create_payslip(self, employee, date_from=date(2026, 3, 1), date_to=date(2026, 3, 31)):
        payslip = self.env["hr.payslip"].create({
            "name": "Test slip %s" % employee.name,
            "employee_id": employee.id,
            "date_from": date_from,
            "date_to": date_to,
            "contract_id": employee.current_version_id.id,
            "struct_id": self.structure.id,
            "company_id": self.company.id,
        })
        payslip.compute_sheet()
        return payslip

    # ------------------------------------------------------------------

    def test_default_setup_creates_journal_and_maps_accounts(self):
        self.assertTrue(self.journal, "يجب إنشاء يومية للرواتب")
        self.assertEqual(self.journal.type, "general")

        net_rule = self.structure.rule_ids.filtered(lambda rule: rule.code == "NET")
        basic_rule = self.structure.rule_ids.filtered(lambda rule: rule.code == "BASIC")
        gross_rule = self.structure.rule_ids.filtered(lambda rule: rule.code == "GROSS")
        self.assertTrue(net_rule.account_credit, "قاعدة الصافي يجب أن يكون لها حساب دائن")
        self.assertTrue(basic_rule.account_debit, "قاعدة الأساسي يجب أن يكون لها حساب مدين")
        self.assertFalse(
            gross_rule.account_debit or gross_rule.account_credit,
            "قاعدة الإجمالي مجموع وسيط ولا يجب ترحيلها",
        )

    def test_confirm_creates_balanced_posted_move(self):
        employee = self._create_employee()
        payslip = self._create_payslip(employee)
        payslip.action_payslip_done()

        move = payslip.move_id
        self.assertTrue(move, "يجب إنشاء قيد محاسبي عند الاعتماد")
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.journal_id, self.journal)
        self.assertEqual(move.date, payslip.date_to)

        total_debit = sum(move.line_ids.mapped("debit"))
        total_credit = sum(move.line_ids.mapped("credit"))
        self.assertAlmostEqual(total_debit, total_credit, places=2)

        net = payslip.line_ids.filtered(lambda line: line.code == "NET").total
        net_account = self.structure.rule_ids.filtered(
            lambda rule: rule.code == "NET"
        ).account_credit
        net_lines = move.line_ids.filtered(lambda line: line.account_id == net_account)
        self.assertAlmostEqual(sum(net_lines.mapped("credit")), net, places=2)

    def test_gross_is_not_posted_twice(self):
        employee = self._create_employee()
        payslip = self._create_payslip(employee)
        payslip.action_payslip_done()

        total_debit = sum(payslip.move_id.line_ids.mapped("debit"))
        gross = payslip.line_ids.filtered(lambda line: line.code == "GROSS").total
        # المدين يساوي إجمالي الراتب مرة واحدة فقط، لا مرتين.
        self.assertAlmostEqual(total_debit, gross, places=2)

    def test_confirm_twice_does_not_duplicate_move(self):
        employee = self._create_employee()
        payslip = self._create_payslip(employee)
        payslip.action_payslip_done()
        move = payslip.move_id

        payslip.action_payslip_done()
        self.assertEqual(payslip.move_id, move, "إعادة الاعتماد يجب ألا تُنشئ قيدًا جديدًا")
        self.assertEqual(
            self.env["account.move"].search_count([("ref", "=", payslip.number)]),
            1,
            "يجب ألا يوجد أكثر من قيد واحد للقسيمة",
        )

    def test_cancel_creates_reversal(self):
        employee = self._create_employee()
        payslip = self._create_payslip(employee)
        payslip.action_payslip_done()
        move = payslip.move_id

        payslip.action_payslip_cancel()

        self.assertEqual(payslip.state, "cancel")
        self.assertTrue(payslip.hosny_reversal_move_id, "يجب إنشاء قيد عكسي")
        reversal = payslip.hosny_reversal_move_id
        self.assertEqual(reversal.state, "posted")
        self.assertEqual(reversal.reversed_entry_id, move)
        self.assertEqual(move.state, "posted", "القيد الأصلي يبقى للمراجعة")

        # الأصلي وعكسه يصفّران بعضهما.
        self.assertAlmostEqual(
            sum(move.line_ids.mapped("debit")) - sum(reversal.line_ids.mapped("debit")),
            0.0,
            places=2,
        )

    def test_reset_to_draft_blocked_while_move_posted(self):
        employee = self._create_employee()
        payslip = self._create_payslip(employee)
        payslip.action_payslip_done()
        payslip.state = "cancel"  # محاكاة حالة ملغاة بدون عكس القيد

        with self.assertRaises(UserError):
            payslip.action_payslip_draft()

    def test_reconfirm_after_cancel_creates_new_move(self):
        employee = self._create_employee()
        payslip = self._create_payslip(employee)
        payslip.action_payslip_done()
        first_move = payslip.move_id

        payslip.action_payslip_cancel()
        payslip.action_payslip_draft()
        self.assertFalse(payslip.move_id, "فك الارتباط بعد العكس يسمح بقيد جديد")

        payslip.action_payslip_done()
        self.assertTrue(payslip.move_id)
        self.assertNotEqual(payslip.move_id, first_move)
        self.assertEqual(payslip.move_id.state, "posted")

    def test_department_account_overrides_expense_only(self):
        expense_account = self.env["account.account"].search([
            ("account_type", "=", "expense"),
            ("company_ids", "in", self.company.id),
        ], limit=1)
        department = self.env["hr.department"].create({
            "name": "Hosny payroll account department",
            "company_id": self.company.id,
            "hosny_payroll_expense_account_id": expense_account.id,
        })
        employee = self._create_employee(department_id=department.id)
        payslip = self._create_payslip(employee)
        payslip.action_payslip_done()

        move = payslip.move_id
        debit_lines = move.line_ids.filtered(lambda line: line.debit > 0)
        self.assertTrue(debit_lines)
        self.assertEqual(
            set(debit_lines.mapped("account_id")),
            {expense_account},
            "مصروفات القسم يجب أن تُرحَّل إلى حساب القسم",
        )
        # الطرف الدائن (المستحق للموظفين) لا يتأثر بحساب القسم.
        credit_lines = move.line_ids.filtered(lambda line: line.credit > 0)
        self.assertNotIn(expense_account, credit_lines.mapped("account_id"))

    def test_unmapped_rule_raises_clear_error(self):
        employee = self._create_employee()
        payslip = self._create_payslip(employee)
        basic_rule = self.structure.rule_ids.filtered(lambda rule: rule.code == "BASIC")
        basic_rule.account_debit = False

        with self.assertRaises(UserError):
            payslip.action_payslip_done()

    def test_unpaid_leave_reduces_salary_and_entry(self):
        unpaid_type = self.env["hr.leave.type"].create({
            "name": "Hosny account unpaid leave",
            "company_id": self.company.id,
            "requires_allocation": False,
            "request_unit": "day",
            "unpaid": True,
            "leave_validation_type": "hr",
            "work_entry_type_id": self.env.ref(
                "hr_work_entry.work_entry_type_unpaid_leave"
            ).id,
        })
        employee = self._create_employee("Hosny leave employee")

        reference = self._create_payslip(employee)
        full_net = reference.line_ids.filtered(lambda line: line.code == "NET").total
        reference.unlink()

        leave = self.env["hr.leave"].create({
            "name": "Unpaid week",
            "employee_id": employee.id,
            "holiday_status_id": unpaid_type.id,
            "request_date_from": date(2026, 3, 9),
            "request_date_to": date(2026, 3, 13),
        })
        leave.action_approve()

        payslip = self._create_payslip(employee)
        reduced_net = payslip.line_ids.filtered(lambda line: line.code == "NET").total
        self.assertLess(reduced_net, full_net, "الإجازة غير المدفوعة يجب أن تُخفّض الصافي")

        payslip.action_payslip_done()
        move = payslip.move_id
        net_account = self.structure.rule_ids.filtered(
            lambda rule: rule.code == "NET"
        ).account_credit
        net_lines = move.line_ids.filtered(lambda line: line.account_id == net_account)
        self.assertAlmostEqual(sum(net_lines.mapped("credit")), reduced_net, places=2)
        self.assertAlmostEqual(
            sum(move.line_ids.mapped("debit")),
            sum(move.line_ids.mapped("credit")),
            places=2,
        )
