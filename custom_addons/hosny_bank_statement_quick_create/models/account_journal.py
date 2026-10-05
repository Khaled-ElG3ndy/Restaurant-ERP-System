from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Branch",
        check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
    )

    def action_quick_create_statement_line(self):
        """Open the standard bank statement line workspace for this dashboard card."""
        self.ensure_one()
        self.check_access("read")
        self.env["account.bank.statement.line"].check_access("create")

        if self.type not in ("bank", "cash"):
            raise UserError(_("Bank transactions can only be created for bank or cash journals."))
        if self.company_id not in self.env.companies:
            raise AccessError(_("You cannot create a transaction for a journal in another company."))
        if not self.analytic_account_id:
            raise UserError(_("Please configure the branch on this journal before creating a transaction."))

        return {
            "type": "ir.actions.client",
            "name": _("New Bank Transaction"),
            "tag": "hosny_bank_statement_quick_create.workspace",
            "target": "current",
            "params": {"journal_id": self.id, "open_entry": True},
            "context": {
                **self.env.context,
                "default_journal_id": self.id,
                "default_company_id": self.company_id.id,
                "default_date": fields.Date.context_today(self),
                "default_analytic_account_id": self.analytic_account_id.id,
                "quick_statement_line_create": True,
            },
        }

    def get_quick_statement_workspace_data(self, limit=200):
        self.ensure_one()
        self.check_access("read")
        lines = self.env["account.bank.statement.line"].search(
            [("journal_id", "=", self.id)], limit=limit
        )
        latest_line = lines[:1]
        currency = self.currency_id or self.company_id.currency_id
        return {
            "journal": {
                "id": self.id,
                "name": self.display_name,
                "company_id": self.company_id.id,
                "company_name": self.company_id.display_name,
                "branch_id": self.analytic_account_id.id,
                "branch_name": self.analytic_account_id.display_name,
                "currency_id": currency.id,
                "currency_name": currency.name,
                "default_account_id": self.default_account_id.id,
                "suspense_account_id": self.suspense_account_id.id,
            },
            "current_balance": latest_line.running_balance if latest_line else 0.0,
            "today": fields.Date.to_string(fields.Date.context_today(self)),
            "lines": [line._quick_workspace_values() for line in lines],
        }
