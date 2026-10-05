from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _hosny_with_pos_analytic_context(self):
        self.ensure_one()
        return self.with_context(hosny_pos_session_id=self.id)

    def _create_account_move(
        self,
        balancing_account=False,
        amount_to_balance=0,
        bank_payment_method_diffs=None,
    ):
        self.ensure_one()
        return super(
            PosSession, self._hosny_with_pos_analytic_context()
        )._create_account_move(
            balancing_account,
            amount_to_balance,
            bank_payment_method_diffs,
        )

    def _create_diff_account_move_for_split_payment_method(self, payment_method, diff_amount):
        self.ensure_one()
        return super(
            PosSession, self._hosny_with_pos_analytic_context()
        )._create_diff_account_move_for_split_payment_method(payment_method, diff_amount)

    def _post_statement_difference(self, amount):
        self.ensure_one()
        return super(
            PosSession, self._hosny_with_pos_analytic_context()
        )._post_statement_difference(amount)
