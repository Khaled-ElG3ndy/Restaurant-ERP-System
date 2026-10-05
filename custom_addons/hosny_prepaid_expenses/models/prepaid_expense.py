import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


_logger = logging.getLogger(__name__)


class PrepaidExpenseSchedule(models.Model):
    _name = "prepaid.expense.schedule"
    _description = "Prepaid Expense Schedule"
    _order = "invoice_date desc, id desc"
    _check_company_auto = True

    invoice_line_id = fields.Many2one(
        "account.move.line",
        string="Vendor Bill Line",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Vendor Bill",
        related="invoice_line_id.move_id",
        store=True,
        index=True,
    )
    invoice_date = fields.Date(related="move_id.invoice_date", store=True, index=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor",
        related="move_id.partner_id",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="invoice_line_id.company_id",
        store=True,
        index=True,
    )
    company_currency_id = fields.Many2one(
        "res.currency",
        string="Company Currency",
        related="company_id.currency_id",
        store=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Invoice Currency",
        related="invoice_line_id.currency_id",
        store=True,
    )
    name = fields.Char(string="Expense", related="invoice_line_id.name", store=True)
    start_date = fields.Date(related="invoice_line_id.prepaid_start_date", store=True, index=True)
    end_date = fields.Date(related="invoice_line_id.prepaid_end_date", store=True, index=True)
    actual_account_id = fields.Many2one(
        "account.account",
        string="Actual Expense Account",
        related="invoice_line_id.prepaid_actual_account_id",
        store=True,
        index=True,
    )
    prepaid_account_id = fields.Many2one(
        "account.account",
        string="Prepaid Expense Account",
        related="invoice_line_id.prepaid_account_id",
        store=True,
        index=True,
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Branch",
        related="move_id.analytic_account_id",
        store=True,
        index=True,
    )
    analytic_distribution = fields.Json(string="Analytic Distribution", readonly=True)
    original_amount = fields.Monetary(
        string="Original Amount",
        currency_field="company_currency_id",
        required=True,
        readonly=True,
    )
    original_amount_currency = fields.Monetary(
        string="Original Amount in Invoice Currency",
        currency_field="currency_id",
        required=True,
        readonly=True,
    )
    refunded_amount = fields.Monetary(
        string="Refunded Amount",
        currency_field="company_currency_id",
        compute="_compute_totals",
        store=True,
    )
    refunded_amount_currency = fields.Monetary(
        string="Refunded Amount in Invoice Currency",
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    recognized_amount = fields.Monetary(
        string="Recognized Amount",
        currency_field="company_currency_id",
        compute="_compute_totals",
        store=True,
    )
    remaining_amount = fields.Monetary(
        string="Remaining Amount",
        currency_field="company_currency_id",
        compute="_compute_totals",
        store=True,
    )
    draft_installment_count = fields.Integer(
        string="Draft Installments",
        compute="_compute_totals",
        store=True,
    )
    posted_installment_count = fields.Integer(
        string="Posted Installments",
        compute="_compute_totals",
        store=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("partial", "Partially Recognized"),
            ("posted", "Fully Recognized"),
            ("refunded", "Refunded"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        compute="_compute_totals",
        store=True,
        index=True,
    )
    line_ids = fields.One2many(
        "prepaid.expense.schedule.line",
        "schedule_id",
        string="Installments",
        copy=False,
    )
    refund_allocation_ids = fields.One2many(
        "prepaid.expense.refund.allocation",
        "schedule_id",
        string="Credit Note Allocations",
        copy=False,
    )
    source_type = fields.Selection(
        [("vendor_bill", "مستند شراء"), ("vendor_payment", "دفعة مورد")],
        string="Prepaid Expense Source",
        default="vendor_bill",
        required=True,
        index=True,
    )
    vendor_bill_id = fields.Many2one(
        "account.move",
        string="Source Vendor Bill",
        compute="_compute_source_links",
        store=True,
        index=True,
    )
    vendor_bill_line_id = fields.Many2one(
        "account.move.line",
        string="Source Vendor Bill Line",
        compute="_compute_source_links",
        store=True,
        index=True,
    )
    vendor_payment_id = fields.Many2one(
        "account.payment",
        string="Vendor Payment",
        copy=False,
        check_company=True,
        index=True,
        ondelete="restrict",
    )
    reclassification_move_id = fields.Many2one(
        "account.move",
        string="Initial Reclassification Entry",
        copy=False,
        check_company=True,
        ondelete="restrict",
    )

    @api.depends("source_type", "invoice_line_id", "invoice_line_id.move_id")
    def _compute_source_links(self):
        for schedule in self:
            is_bill = schedule.source_type == "vendor_bill"
            schedule.vendor_bill_line_id = schedule.invoice_line_id if is_bill else False
            schedule.vendor_bill_id = schedule.invoice_line_id.move_id if is_bill else False

    @api.constrains("source_type", "vendor_payment_id", "invoice_line_id")
    def _check_source_links(self):
        for schedule in self:
            if schedule.source_type == "vendor_bill":
                if not schedule.invoice_line_id or schedule.vendor_payment_id:
                    raise ValidationError(_("A vendor-bill prepaid expense must have one vendor bill line only."))
            elif not schedule.vendor_payment_id or not schedule.invoice_line_id:
                raise ValidationError(_("A vendor-payment prepaid expense must have one vendor payment and its funding line."))

    @api.model
    def _prepaid_general_journal(self, company):
        return self.env["account.journal"].with_company(company).search([
            ("company_id", "=", company.id),
            ("type", "=", "general"),
        ], limit=1)

    @api.model
    def _prepaid_create_reclassification(
        self, *, source, source_account, prepaid_account, company_amount,
        currency, currency_amount, partner, label, analytic_account=False,
        analytic_distribution=False,
    ):
        company = source.company_id
        journal = self._prepaid_general_journal(company)
        if not journal:
            raise ValidationError(_("Configure a miscellaneous journal before creating a prepaid expense."))
        move_values = {
            "move_type": "entry",
            "date": source.date,
            "journal_id": journal.id,
            "company_id": company.id,
            "partner_id": partner.id,
            "ref": _("Prepaid expense reclassification - %s") % source.display_name,
        }
        if "analytic_account_id" in self.env["account.move"]._fields:
            move_values["analytic_account_id"] = analytic_account.id
        move = self.env["account.move"].with_company(company).create(move_values)
        foreign_currency = currency
        common = {
            "move_id": move.id,
            "name": label,
            "partner_id": partner.id,
            "currency_id": foreign_currency.id,
            "analytic_distribution": analytic_distribution or False,
        }
        debit_values = {
            **common,
            "account_id": prepaid_account.id,
            "debit": company_amount,
            "credit": 0.0,
            "amount_currency": currency_amount,
        }
        credit_values = {
            **common,
            "account_id": source_account.id,
            "debit": 0.0,
            "credit": company_amount,
            "amount_currency": -currency_amount,
        }
        lines = self.env["account.move.line"].with_context(check_move_validity=False).create([
            debit_values, credit_values,
        ])
        move.action_post()
        return move, lines.filtered(lambda line: line.debit > 0), lines.filtered(lambda line: line.credit > 0)

    @api.model
    def create_from_source(self, values):
        """Central creation service shared by vendor-bill and vendor-payment wizards."""
        source_type = values["source_type"]
        source = values["source"]
        company = source.company_id
        currency = source.currency_id
        amount_currency = currency.round(values["amount"])
        if float_compare(amount_currency, 0.0, precision_rounding=currency.rounding) <= 0:
            raise ValidationError(_("The prepaid expense amount must be greater than zero."))
        actual_account = values["actual_account"]
        prepaid_account = values["prepaid_account"]
        if actual_account == prepaid_account:
            raise ValidationError(_("The actual expense account and prepaid expense account must be different."))
        for account in (actual_account, prepaid_account):
            if company not in account.company_ids:
                raise ValidationError(_("The prepaid expense accounts must be available to the source company."))
        start_date = values["start_date"]
        end_date = values["end_date"]
        if not start_date or not end_date or end_date < start_date:
            raise ValidationError(_("The prepaid expense end date cannot be before the start date."))

        analytic_account = values.get("analytic_account") or self.env["account.analytic.account"]
        analytic_distribution = values.get("analytic_distribution") or (
            {str(analytic_account.id): 100.0} if analytic_account else False
        )
        label = values.get("name") or source.display_name
        company_amount = company.currency_id.round(currency._convert(
            amount_currency, company.currency_id, company, source.date
        ))
        reclassification = self.env["account.move"]
        payable_line = self.env["account.move.line"]

        if source_type == "vendor_bill":
            bill_line = values["source_line"]
            if (
                not source._is_prepaid_purchase_document()
                or source.state not in ("draft", "posted")
                or bill_line.move_id != source
            ):
                raise ValidationError(_("The source must be a valid purchase-document line."))
            if bill_line.prepaid_schedule_id:
                raise ValidationError(_("A prepaid expense schedule already exists for this purchase-document line."))
            _company_total, available = bill_line._prepaid_source_totals()
            if float_compare(amount_currency, available, precision_rounding=currency.rounding) > 0:
                raise ValidationError(_("The prepaid expense amount exceeds the purchase-document line amount."))
            line_values = {
                "is_prepaid_expense": True,
                "prepaid_start_date": start_date,
                "prepaid_end_date": end_date,
                "prepaid_actual_account_id": actual_account.id,
                "prepaid_account_id": prepaid_account.id,
                "prepaid_distribution_method": values["distribution_method"],
                "prepaid_installment_count": values.get("installment_count", 1),
            }
            if source.state == "draft":
                if float_compare(amount_currency, available, precision_rounding=currency.rounding) != 0:
                    raise ValidationError(_(
                        "A draft purchase-document line must be configured in full. "
                        "Post the document first to create a partial prepaid expense."
                    ))
                bill_line.write({**line_values, "account_id": prepaid_account.id})
                return self.browse()
            if bill_line.account_id == prepaid_account:
                if float_compare(amount_currency, available, precision_rounding=currency.rounding) != 0:
                    raise ValidationError(_("A bill line already posted to the prepaid account must be scheduled in full."))
                funding_line = bill_line
            else:
                reclassification, _debit_line, _credit_line = self._prepaid_create_reclassification(
                    source=source,
                    source_account=bill_line.account_id,
                    prepaid_account=prepaid_account,
                    company_amount=company_amount,
                    currency=currency,
                    currency_amount=amount_currency,
                    partner=source.partner_id,
                    label=label,
                    analytic_account=analytic_account,
                    analytic_distribution=analytic_distribution,
                )
                funding_line = bill_line
            bill_line.write(line_values)
        elif source_type == "vendor_payment":
            payment = source
            if (
                payment.partner_type != "supplier"
                or payment.payment_type != "outbound"
                or payment.state not in ("in_process", "paid")
                or payment.move_id.state != "posted"
            ):
                raise ValidationError(_("The source must be a posted outbound vendor payment."))
            payment_line = payment.move_id.line_ids.filtered(
                lambda line: line.account_id == payment.destination_account_id and line.partner_id == payment.partner_id
            )
            if len(payment_line) != 1:
                raise ValidationError(_("The vendor payment counterpart line could not be identified safely."))
            available = abs(payment_line.amount_residual_currency) if payment_line.currency_id == currency else abs(payment_line.amount_residual)
            if float_compare(amount_currency, available, precision_rounding=currency.rounding) > 0:
                raise ValidationError(_("The prepaid expense amount exceeds the unused vendor payment amount."))
            reclassification, funding_line, payable_line = self._prepaid_create_reclassification(
                source=payment,
                source_account=payment.destination_account_id,
                prepaid_account=prepaid_account,
                company_amount=company_amount,
                currency=currency,
                currency_amount=amount_currency,
                partner=payment.partner_id,
                label=label,
                analytic_account=analytic_account,
                analytic_distribution=analytic_distribution,
            )
            funding_line.write({
                "prepaid_start_date": start_date,
                "prepaid_end_date": end_date,
                "prepaid_actual_account_id": actual_account.id,
                "prepaid_account_id": prepaid_account.id,
                "prepaid_distribution_method": values["distribution_method"],
                "prepaid_installment_count": values.get("installment_count", 1),
            })
        else:
            raise ValidationError(_("Unsupported prepaid expense source."))

        periods = funding_line._prepaid_periods()
        company_amounts = funding_line._prepaid_amounts(company_amount, company.currency_id)
        currency_amounts = funding_line._prepaid_amounts(amount_currency, currency)
        schedule = self.create({
            "invoice_line_id": funding_line.id,
            "source_type": source_type,
            "vendor_payment_id": source.id if source_type == "vendor_payment" else False,
            "reclassification_move_id": reclassification.id,
            "original_amount": company_amount,
            "original_amount_currency": amount_currency,
            "analytic_distribution": analytic_distribution or False,
        })
        for sequence, ((period_start, period_end, due_date), amount, foreign_amount) in enumerate(
            zip(periods, company_amounts, currency_amounts), start=1
        ):
            self.env["prepaid.expense.schedule.line"].create({
                "schedule_id": schedule.id,
                "sequence": sequence,
                "period_start": period_start,
                "period_end": period_end,
                "due_date": due_date,
                "amount": amount,
                "amount_currency": foreign_amount,
            })._ensure_draft_move()
        funding_line.prepaid_schedule_id = schedule
        schedule._check_totals()
        if payable_line:
            (payment_line + payable_line).reconcile()
        return schedule

    _unique_invoice_line = models.Constraint(
        "UNIQUE(invoice_line_id)",
        "A prepaid expense schedule already exists for this vendor bill line.",
    )

    @api.depends(
        "line_ids.state",
        "line_ids.net_amount",
        "refund_allocation_ids.amount",
        "refund_allocation_ids.amount_currency",
        "refund_allocation_ids.kind",
        "refund_allocation_ids.refund_line_id.move_id.state",
        "original_amount",
    )
    def _compute_totals(self):
        rounding = self.env.company.currency_id.rounding
        for schedule in self:
            rounding = schedule.company_currency_id.rounding
            posted_lines = schedule.line_ids.filtered(lambda line: line.state == "posted")
            draft_lines = schedule.line_ids.filtered(lambda line: line.state == "draft")
            active_allocations = schedule.refund_allocation_ids.filtered(
                lambda allocation: allocation.refund_line_id.move_id.state == "posted"
            )
            recognized_refunds = sum(
                active_allocations.filtered(lambda allocation: allocation.kind == "recognized").mapped("amount")
            )
            schedule.refunded_amount = sum(active_allocations.mapped("amount"))
            schedule.refunded_amount_currency = sum(active_allocations.mapped("amount_currency"))
            schedule.recognized_amount = max(sum(posted_lines.mapped("amount")) - recognized_refunds, 0.0)
            net_original = max(schedule.original_amount - schedule.refunded_amount, 0.0)
            schedule.remaining_amount = max(net_original - schedule.recognized_amount, 0.0)
            schedule.draft_installment_count = len(draft_lines.filtered(lambda line: line.net_amount > 0))
            schedule.posted_installment_count = len(posted_lines)
            if schedule.line_ids and all(line.state == "cancel" for line in schedule.line_ids):
                schedule.state = "refunded" if schedule.refunded_amount else "cancel"
            elif float_is_zero(net_original, precision_rounding=rounding):
                schedule.state = "refunded"
            elif float_is_zero(schedule.remaining_amount, precision_rounding=rounding):
                schedule.state = "posted"
            elif schedule.recognized_amount:
                schedule.state = "partial"
            else:
                schedule.state = "draft"

    def _check_totals(self, after_refund=False):
        for schedule in self:
            expected = schedule.original_amount - (schedule.refunded_amount if after_refund else 0.0)
            recognized_refunds = sum(
                schedule.refund_allocation_ids.filtered(
                    lambda allocation: allocation.kind == "recognized"
                    and allocation.refund_line_id.move_id.state == "posted"
                ).mapped("amount")
            )
            actual = sum(schedule.line_ids.mapped("net_amount")) - recognized_refunds
            if float_compare(actual, expected, precision_rounding=schedule.company_currency_id.rounding) != 0:
                raise ValidationError(_(
                    "The prepaid schedule total (%(actual)s) does not equal the expected amount (%(expected)s).",
                    actual=actual,
                    expected=expected,
                ))

    def unlink(self):
        if self.reclassification_move_id.filtered(lambda move: move.state == "posted"):
            raise UserError(_(
                "A prepaid expense with a posted initial reclassification entry cannot be deleted. "
                "Reverse it explicitly instead."
            ))
        if self.line_ids.filtered(lambda line: line.state == "posted"):
            raise UserError(_("A prepaid expense schedule containing posted entries cannot be deleted."))
        return super().unlink()


class PrepaidExpenseScheduleLine(models.Model):
    _name = "prepaid.expense.schedule.line"
    _description = "Prepaid Expense Installment"
    _order = "due_date, sequence, id"
    _check_company_auto = True

    schedule_id = fields.Many2one(
        "prepaid.expense.schedule",
        string="Prepaid Expense",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    sequence = fields.Integer(string="Installment Number", required=True)
    due_date = fields.Date(string="Due Date", required=True, index=True)
    period_start = fields.Date(string="Period From", required=True)
    period_end = fields.Date(string="Period To", required=True)
    company_id = fields.Many2one(related="schedule_id.company_id", store=True, index=True)
    company_currency_id = fields.Many2one(string="Company Currency", related="company_id.currency_id", store=True)
    currency_id = fields.Many2one(string="Invoice Currency", related="schedule_id.currency_id", store=True)
    partner_id = fields.Many2one(related="schedule_id.partner_id", store=True, index=True)
    invoice_id = fields.Many2one(related="schedule_id.move_id", store=True, index=True)
    invoice_line_id = fields.Many2one(related="schedule_id.invoice_line_id", store=True, index=True)
    actual_account_id = fields.Many2one(related="schedule_id.actual_account_id", store=True, index=True)
    prepaid_account_id = fields.Many2one(related="schedule_id.prepaid_account_id", store=True, index=True)
    analytic_account_id = fields.Many2one(related="schedule_id.analytic_account_id", store=True, index=True)
    amount = fields.Monetary(
        string="Original Amount",
        currency_field="company_currency_id",
        required=True,
        readonly=True,
    )
    amount_currency = fields.Monetary(
        string="Original Amount in Invoice Currency",
        currency_field="currency_id",
        required=True,
        readonly=True,
    )
    refunded_amount = fields.Monetary(
        string="Refunded Amount",
        currency_field="company_currency_id",
        compute="_compute_net_amounts",
        store=True,
    )
    refunded_amount_currency = fields.Monetary(
        string="Refunded Amount in Invoice Currency",
        currency_field="currency_id",
        compute="_compute_net_amounts",
        store=True,
    )
    net_amount = fields.Monetary(
        string="Amount",
        currency_field="company_currency_id",
        compute="_compute_net_amounts",
        store=True,
    )
    net_amount_currency = fields.Monetary(
        string="Amount in Invoice Currency",
        currency_field="currency_id",
        compute="_compute_net_amounts",
        store=True,
    )
    accrual_move_id = fields.Many2one(
        "account.move",
        string="Journal Entry",
        copy=False,
        readonly=True,
        check_company=True,
        ondelete="restrict",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancel", "Cancelled")],
        string="Status",
        compute="_compute_state",
        store=True,
        index=True,
    )
    last_error = fields.Text(string="Last Posting Error", copy=False, readonly=True)
    refund_allocation_ids = fields.One2many(
        "prepaid.expense.refund.allocation",
        "schedule_line_id",
        string="Refund Allocations",
        copy=False,
    )

    _unique_sequence = models.Constraint(
        "UNIQUE(schedule_id, sequence)",
        "Installment numbers must be unique inside a prepaid expense schedule.",
    )

    @api.depends(
        "amount",
        "amount_currency",
        "refund_allocation_ids.amount",
        "refund_allocation_ids.amount_currency",
        "refund_allocation_ids.refund_line_id.move_id.state",
    )
    def _compute_net_amounts(self):
        for line in self:
            allocations = line.refund_allocation_ids.filtered(
                lambda allocation: allocation.refund_line_id.move_id.state == "posted"
            )
            line.refunded_amount = sum(allocations.mapped("amount"))
            line.refunded_amount_currency = sum(allocations.mapped("amount_currency"))
            line.net_amount = max(line.amount - line.refunded_amount, 0.0)
            line.net_amount_currency = max(line.amount_currency - line.refunded_amount_currency, 0.0)

    @api.depends("accrual_move_id.state", "net_amount")
    def _compute_state(self):
        for line in self:
            if float_is_zero(line.net_amount, precision_rounding=line.company_currency_id.rounding):
                line.state = "cancel"
            elif line.accrual_move_id.state == "posted":
                line.state = "posted"
            elif line.accrual_move_id.state == "cancel":
                line.state = "cancel"
            else:
                line.state = "draft"

    def _move_values(self):
        self.ensure_one()
        schedule = self.schedule_id
        values = {
            "move_type": "entry",
            "date": self.due_date,
            "journal_id": schedule.move_id.journal_id.id,
            "ref": _("Prepaid expense %(invoice)s - installment %(number)s", invoice=schedule.move_id.name, number=self.sequence),
            "company_id": self.company_id.id,
        }
        if "analytic_account_id" in self.env["account.move"]._fields:
            values["analytic_account_id"] = schedule.analytic_account_id.id
        return values

    def _line_values(self, move):
        self.ensure_one()
        analytic_values = self.invoice_line_id._prepaid_dynamic_analytic_values()
        currency = self.currency_id
        return [
            {
                "move_id": move.id,
                "name": self.schedule_id.name,
                "account_id": self.actual_account_id.id,
                "partner_id": self.partner_id.id,
                "debit": self.net_amount,
                "credit": 0.0,
                "currency_id": currency.id,
                "amount_currency": self.net_amount_currency,
                **analytic_values,
            },
            {
                "move_id": move.id,
                "name": self.schedule_id.name,
                "account_id": self.prepaid_account_id.id,
                "partner_id": self.partner_id.id,
                "debit": 0.0,
                "credit": self.net_amount,
                "currency_id": currency.id,
                "amount_currency": -self.net_amount_currency,
                **analytic_values,
            },
        ]

    def _ensure_draft_move(self):
        for line in self:
            if float_is_zero(line.net_amount, precision_rounding=line.company_currency_id.rounding):
                continue
            if line.accrual_move_id:
                continue
            move = self.env["account.move"].with_company(line.company_id).create(line._move_values())
            created_lines = self.env["account.move.line"].with_context(check_move_validity=False).create(
                line._line_values(move)
            )
            analytic_distribution = line.invoice_line_id.analytic_distribution
            if analytic_distribution:
                created_lines.write({"analytic_distribution": analytic_distribution})
            line.accrual_move_id = move
        return self

    def _sync_draft_move(self):
        for line in self:
            move = line.accrual_move_id
            if move and move.state == "posted":
                raise UserError(_("Posted prepaid expense entries cannot be modified."))
            if float_is_zero(line.net_amount, precision_rounding=line.company_currency_id.rounding):
                if move:
                    line.accrual_move_id = False
                    move.with_context(force_delete=True).unlink()
                continue
            line._ensure_draft_move()
            move = line.accrual_move_id
            move.with_context(check_move_validity=False).line_ids.unlink()
            created_lines = self.env["account.move.line"].with_context(check_move_validity=False).create(
                line._line_values(move)
            )
            if line.invoice_line_id.analytic_distribution:
                created_lines.write({"analytic_distribution": line.invoice_line_id.analytic_distribution})

    def _post_due_entries(self):
        today = fields.Date.context_today(self)
        candidates = self.filtered(
            lambda line: line.state == "draft" and line.due_date <= today and line.accrual_move_id.state == "draft"
        )
        for line in candidates:
            try:
                with self.env.cr.savepoint():
                    line.accrual_move_id.with_company(line.company_id).action_post()
                    line.last_error = False
            except Exception as error:  # one bad period must not stop the daily job
                _logger.exception(
                    "Failed to post prepaid expense installment %s (schedule %s)",
                    line.id,
                    line.schedule_id.id,
                )
                line.last_error = str(error)
        return True

    @api.model
    def _cron_post_due_entries(self):
        today = fields.Date.context_today(self)
        due_lines = self.sudo().search([
            ("state", "=", "draft"),
            ("due_date", "<=", today),
            ("accrual_move_id.state", "=", "draft"),
        ], order="company_id, due_date, id")
        _logger.info("Prepaid expense daily cron found %s due installment(s) through %s", len(due_lines), today)
        return due_lines._post_due_entries()

    def action_open_journal_entry(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Entry"),
            "res_model": "account.move",
            "res_id": self.accrual_move_id.id,
            "view_mode": "form",
        }

    def write(self, values):
        protected = set(values) - {"last_error"}
        if protected and self.filtered(lambda line: line.state == "posted"):
            raise UserError(_("Posted prepaid expense installments cannot be modified."))
        return super().write(values)

    def unlink(self):
        if self.filtered(lambda line: line.state == "posted"):
            raise UserError(_("Posted prepaid expense installments cannot be deleted."))
        moves = self.accrual_move_id.filtered(lambda move: move.state == "draft")
        self.accrual_move_id = False
        result = super().unlink()
        moves.with_context(force_delete=True).unlink()
        return result


class PrepaidExpenseRefundAllocation(models.Model):
    _name = "prepaid.expense.refund.allocation"
    _description = "Prepaid Expense Credit Note Allocation"
    _order = "id"
    _check_company_auto = True

    refund_line_id = fields.Many2one(
        "account.move.line",
        string="Credit Note Line",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    schedule_id = fields.Many2one(
        "prepaid.expense.schedule",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    schedule_line_id = fields.Many2one(
        "prepaid.expense.schedule.line",
        string="Installment",
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(related="schedule_id.company_id", store=True, index=True)
    company_currency_id = fields.Many2one(string="Company Currency", related="company_id.currency_id", store=True)
    currency_id = fields.Many2one(string="Invoice Currency", related="schedule_id.currency_id", store=True)
    kind = fields.Selection(
        [("future", "Future Prepaid Balance"), ("recognized", "Recognized Expense Reversal")],
        required=True,
        index=True,
    )
    amount = fields.Monetary(currency_field="company_currency_id", required=True)
    amount_currency = fields.Monetary(currency_field="currency_id", required=True)
    adjustment_move_id = fields.Many2one(
        "account.move",
        string="Adjustment Entry",
        check_company=True,
        copy=False,
        ondelete="restrict",
    )

    @api.constrains("kind", "schedule_line_id")
    def _check_schedule_line_kind(self):
        for allocation in self:
            if allocation.kind == "future" and not allocation.schedule_line_id:
                raise ValidationError(_("A future prepaid refund allocation must reference an installment."))
            if allocation.schedule_line_id and allocation.schedule_line_id.schedule_id != allocation.schedule_id:
                raise ValidationError(_("The refund allocation installment belongs to a different schedule."))
