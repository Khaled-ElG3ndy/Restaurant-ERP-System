from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPrepaidExpenses(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.purchase_journal = cls.env["account.journal"].create({
            "name": "Prepaid Test Purchases",
            "code": "PETP",
            "type": "purchase",
            "company_id": cls.company.id,
        })
        cls.expense_account = cls.env["account.account"].create({
            "name": "Prepaid Test Rent Expense",
            "code": "PE5100",
            "account_type": "expense",
            "company_ids": [Command.set(cls.company.ids)],
        })
        cls.prepaid_account = cls.env["account.account"].create({
            "name": "Prepaid Test Current Asset",
            "code": "PE1100",
            "account_type": "asset_current",
            "company_ids": [Command.set(cls.company.ids)],
        })
        cls.payable_account = cls.env["account.account"].create({
            "name": "Prepaid Test Payable",
            "code": "PE2100",
            "account_type": "liability_payable",
            "company_ids": [Command.set(cls.company.ids)],
        })
        cls.vendor = cls.env["res.partner"].create({"name": "Prepaid Expense Test Vendor"})
        cls.vendor.with_company(cls.company).property_account_payable_id = cls.payable_account
        plan = cls.env["account.analytic.plan"].search([], limit=1)
        cls.branch = cls.env["account.analytic.account"].create({
            "name": "Prepaid Test Branch",
            "plan_id": plan.id,
            "company_id": cls.company.id,
        })

    def _line_values(self, amount, start, end, method="monthly", count=1, name="Prepaid Test"):
        return {
            "name": name,
            "quantity": 1,
            "price_unit": amount,
            "account_id": self.expense_account.id,
            "analytic_distribution": {str(self.branch.id): 100.0},
            "is_prepaid_expense": True,
            "prepaid_start_date": start,
            "prepaid_end_date": end,
            "prepaid_actual_account_id": self.expense_account.id,
            "prepaid_account_id": self.prepaid_account.id,
            "prepaid_distribution_method": method,
            "prepaid_installment_count": count,
        }

    def _bill(self, lines):
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.vendor.id,
            "journal_id": self.purchase_journal.id,
            "invoice_date": date(2026, 7, 11),
            "invoice_date_due": date(2026, 7, 11),
            "date": date(2026, 7, 11),
            "analytic_account_id": self.branch.id,
            "invoice_line_ids": [Command.create(values) for values in lines],
        })
        bill.action_post()
        return bill

    def _service_values(self, source_type, source, amount, name="Wizard Prepaid Test"):
        values = {
            "source_type": source_type,
            "source": source,
            "amount": amount,
            "start_date": date(2027, 1, 1),
            "end_date": date(2027, 12, 31),
            "distribution_method": "monthly",
            "installment_count": 1,
            "actual_account": self.expense_account,
            "prepaid_account": self.prepaid_account,
            "analytic_account": self.branch,
            "analytic_distribution": {str(self.branch.id): 100.0},
            "name": name,
        }
        return values

    def test_monthly_bill_and_recognition(self):
        bill = self._bill([
            self._line_values(12000, date(2027, 1, 1), date(2027, 12, 31))
        ])
        expense_line = bill.invoice_line_ids.filtered("is_prepaid_expense")
        schedule = expense_line.prepaid_schedule_id
        self.assertEqual(expense_line.account_id, self.prepaid_account)
        self.assertEqual(len(schedule.line_ids), 12)
        self.assertEqual(schedule.line_ids.mapped("net_amount"), [1000.0] * 12)
        self.assertEqual(schedule.line_ids[0].due_date, date(2027, 1, 31))
        self.assertEqual(schedule.line_ids[-1].due_date, date(2027, 12, 31))
        schedule.line_ids[0].accrual_move_id.action_post()
        self.assertEqual(schedule.recognized_amount, 1000.0)
        self.assertEqual(schedule.remaining_amount, 11000.0)
        self.assertEqual(
            schedule.line_ids[0].accrual_move_id.line_ids.filtered(
                lambda line: line.account_id == self.expense_account
            ).debit,
            1000.0,
        )

    def test_daily_custom_rounding_and_mixed_lines(self):
        normal_values = {
            "name": "Ordinary Expense",
            "quantity": 1,
            "price_unit": 250,
            "account_id": self.expense_account.id,
        }
        bill = self._bill([
            self._line_values(3100, date(2027, 1, 15), date(2027, 2, 14), "daily"),
            self._line_values(100, date(2027, 3, 1), date(2027, 3, 31), "custom", 3),
            normal_values,
        ])
        daily, custom = bill.invoice_line_ids.filtered("is_prepaid_expense")
        normal = bill.invoice_line_ids.filtered(
            lambda line: line.display_type == "product" and not line.is_prepaid_expense
        )
        self.assertEqual(daily.prepaid_schedule_id.line_ids.mapped("net_amount"), [1700.0, 1400.0])
        self.assertEqual(custom.prepaid_schedule_id.line_ids.mapped("net_amount"), [33.33, 33.33, 33.34])
        self.assertEqual(normal.account_id, self.expense_account)

    def test_discount_allocation_closes_prepaid_balance(self):
        allocation_account = self.env["account.account"].create({
            "name": "Prepaid Test Discount Allocation",
            "code": "PE4200",
            "account_type": "income_other",
            "company_ids": [Command.set(self.company.ids)],
        })
        self.company.account_discount_income_allocation_id = allocation_account
        values = self._line_values(1000, date(2027, 1, 1), date(2027, 12, 31))
        values["discount"] = 10
        bill = self._bill([values])
        expense_line = bill.invoice_line_ids.filtered("is_prepaid_expense")
        schedule = expense_line.prepaid_schedule_id
        prepaid_balance = sum(
            bill.line_ids.filtered(lambda line: line.account_id == self.prepaid_account).mapped("balance")
        )
        self.assertEqual(schedule.original_amount, prepaid_balance)

    def test_cron_reset_and_duplicate_prevention(self):
        bill = self._bill([
            self._line_values(100, date(2026, 7, 11), date(2026, 7, 11), "custom", 1)
        ])
        installment = bill.prepaid_schedule_ids.line_ids
        self.env["prepaid.expense.schedule.line"]._cron_post_due_entries()
        self.assertEqual(installment.state, "posted")
        move_id = installment.accrual_move_id.id
        self.env["prepaid.expense.schedule.line"]._cron_post_due_entries()
        self.assertEqual(installment.accrual_move_id.id, move_id)
        with self.assertRaises(UserError):
            bill.button_draft()

        future_bill = self._bill([
            self._line_values(120, date(2027, 1, 1), date(2027, 12, 31))
        ])
        future_bill.button_draft()
        self.assertFalse(future_bill.prepaid_schedule_ids)

    def test_partial_credit_note_preserves_posted_entries(self):
        bill = self._bill([
            self._line_values(12000, date(2026, 1, 1), date(2026, 12, 31))
        ])
        schedule = bill.prepaid_schedule_ids
        schedule.line_ids[0].accrual_move_id.action_post()
        refund = bill._reverse_moves([{
            "date": date(2026, 7, 11),
            "invoice_date": date(2026, 7, 11),
        }], cancel=False)
        refund_line = refund.invoice_line_ids.filtered(lambda line: line.display_type == "product")
        refund_line.price_unit = 6000
        refund.action_post()
        self.assertEqual(schedule.refunded_amount, 6000.0)
        self.assertEqual(schedule.recognized_amount, 1000.0)
        self.assertEqual(schedule.remaining_amount, 5000.0)
        self.assertEqual(set(refund_line.prepaid_refund_allocation_ids.mapped("kind")), {"future"})

    def test_posted_bill_wizard_service_partial_and_duplicate_guard(self):
        bill = self._bill([{
            "name": "Posted ordinary expense",
            "quantity": 1,
            "price_unit": 1000,
            "account_id": self.expense_account.id,
            "analytic_distribution": {str(self.branch.id): 100.0},
        }])
        line = bill.invoice_line_ids.filtered(lambda item: item.display_type == "product")
        values = self._service_values("vendor_bill", bill, 400)
        values["source_line"] = line
        schedule = self.env["prepaid.expense.schedule"].create_from_source(values)
        self.assertEqual(schedule.original_amount, 400)
        self.assertEqual(len(schedule.line_ids), 12)
        self.assertAlmostEqual(sum(schedule.line_ids.mapped("amount")), 400, places=2)
        self.assertEqual(
            sum(schedule.reclassification_move_id.line_ids.filtered(
                lambda item: item.account_id == self.prepaid_account
            ).mapped("balance")),
            400,
        )
        with self.assertRaises(ValidationError):
            self.env["prepaid.expense.schedule"].create_from_source(values)

    def test_vendor_payment_partial_full_and_wizard_cancel(self):
        bank_journal = self.env["account.journal"].search([
            ("company_id", "=", self.company.id), ("type", "=", "bank")
        ], limit=1)
        method_line = bank_journal.outbound_payment_method_line_ids[:1]
        payment = self.env["account.payment"].create({
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.vendor.id,
            "amount": 12000,
            "currency_id": self.company.currency_id.id,
            "date": date(2026, 7, 11),
            "journal_id": bank_journal.id,
            "payment_method_line_id": method_line.id,
            "memo": "Vendor payment prepaid test",
        })
        payment.action_post()
        count_before = self.env["prepaid.expense.schedule"].search_count([
            ("vendor_payment_id", "=", payment.id)
        ])
        payment.action_create_prepaid_expense()
        self.assertEqual(
            self.env["prepaid.expense.schedule"].search_count([
                ("vendor_payment_id", "=", payment.id)
            ]),
            count_before,
        )
        first = self.env["prepaid.expense.schedule"].create_from_source(
            self._service_values("vendor_payment", payment, 5000)
        )
        self.assertEqual(first.original_amount, 5000)
        self.assertEqual(payment.prepaid_available_amount, 7000)
        with self.assertRaises(ValidationError):
            self.env["prepaid.expense.schedule"].create_from_source(
                self._service_values("vendor_payment", payment, 7000.01)
            )
        second = self.env["prepaid.expense.schedule"].create_from_source(
            self._service_values("vendor_payment", payment, 7000)
        )
        self.assertEqual(second.original_amount, 7000)
        self.assertEqual(payment.prepaid_used_amount, 12000)
        self.assertEqual(payment.prepaid_available_amount, 0)
        self.assertFalse(payment.can_create_prepaid_expense)
        with self.assertRaises(UserError):
            payment.action_draft()

    def test_draft_vendor_bill_and_receipt_use_same_wizard_service(self):
        for move_type in ("in_invoice", "in_receipt"):
            document = self.env["account.move"].create({
                "move_type": move_type,
                "partner_id": self.vendor.id,
                "journal_id": self.purchase_journal.id,
                "invoice_date": date(2026, 7, 11),
                "date": date(2026, 7, 11),
                "analytic_account_id": self.branch.id,
                "invoice_line_ids": [Command.create({
                    "name": "Draft purchase document prepaid",
                    "quantity": 1,
                    "price_unit": 1200,
                    "account_id": self.expense_account.id,
                    "analytic_distribution": {str(self.branch.id): 100.0},
                })],
            })
            line = document.invoice_line_ids.filtered(lambda item: item.display_type == "product")
            self.assertTrue(document.can_create_prepaid_expense)
            values = self._service_values("vendor_bill", document, 1200)
            values["source_line"] = line
            schedule = self.env["prepaid.expense.schedule"].create_from_source(values)
            self.assertFalse(schedule)
            self.assertTrue(line.is_prepaid_expense)
            self.assertEqual(line.account_id, self.prepaid_account)
            self.assertFalse(document.can_create_prepaid_expense)
            document.action_post()
            self.assertEqual(len(document.prepaid_schedule_ids), 1)
            self.assertEqual(len(document.prepaid_schedule_ids.line_ids), 12)
            self.assertEqual(document.prepaid_schedule_ids.original_amount, 1200)

    def test_posted_vendor_receipt_uses_bill_wizard_and_smart_button(self):
        receipt = self.env["account.move"].create({
            "move_type": "in_receipt",
            "partner_id": self.vendor.id,
            "journal_id": self.purchase_journal.id,
            "invoice_date": date(2026, 7, 11),
            "date": date(2026, 7, 11),
            "analytic_account_id": self.branch.id,
            "invoice_line_ids": [Command.create({
                "name": "Posted vendor receipt prepaid",
                "quantity": 1,
                "price_unit": 1200,
                "account_id": self.expense_account.id,
                "analytic_distribution": {str(self.branch.id): 100.0},
            })],
        })
        receipt.action_post()
        self.assertTrue(receipt.can_create_prepaid_expense)
        wizard_action = receipt.action_create_prepaid_expense()
        self.assertEqual(wizard_action["res_model"], "prepaid.expense.bill.wizard")
        self.assertEqual(wizard_action["name"], "إنشاء مصروف مقدم")

        line = receipt.invoice_line_ids.filtered(lambda item: item.display_type == "product")
        values = self._service_values("vendor_bill", receipt, 1200)
        values["source_line"] = line
        schedule = self.env["prepaid.expense.schedule"].create_from_source(values)

        self.assertEqual(schedule.move_id, receipt)
        self.assertEqual(receipt.prepaid_schedule_count, 1)
        self.assertEqual(receipt.action_open_prepaid_schedule()["domain"], [("id", "in", schedule.ids)])
        self.assertFalse(receipt.can_create_prepaid_expense)

    def test_daily_cron_posts_every_due_installment_and_updates_totals(self):
        today = fields.Date.context_today(self.env["prepaid.expense.schedule.line"])
        start = today + relativedelta(months=-2, day=1)
        end = today + relativedelta(months=2, day=31)
        values = self._line_values(500, start, end)
        values["prepaid_monthly_due_day"] = 1
        bill = self._bill([values])
        schedule = bill.prepaid_schedule_ids
        due_lines = schedule.line_ids.filtered(lambda line: line.due_date <= today)
        future_lines = schedule.line_ids - due_lines
        cron = self.env.ref("hosny_prepaid_expenses.ir_cron_post_due_prepaid_expenses")
        self.assertTrue(cron.active)
        self.assertEqual(cron.interval_number, 1)
        self.assertEqual(cron.interval_type, "days")
        self.env["prepaid.expense.schedule.line"]._cron_post_due_entries()
        self.assertTrue(all(line.state == "posted" for line in due_lines))
        self.assertTrue(all(line.state == "draft" for line in future_lines))
        self.assertEqual(schedule.posted_installment_count, len(due_lines))
        self.assertEqual(schedule.draft_installment_count, len(future_lines))
        self.assertEqual(schedule.recognized_amount, sum(due_lines.mapped("amount")))
        self.assertEqual(
            schedule.remaining_amount,
            schedule.original_amount - schedule.recognized_amount,
        )
