from collections import defaultdict

from odoo import Command, _, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
class PosSession(models.Model):
    _inherit = "pos.session"

    def _check_multi_cash_in_out_access(self):
        if not self.user_has_groups("account.group_account_invoice"):
            raise AccessError(
                _("You do not have the access rights required to post POS cash movements.")
            )

    def _check_multi_cash_in_out_state(self):
        self.ensure_one()
        if self.state == "closed":
            raise UserError(_("This POS session is already closed."))
        if self.state not in ("opened", "closing_control"):
            raise UserError(
                _("POS cash in/out is only available while the POS session is open.")
            )

    def _get_multi_cash_in_out_payment_methods(self):
        self.ensure_one()
        return self.payment_method_ids.filtered(lambda pm: pm.type in ("cash", "bank") and pm.journal_id)

    def _get_multi_cash_in_out_previous_session(self):
        self.ensure_one()
        return self.search(
            [
                ("config_id", "=", self.config_id.id),
                ("id", "<", self.id),
                ("rescue", "=", False),
            ],
            limit=1,
            order="id desc",
        )

    def _get_multi_cash_in_out_payment_stats(self, payment_methods):
        self.ensure_one()
        totals = defaultdict(float)
        counts = defaultdict(int)
        payments = self.env["pos.payment"].search(
            [
                ("session_id", "=", self.id),
                ("payment_method_id", "in", payment_methods.ids),
            ]
        )
        for payment in payments:
            totals[payment.payment_method_id.id] += payment.amount
            counts[payment.payment_method_id.id] += 1
        return totals, counts

    def _get_multi_cash_in_out_move_adjustments(self):
        self.ensure_one()
        totals = defaultdict(float)
        moves = self.env["account.move"].search(
            [
                ("pos_session_id", "=", self.id),
                ("is_pos_payment_adjustment", "=", True),
                ("state", "=", "posted"),
            ]
        )
        for move in moves:
            totals[move.pos_payment_method_id.id] += move.pos_adjustment_amount
        return totals

    def _get_multi_cash_in_out_cash_statement_total(self, payment_method):
        self.ensure_one()
        return sum(
            self.statement_line_ids.filtered(
                lambda line: line.journal_id == payment_method.journal_id
            ).mapped("amount")
        )

    def _get_multi_cash_in_out_expected_amount(self, payment_method, payment_totals=None, move_adjustments=None):
        self.ensure_one()
        payment_totals = payment_totals or {}
        move_adjustments = move_adjustments or {}
        expected = payment_totals.get(payment_method.id, 0.0)
        if payment_method.is_cash_count:
            opening_balance = 0.0
            if payment_method.journal_id == self.cash_journal_id:
                previous_session = self._get_multi_cash_in_out_previous_session()
                opening_balance = previous_session.cash_register_balance_end_real if previous_session else 0.0
            expected += opening_balance + self._get_multi_cash_in_out_cash_statement_total(payment_method)
        expected += move_adjustments.get(payment_method.id, 0.0)
        return self.currency_id.round(expected)

    def _get_multi_cash_in_out_source_account(self, payment_method):
        self.ensure_one()
        return (
            payment_method.outstanding_account_id
            or payment_method.journal_id.default_account_id
            or self.company_id.account_journal_payment_debit_account_id
        )

    def _get_multi_cash_in_out_counterpart_account(self, payment_method, difference):
        self.ensure_one()
        compare = self.currency_id.compare_amounts(difference, 0)
        journal = payment_method.journal_id
        if compare > 0:
            return journal.profit_account_id
        if compare < 0:
            return journal.loss_account_id
        return self.env["account.account"]

    def _get_multi_cash_in_out_entry_counterpart_account(self, payment_method, difference):
        self.ensure_one()
        if payment_method.journal_id.suspense_account_id:
            return payment_method.journal_id.suspense_account_id
        counterpart_account = self._get_multi_cash_in_out_counterpart_account(payment_method, difference)
        if counterpart_account:
            return counterpart_account
        return (
            self._get_multi_cash_in_out_source_account(payment_method)
            or payment_method.journal_id.default_account_id
            or payment_method.journal_id.suspense_account_id
        )

    def _get_multi_cash_in_out_ref(self, payment_method):
        self.ensure_one()
        return _("POS Cash In/Out - Session %s - Payment Method %s", self.name, payment_method.name)

    def _get_multi_cash_in_out_line_name(self, payment_method, reason):
        self.ensure_one()
        if reason:
            return _("%s - %s", payment_method.name, reason)
        return _("%s Cash In/Out", payment_method.name)

    def _validate_multi_cash_in_out_accounts(self, payment_method, difference):
        self.ensure_one()
        source_account = self._get_multi_cash_in_out_source_account(payment_method)
        if not source_account:
            raise UserError(
                _(
                    "Please configure an outstanding or default account for the payment method %s.",
                    payment_method.display_name,
                )
            )
        counterpart_account = self._get_multi_cash_in_out_entry_counterpart_account(
            payment_method, difference
        )
        if not counterpart_account:
            raise UserError(
                _(
                    "Please configure a suspense, default, or transfer account on the journal %s.",
                    payment_method.journal_id.display_name,
                )
            )

    def _create_multi_cash_in_out_move(self, payment_method, expected, counted, difference, reason):
        self.ensure_one()
        source_account = self._get_multi_cash_in_out_source_account(payment_method)
        counterpart_account = self._get_multi_cash_in_out_entry_counterpart_account(
            payment_method, difference
        )
        line_name = self._get_multi_cash_in_out_line_name(payment_method, reason)
        amounts = self._update_amounts(
            {"amount": 0.0, "amount_converted": 0.0},
            {"amount": counted},
            fields.Datetime.now(),
        )
        source_vals = self._debit_amounts(
            {
                "name": line_name,
                "account_id": source_account.id,
            },
            amounts["amount"],
            amounts["amount_converted"],
        )
        counterpart_vals = self._credit_amounts(
            {
                "name": line_name,
                "account_id": counterpart_account.id,
            },
            amounts["amount"],
            amounts["amount_converted"],
        )
        move = self.env["account.move"].create(
            {
                "journal_id": payment_method.journal_id.id,
                "date": fields.Date.context_today(self),
                "ref": self._get_multi_cash_in_out_ref(payment_method),
                "line_ids": [Command.create(source_vals), Command.create(counterpart_vals)],
                "pos_session_id": self.id,
                "pos_payment_method_id": payment_method.id,
                "is_pos_payment_adjustment": True,
                "pos_adjustment_amount": difference,
                "pos_expected_amount": expected,
                "pos_counted_amount": counted,
                "pos_adjustment_reason": reason,
            }
        )
        move._post()
        return move

    def _prepare_multi_cash_in_out_response_line(
        self, payment_method, expected, counted, difference, reason, entry=False
    ):
        self.ensure_one()
        return {
            "payment_method_id": payment_method.id,
            "payment_method_name": payment_method.name,
            "expected": self.currency_id.round(expected),
            "counted": self.currency_id.round(counted),
            "difference": self.currency_id.round(difference),
            "reason": reason,
            "entry_created": bool(entry),
            "entry_model": entry._name if entry else False,
            "entry_id": entry.id if entry else False,
        }

    def _normalize_multi_cash_in_out_payload(self, data, allowed_payment_methods):
        self.ensure_one()
        if not isinstance(data, list):
            raise ValidationError(_("Invalid cash in/out payload."))

        normalized_lines = []
        seen_payment_methods = set()
        payment_methods_by_id = {pm.id: pm for pm in allowed_payment_methods}

        for line in data:
            if not isinstance(line, dict):
                raise ValidationError(_("Invalid cash in/out line."))
            payment_method_id = int(line.get("payment_method_id") or 0)
            payment_method = payment_methods_by_id.get(payment_method_id)
            if not payment_method:
                raise UserError(_("The selected payment method is not available in this POS session."))
            if payment_method_id in seen_payment_methods:
                raise ValidationError(_("A payment method was submitted more than once."))
            seen_payment_methods.add(payment_method_id)

            counted = line.get("counted")
            if counted in (False, None, ""):
                continue

            try:
                counted = float(counted)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    _("Amount must be a valid number for payment method %s.", payment_method.name)
                ) from exc

            normalized_lines.append(
                {
                    "payment_method": payment_method,
                    "counted": self.currency_id.round(counted),
                    "reason": (line.get("reason") or "").strip(),
                }
            )

        if not normalized_lines:
            raise UserError(_("Please enter at least one amount before confirming."))
        return normalized_lines

    def get_multi_cash_in_out_data(self):
        self.ensure_one()
        self._check_multi_cash_in_out_access()
        self._check_multi_cash_in_out_state()

        payment_methods = self._get_multi_cash_in_out_payment_methods().sorted(
            lambda pm: (pm.sequence, pm.id)
        )
        payment_totals, _payment_counts = self._get_multi_cash_in_out_payment_stats(payment_methods)
        move_adjustments = self._get_multi_cash_in_out_move_adjustments()
        lines = []

        for payment_method in payment_methods:
            expected = self._get_multi_cash_in_out_expected_amount(
                payment_method,
                payment_totals=payment_totals,
                move_adjustments=move_adjustments,
            )
            lines.append(
                {
                    "payment_method_id": payment_method.id,
                    "name": payment_method.name,
                    "type": payment_method.type,
                    "expected": expected,
                }
            )

        return {
            "lines": lines,
            "currency_id": self.currency_id.id,
        }

    def action_multi_cash_in_out(self, data):
        self.ensure_one()
        self._check_multi_cash_in_out_access()
        self._check_multi_cash_in_out_state()

        payment_methods = self._get_multi_cash_in_out_payment_methods()
        normalized_lines = self._normalize_multi_cash_in_out_payload(data, payment_methods)
        payment_totals, _payment_counts = self._get_multi_cash_in_out_payment_stats(payment_methods)
        move_adjustments = self._get_multi_cash_in_out_move_adjustments()

        processed_lines = []
        created_entries = []

        for line in normalized_lines:
            payment_method = line["payment_method"]
            expected = self._get_multi_cash_in_out_expected_amount(
                payment_method,
                payment_totals=payment_totals,
                move_adjustments=move_adjustments,
            )
            counted = self.currency_id.round(line["counted"])
            difference = self.currency_id.round(counted - expected)
            self._validate_multi_cash_in_out_accounts(payment_method, difference)

            entry = self._create_multi_cash_in_out_move(
                payment_method,
                expected,
                counted,
                difference,
                line["reason"],
            )
            created_entries.append(entry)
            move_adjustments[payment_method.id] += difference
            processed_lines.append(
                self._prepare_multi_cash_in_out_response_line(
                    payment_method,
                    expected,
                    counted,
                    difference,
                    line["reason"],
                    entry=entry,
                )
            )

        created_count = len(created_entries)
        message = _("Successfully posted %s POS cash movement(s).", created_count)

        return {
            "processed_lines": processed_lines,
            "created_count": created_count,
            "message": message,
        }

    def get_closing_control_data(self):
        self.ensure_one()
        data = super().get_closing_control_data()
        move_adjustments = self._get_multi_cash_in_out_move_adjustments()
        if data.get("default_cash_details"):
            default_cash_details = data["default_cash_details"]
            default_cash_details["amount"] = self.currency_id.round(
                default_cash_details["amount"]
                + move_adjustments.get(default_cash_details["id"], 0.0)
            )
        for payment_method in data.get("other_payment_methods", []):
            payment_method["amount"] = self.currency_id.round(
                payment_method["amount"] + move_adjustments.get(payment_method["id"], 0.0)
            )
        return data

    def _get_related_account_moves(self):
        related_moves = super()._get_related_account_moves()
        adjustment_moves = self.env["account.move"].search(
            [
                ("pos_session_id", "in", self.ids),
                ("is_pos_payment_adjustment", "=", True),
            ]
        )
        return related_moves | adjustment_moves
