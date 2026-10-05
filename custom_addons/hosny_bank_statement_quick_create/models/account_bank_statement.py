from odoo import _, models
from odoo.exceptions import UserError


class AccountBankStatement(models.Model):
    _inherit = "account.bank.statement"

    def action_quick_create_statement_line(self):
        """Create a transaction for the journal whose statements are displayed."""
        journal_id = self.env.context.get("default_journal_id")
        journal = self.env["account.journal"].browse(journal_id).exists()
        if not journal and self:
            journals = self.mapped("journal_id")
            if len(journals) == 1:
                journal = journals
        if not journal:
            raise UserError(
                _("Open the statements from a bank or cash journal before creating a transaction.")
            )
        return journal.action_quick_create_statement_line()

