from odoo import Command, fields
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestBankStatementQuickCreate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.bank_journal = cls.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "bank")], limit=1
        )
        cls.cash_journal = cls.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "cash")], limit=1
        )
        cls.sale_journal = cls.env["account.journal"].search(
            [("company_id", "=", company.id), ("type", "=", "sale")], limit=1
        )

    def _create_line(self, journal, amount, label):
        return self.env["account.bank.statement.line"].with_context(
            quick_statement_line_create=True
        ).create(
            {
                "journal_id": journal.id,
                "company_id": journal.company_id.id,
                "date": fields.Date.context_today(self.env.user),
                "payment_ref": label,
                "amount": amount,
            }
        )

    def test_dashboard_action_locks_clicked_journal(self):
        action = self.bank_journal.action_quick_create_statement_line()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "hosny_bank_statement_quick_create.workspace")
        self.assertEqual(action["target"], "current")
        self.assertEqual(action["params"]["journal_id"], self.bank_journal.id)

    def test_statement_list_button_uses_action_journal(self):
        action = self.env["account.bank.statement"].with_context(
            default_journal_id=self.bank_journal.id
        ).action_quick_create_statement_line()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["params"]["journal_id"], self.bank_journal.id)
        self.assertEqual(action["target"], "current")

    def test_statement_list_button_requires_journal_context(self):
        with self.assertRaises(UserError):
            self.env["account.bank.statement"].action_quick_create_statement_line()

    def test_positive_negative_and_cash_transactions(self):
        incoming = self._create_line(self.bank_journal, 1000, "Cash deposit")
        outgoing = self._create_line(self.bank_journal, -250, "Bank expense")
        cash = self._create_line(self.cash_journal, 50, "Cash movement")
        self.assertEqual(incoming.state, "posted")
        self.assertEqual(outgoing.state, "posted")
        self.assertEqual(cash.journal_id, self.cash_journal)
        self.assertEqual(incoming.analytic_account_id, self.bank_journal.analytic_account_id)
        self.assertFalse(incoming.is_reconciled)
        self.assertFalse(outgoing.is_reconciled)
        self.assertIn(incoming, self.env["account.bank.statement.line"].search([
            ("journal_id", "=", self.bank_journal.id)
        ]))

    def test_quick_account_and_partner_use_real_balanced_move_lines(self):
        account = self.env["account.account"].search([
            ("company_ids", "parent_of", self.env.company.id),
            ("account_type", "in", ("expense", "income", "asset_current")),
            ("id", "not in", (
                self.bank_journal.default_account_id.id,
                self.bank_journal.suspense_account_id.id,
            )),
        ], limit=1)
        partner = self.env.company.partner_id
        line_id = self.env["account.bank.statement.line"].quick_create_transaction({
            "journal_id": self.bank_journal.id,
            "date": fields.Date.context_today(self.env.user),
            "label": "Accounted deposit",
            "partner_id": partner.id,
            "account_id": account.id,
            "amount": 1000,
            "token": "accounted-deposit-token",
        })
        line = self.env["account.bank.statement.line"].browse(line_id)
        liquidity, suspense, other = line._seek_for_lines()
        self.assertFalse(suspense)
        self.assertEqual(other.account_id, account)
        self.assertEqual(line.partner_id, partner)
        self.assertTrue(all(item.partner_id == partner for item in line.move_id.line_ids))
        self.assertEqual(sum(line.move_id.line_ids.mapped("balance")), 0)
        self.assertEqual(liquidity.debit, 1000)
        self.assertEqual(other.credit, 1000)
        self.assertTrue(line.is_reconciled)

        outgoing_id = self.env["account.bank.statement.line"].quick_create_transaction({
            "journal_id": self.bank_journal.id,
            "date": fields.Date.context_today(self.env.user),
            "label": "Accounted expense",
            "account_id": account.id,
            "amount": -250,
            "token": "accounted-expense-token",
        })
        outgoing = self.env["account.bank.statement.line"].browse(outgoing_id)
        liquidity, _suspense, other = outgoing._seek_for_lines()
        self.assertEqual(liquidity.credit, 250)
        self.assertEqual(other.debit, 250)
        self.assertEqual(sum(outgoing.move_id.line_ids.mapped("balance")), 0)

    def test_missing_account_is_pending_then_real_move_is_updated(self):
        line = self._create_line(self.bank_journal, 75, "Pending account")
        values = line._quick_workspace_values()
        self.assertFalse(values["account_id"])
        self.assertFalse(values["is_reconciled"])
        self.assertEqual(values["processing_state"], "pending")

        account = self.env["account.account"].search([
            ("company_ids", "parent_of", self.env.company.id),
            ("account_type", "in", ("expense", "income", "asset_current")),
            ("id", "not in", (
                self.bank_journal.default_account_id.id,
                self.bank_journal.suspense_account_id.id,
            )),
        ], limit=1)
        line.quick_set_account(account.id)
        _liquidity, suspense, other = line._seek_for_lines()
        self.assertFalse(suspense)
        self.assertEqual(other.account_id, account)
        self.assertEqual(sum(line.move_id.line_ids.mapped("balance")), 0)
        self.assertTrue(line.is_reconciled)

    def test_rejects_zero_non_bank_and_missing_label(self):
        with self.assertRaises(ValidationError):
            self._create_line(self.bank_journal, 0, "Zero")
        with self.assertRaises(ValidationError):
            self._create_line(self.sale_journal, 10, "Wrong journal")
        with self.assertRaises(ValidationError):
            self._create_line(self.bank_journal, 10, "")

    def test_lock_date_is_respected(self):
        today = fields.Date.context_today(self.env.user)
        self.env.cr.execute(
            "UPDATE res_company SET hard_lock_date = %s WHERE id = %s",
            (today, self.env.company.id),
        )
        self.env["res.company"].invalidate_model(["hard_lock_date", "user_hard_lock_date"])
        line = self._create_line(self.bank_journal, 10, "Locked transaction")
        self.assertGreater(line.date, today)

    def test_duplicate_form_token_is_rejected(self):
        token = "same-form-submit-token"
        values = {
            "journal_id": self.bank_journal.id,
            "company_id": self.bank_journal.company_id.id,
            "date": fields.Date.context_today(self.env.user),
            "payment_ref": "First submit",
            "amount": 10,
            "quick_create_token": token,
        }
        self.env["account.bank.statement.line"].create(values)
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["account.bank.statement.line"].create({**values, "payment_ref": "Second submit"})

    def test_readonly_user_cannot_open_quick_create(self):
        readonly_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Quick Create Readonly Test",
            "login": "quick-create-readonly-test",
            "company_id": self.env.company.id,
            "company_ids": [Command.set(self.env.company.ids)],
            "group_ids": [Command.set([self.env.ref("account.group_account_readonly").id])],
        })
        with self.assertRaises(AccessError):
            self.bank_journal.with_user(readonly_user).action_quick_create_statement_line()

    def test_other_company_journal_is_blocked(self):
        other_company = self.env["res.company"].create({"name": "Quick Create Other Company"})
        other_journal = self.env["account.journal"].create({
            "name": "Other Company Bank",
            "code": "QCBK",
            "type": "bank",
            "company_id": other_company.id,
        })
        accounting_user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Quick Create Company Test",
            "login": "quick-create-company-test",
            "company_id": self.env.company.id,
            "company_ids": [Command.set(self.env.company.ids)],
            "group_ids": [Command.set([self.env.ref("account.group_account_user").id])],
        })
        with self.assertRaises(AccessError):
            other_journal.with_user(accounting_user).action_quick_create_statement_line()
