import uuid

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    quick_create_token = fields.Char(
        copy=False,
        readonly=True,
        index=True,
    )
    counterpart_account_id = fields.Many2one(
        "account.account",
        string="Account",
        compute="_compute_counterpart_account_id",
        check_company=True,
    )

    @api.depends("move_id.line_ids.account_id", "journal_id.default_account_id", "journal_id.suspense_account_id")
    def _compute_counterpart_account_id(self):
        for line in self:
            _liquidity_lines, _suspense_lines, other_lines = line._seek_for_lines()
            line.counterpart_account_id = other_lines.account_id[:1]

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                account_bank_statement_line_quick_create_token_unique
            ON account_bank_statement_line (quick_create_token)
            WHERE quick_create_token IS NOT NULL
            """
        )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if "quick_create_token" in fields_list:
            defaults["quick_create_token"] = str(uuid.uuid4())
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("quick_create_token", str(uuid.uuid4()))
            journal = self.env["account.journal"].browse(vals.get("journal_id")).exists()
            if journal and "analytic_account_id" in self._fields:
                if not vals.get("analytic_account_id") and journal.analytic_account_id:
                    vals["analytic_account_id"] = journal.analytic_account_id.id
                elif not vals.get("analytic_account_id"):
                    raise ValidationError(
                        _("Please configure the branch on this journal before creating a transaction.")
                    )
        return super().create(vals_list)

    @api.model
    def quick_create_transaction(self, values):
        journal = self.env["account.journal"].browse(values.get("journal_id")).exists()
        if not journal:
            raise ValidationError(_("The bank or cash journal is required."))
        journal.check_access("read")
        self.check_access("create")
        if journal.type not in ("bank", "cash"):
            raise ValidationError(_("Bank transactions can only use a bank or cash journal."))
        if journal.company_id not in self.env.companies:
            raise AccessError(_("You cannot create a transaction for a journal in another company."))

        account = self._quick_validate_account(journal, values.get("account_id"))
        date = values.get("date") or fields.Date.context_today(self)
        create_values = {
            "journal_id": journal.id,
            "company_id": journal.company_id.id,
            "analytic_account_id": journal.analytic_account_id.id,
            "date": date,
            "payment_ref": (values.get("label") or "").strip(),
            "partner_id": values.get("partner_id") or False,
            "amount": values.get("amount"),
            "quick_create_token": values.get("token") or str(uuid.uuid4()),
        }
        if account:
            create_values["counterpart_account_id"] = account.id
        statement = self._get_default_statement(journal_id=journal.id, date=date)
        if statement and statement.journal_id == journal and not statement.is_complete:
            create_values["statement_id"] = statement.id
        line = self.with_context(quick_statement_line_create=True).create(create_values)
        return line.id

    @api.model
    def _quick_validate_account(self, journal, account_id):
        if not account_id:
            return self.env["account.account"]
        account = self.env["account.account"].browse(account_id).exists()
        if not account:
            raise ValidationError(_("The selected account does not exist."))
        account.check_access("read")
        available_account = self.env["account.account"].search_count([
            ("id", "=", account.id),
            ("company_ids", "parent_of", journal.company_id.id),
        ], limit=1)
        if not available_account:
            raise ValidationError(_("The selected account is not available for the journal company."))
        if account in (journal.default_account_id | journal.suspense_account_id):
            raise ValidationError(_("Select a counterpart account different from the liquidity and suspense accounts."))
        return account

    def quick_set_partner(self, partner_id=False):
        self.check_access("write")
        partner = self.env["res.partner"].browse(partner_id).exists() if partner_id else False
        if partner:
            partner.check_access("read")
            invalid = self.filtered(
                lambda line: partner.company_id and partner.company_id != line.company_id
            )
            if invalid:
                raise ValidationError(_("The selected partner is not available for the transaction company."))
        self.write({"partner_id": partner.id if partner else False})
        return True

    def quick_set_account(self, account_id):
        self.check_access("write")
        for line in self:
            account = self._quick_validate_account(line.journal_id, account_id)
            if not account:
                raise ValidationError(_("The account is required."))
            line.line_ids.remove_move_reconcile()
            line.payment_ids.unlink()
            move_line_values = line._prepare_move_line_default_vals(account.id)
            line.with_context(force_delete=True, skip_readonly_check=True).write({
                "checked": True,
                "line_ids": [Command.clear()] + [
                    Command.create(move_line_value) for move_line_value in move_line_values
                ],
            })
        return True

    def _quick_workspace_values(self):
        self.ensure_one()
        liquidity_lines, suspense_lines, other_lines = self._seek_for_lines()
        counterpart_accounts = other_lines.account_id
        counterpart_account = counterpart_accounts[:1]
        is_balanced = self.company_id.currency_id.is_zero(sum(self.move_id.line_ids.mapped("balance")))
        matched_lines = other_lines.filtered(
            lambda item: item.matched_debit_ids or item.matched_credit_ids
        )
        if self.move_id.state != "posted" or not is_balanced:
            processing_state = "error"
        elif suspense_lines:
            processing_state = "pending"
        elif self.is_reconciled and matched_lines:
            processing_state = "reconciled"
        elif self.is_reconciled:
            processing_state = "processed"
        else:
            processing_state = "assigned_pending"
        return {
            "id": self.id,
            "date": fields.Date.to_string(self.date),
            "label": self.payment_ref or "",
            "partner_id": self.partner_id.id or False,
            "partner_name": self.partner_id.display_name or "",
            "account_id": counterpart_account.id or False,
            "account_name": counterpart_account.display_name or "",
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "currency_name": self.currency_id.name,
            "is_reconciled": self.is_reconciled,
            "amount_residual": self.amount_residual,
            "processing_state": processing_state,
            "move_id": self.move_id.id,
            "move_name": self.move_id.name,
            "statement_id": self.statement_id.id or False,
            "journal_items": [{
                "id": item.id,
                "account": item.account_id.display_name,
                "partner": item.partner_id.display_name or "",
                "debit": item.debit,
                "credit": item.credit,
                "reconciled": item.reconciled,
            } for item in self.move_id.line_ids.sorted("id")],
        }

    @api.constrains("journal_id", "company_id", "amount", "payment_ref")
    def _check_quick_transaction_requirements(self):
        for line in self:
            if line.journal_id.type not in ("bank", "cash"):
                raise ValidationError(
                    _("Bank transactions can only use a bank or cash journal.")
                )
            if line.company_id != line.journal_id.company_id:
                raise ValidationError(
                    _("The transaction and its journal must belong to the same company.")
                )
            if line.currency_id.is_zero(line.amount):
                raise ValidationError(_("The transaction amount must not be zero."))
            if not (line.payment_ref or "").strip():
                raise ValidationError(_("The transaction label is required."))
