from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="الحساب التحليلي",
        check_company=True,
        copy=True,
    )

    def _hosny_requires_analytic_account(self):
        self.ensure_one()
        if self.move_type == "entry":
            return not (self.origin_payment_id or self.statement_line_id)
        return self.move_type in (
            "out_invoice",
            "out_refund",
            "in_invoice",
            "in_refund",
            "out_receipt",
            "in_receipt",
        )

    def _hosny_analytic_distribution(self):
        self.ensure_one()
        return {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else False

    def _hosny_analytic_lines(self):
        return self.line_ids.filtered(lambda line: line.display_type == "product")

    @api.model
    def _hosny_extract_command_ids(self, commands):
        ids = []
        for command in commands or []:
            if isinstance(command, int):
                ids.append(command)
                continue
            if not isinstance(command, (tuple, list)) or not command:
                continue
            if command[0] == 4 and len(command) > 1:
                ids.append(command[1])
            elif command[0] == 6 and len(command) > 2:
                ids.extend(command[2])
        return ids

    @api.model
    def _hosny_get_pos_analytic_account_from_vals(self, vals):
        PosSession = self.env["pos.session"].sudo()
        PosOrder = self.env["pos.order"].sudo()
        PosPayment = self.env["pos.payment"].sudo()

        session = PosSession.browse()
        if self.env.context.get("hosny_pos_session_id"):
            session = PosSession.browse(self.env.context["hosny_pos_session_id"]).exists()
        if vals.get("pos_order_ids"):
            session = PosOrder.browse(self._hosny_extract_command_ids(vals["pos_order_ids"])).mapped("session_id")[:1]
        if not session and vals.get("reversed_pos_order_id"):
            session = PosOrder.browse(vals["reversed_pos_order_id"]).session_id
        if not session and vals.get("pos_payment_ids"):
            session = PosPayment.browse(self._hosny_extract_command_ids(vals["pos_payment_ids"])).mapped("session_id")[:1]
        if not session and vals.get("ref"):
            session = PosSession.search([("name", "=", vals["ref"])], limit=1)
            if not session:
                sessions = PosSession.search([("state", "!=", "closed")])
                session = sessions.filtered(lambda pos_session: pos_session.name and pos_session.name in vals["ref"])[:1]

        return session.config_id.analytic_account_id if session else self.env["account.analytic.account"]

    @api.model
    def _hosny_add_pos_analytic_account_to_vals(self, vals):
        if vals.get("analytic_account_id") or "analytic_account_id" not in self._fields:
            return vals
        analytic_account = self._hosny_get_pos_analytic_account_from_vals(vals)
        if analytic_account:
            vals = dict(vals)
            vals["analytic_account_id"] = analytic_account.id
        return vals

    def _hosny_sync_header_analytic_distribution(self):
        for move in self.filtered("analytic_account_id"):
            distribution = move._hosny_analytic_distribution()
            for line in move._hosny_analytic_lines():
                if line.analytic_distribution != distribution:
                    line.analytic_distribution = distribution

    @api.onchange("analytic_account_id")
    def _onchange_analytic_account_id(self):
        self._hosny_sync_header_analytic_distribution()

    def _hosny_check_required_analytic_account_id(self, posting=False):
        for move in self:
            if (
                move._hosny_requires_analytic_account()
                and not move.analytic_account_id
                and (posting or move.state == "draft")
            ):
                action = _("posting") if posting else _("saving")
                raise ValidationError(_("Please select الحساب التحليلي before %s this document.") % action)

    @api.constrains("analytic_account_id", "move_type", "origin_payment_id", "statement_line_id", "state")
    def _check_required_analytic_account_id(self):
        self._hosny_check_required_analytic_account_id()

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._hosny_add_pos_analytic_account_to_vals(vals) for vals in vals_list]
        moves = super().create(vals_list)
        moves._hosny_sync_header_analytic_distribution()
        moves._hosny_check_required_analytic_account_id()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if "analytic_account_id" in vals or "line_ids" in vals or "invoice_line_ids" in vals:
            self._hosny_sync_header_analytic_distribution()
        self._hosny_check_required_analytic_account_id()
        return res

    def _post(self, soft=True):
        self._hosny_check_required_analytic_account_id(posting=True)
        self._hosny_sync_header_analytic_distribution()
        return super()._post(soft=soft)
