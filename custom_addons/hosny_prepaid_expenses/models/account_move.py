import calendar
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    is_prepaid_expense = fields.Boolean(
        string="Prepaid Expense",
        copy=True,
        help="Post this vendor bill line to a prepaid account and recognize it periodically.",
    )
    prepaid_start_date = fields.Date(string="Start Date", copy=True)
    prepaid_end_date = fields.Date(string="End Date", copy=True)
    prepaid_actual_account_id = fields.Many2one(
        "account.account",
        string="Actual Expense Account",
        check_company=True,
        copy=True,
    )
    prepaid_account_id = fields.Many2one(
        "account.account",
        string="Prepaid Expense Account",
        check_company=True,
        copy=True,
    )
    prepaid_distribution_method = fields.Selection(
        [
            ("monthly", "Monthly"),
            ("daily", "Daily"),
            ("custom", "Custom Installments"),
        ],
        string="Distribution Method",
        default="monthly",
        required=True,
        copy=True,
    )
    prepaid_installment_count = fields.Integer(
        string="Number of Installments",
        default=1,
        copy=True,
    )
    prepaid_monthly_due_day = fields.Integer(
        string="Monthly Due Day",
        help="Leave zero to use the period end date. Values 1-31 are adjusted to the month length.",
        copy=True,
    )
    prepaid_installment_amount = fields.Monetary(
        string="Calculated Installment",
        currency_field="currency_id",
        compute="_compute_prepaid_preview",
        store=True,
    )
    prepaid_recognized_amount = fields.Monetary(
        string="Recognized Amount",
        currency_field="company_currency_id",
        compute="_compute_prepaid_schedule_totals",
        store=True,
    )
    prepaid_remaining_amount = fields.Monetary(
        string="Remaining Amount",
        currency_field="company_currency_id",
        compute="_compute_prepaid_schedule_totals",
        store=True,
    )
    prepaid_schedule_state = fields.Selection(
        [
            ("none", "Not Generated"),
            ("draft", "Draft"),
            ("partial", "Partially Recognized"),
            ("posted", "Fully Recognized"),
            ("refunded", "Refunded"),
            ("cancel", "Cancelled"),
        ],
        string="Schedule Status",
        compute="_compute_prepaid_schedule_totals",
        store=True,
    )
    prepaid_schedule_id = fields.Many2one(
        "prepaid.expense.schedule",
        string="Prepaid Expense Schedule",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    prepaid_origin_line_id = fields.Many2one(
        "account.move.line",
        string="Original Prepaid Expense Line",
        copy=False,
        domain="[('is_prepaid_expense', '=', True), ('move_id.move_type', '=', 'in_invoice'), ('move_id.state', '=', 'posted'), ('company_id', '=', company_id)]",
        help="Required on a prepaid vendor credit note so the remaining original schedule can be reduced safely.",
    )
    prepaid_refund_allocation_ids = fields.One2many(
        "prepaid.expense.refund.allocation",
        "refund_line_id",
        string="Refund Allocations",
        copy=False,
    )

    @api.depends(
        "is_prepaid_expense",
        "price_subtotal",
        "currency_id",
        "prepaid_start_date",
        "prepaid_end_date",
        "prepaid_distribution_method",
        "prepaid_installment_count",
    )
    def _compute_prepaid_preview(self):
        for line in self:
            line.prepaid_installment_amount = 0.0
            if not line.is_prepaid_expense or not line.prepaid_start_date or not line.prepaid_end_date:
                continue
            periods = line._prepaid_periods()
            if periods:
                line.prepaid_installment_amount = line.currency_id.round(
                    abs(line.price_subtotal) / len(periods)
                )

    @api.depends(
        "prepaid_schedule_id.recognized_amount",
        "prepaid_schedule_id.remaining_amount",
        "prepaid_schedule_id.state",
    )
    def _compute_prepaid_schedule_totals(self):
        for line in self:
            schedule = line.prepaid_schedule_id
            line.prepaid_recognized_amount = schedule.recognized_amount if schedule else 0.0
            line.prepaid_remaining_amount = schedule.remaining_amount if schedule else 0.0
            line.prepaid_schedule_state = schedule.state if schedule else "none"

    @api.onchange("is_prepaid_expense")
    def _onchange_is_prepaid_expense(self):
        for line in self:
            if line.is_prepaid_expense and not line.prepaid_actual_account_id:
                line.prepaid_actual_account_id = line.account_id

    @api.onchange("prepaid_account_id")
    def _onchange_prepaid_account_id(self):
        for line in self.filtered(lambda item: item.is_prepaid_expense and item.prepaid_account_id):
            line.account_id = line.prepaid_account_id

    @api.onchange("prepaid_origin_line_id")
    def _onchange_prepaid_origin_line_id(self):
        for line in self.filtered("prepaid_origin_line_id"):
            origin = line.prepaid_origin_line_id
            line.is_prepaid_expense = True
            line.prepaid_start_date = origin.prepaid_start_date
            line.prepaid_end_date = origin.prepaid_end_date
            line.prepaid_actual_account_id = origin.prepaid_actual_account_id
            line.prepaid_account_id = origin.prepaid_account_id
            line.prepaid_distribution_method = origin.prepaid_distribution_method
            line.prepaid_installment_count = origin.prepaid_installment_count
            line.prepaid_monthly_due_day = origin.prepaid_monthly_due_day
            line.account_id = origin.prepaid_account_id

    @api.constrains(
        "is_prepaid_expense",
        "prepaid_start_date",
        "prepaid_end_date",
        "prepaid_actual_account_id",
        "prepaid_account_id",
        "prepaid_distribution_method",
        "prepaid_installment_count",
        "prepaid_monthly_due_day",
        "price_subtotal",
    )
    def _check_prepaid_configuration(self):
        for line in self.filtered(lambda item: item.is_prepaid_expense and item.display_type == "product"):
            if not line.move_id.is_purchase_document(include_receipts=True):
                raise ValidationError(_("Prepaid expenses are only available on purchase documents."))
            missing = []
            if not line.prepaid_actual_account_id:
                missing.append(_("Actual Expense Account"))
            if not line.prepaid_account_id:
                missing.append(_("Prepaid Expense Account"))
            if not line.prepaid_start_date:
                missing.append(_("Start Date"))
            if not line.prepaid_end_date:
                missing.append(_("End Date"))
            if missing:
                raise ValidationError(_("Missing prepaid expense values: %s") % ", ".join(missing))
            if line.prepaid_end_date < line.prepaid_start_date:
                raise ValidationError(_("The prepaid expense end date cannot be before the start date."))
            if line.prepaid_actual_account_id == line.prepaid_account_id:
                raise ValidationError(_("The actual expense account and prepaid expense account must be different."))
            if line.prepaid_distribution_method == "custom" and line.prepaid_installment_count <= 0:
                raise ValidationError(_("The number of installments must be greater than zero."))
            if not 0 <= line.prepaid_monthly_due_day <= 31:
                raise ValidationError(_("The monthly due day must be between 1 and 31, or zero for period end."))
            if float_compare(abs(line.price_subtotal), 0.0, precision_rounding=line.currency_id.rounding) <= 0:
                raise ValidationError(_("The prepaid expense amount must be greater than zero."))
            for account in (line.prepaid_actual_account_id, line.prepaid_account_id):
                if line.company_id not in account.company_ids:
                    raise ValidationError(_("The prepaid expense accounts must be available to the invoice company."))
            if (
                line.move_id.move_type == "in_refund"
                and not line.prepaid_origin_line_id
                and not self.env.context.get("include_business_fields")
            ):
                raise ValidationError(_("Select the original prepaid expense line on every prepaid vendor credit note line."))
            if line.prepaid_origin_line_id and line.prepaid_origin_line_id.company_id != line.company_id:
                raise ValidationError(_("The original prepaid expense and credit note must belong to the same company."))

    def _prepaid_due_date(self, period_end):
        self.ensure_one()
        if not self.prepaid_monthly_due_day:
            return period_end
        day = min(self.prepaid_monthly_due_day, calendar.monthrange(period_end.year, period_end.month)[1])
        return period_end.replace(day=day)

    def _prepaid_periods(self):
        self.ensure_one()
        start = self.prepaid_start_date
        end = self.prepaid_end_date
        if not start or not end or end < start:
            return []
        if self.prepaid_distribution_method in ("monthly", "daily"):
            periods = []
            cursor = start
            while cursor <= end:
                month_end = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
                period_end = min(month_end, end)
                periods.append((cursor, period_end, self._prepaid_due_date(period_end)))
                cursor = period_end + timedelta(days=1)
            return periods

        count = self.prepaid_installment_count
        total_days = (end - start).days + 1
        if count > total_days:
            raise ValidationError(_("The number of custom installments cannot exceed the number of days in the prepaid period."))
        periods = []
        for index in range(count):
            period_start = start + timedelta(days=(total_days * index) // count)
            period_end = start + timedelta(days=(total_days * (index + 1)) // count - 1)
            periods.append((period_start, period_end, self._prepaid_due_date(period_end)))
        return periods

    def _prepaid_amounts(self, total, currency):
        self.ensure_one()
        periods = self._prepaid_periods()
        if not periods:
            return []
        if self.prepaid_distribution_method == "daily":
            total_days = sum((end - start).days + 1 for start, end, _due in periods)
            raw = [total * (((end - start).days + 1) / total_days) for start, end, _due in periods]
        else:
            raw = [total / len(periods)] * len(periods)
        amounts = []
        allocated = 0.0
        for index, amount in enumerate(raw):
            rounded = currency.round(amount) if index < len(raw) - 1 else currency.round(total - allocated)
            amounts.append(rounded)
            allocated += rounded
        if amounts:
            amounts[-1] = currency.round(amounts[-1] + (total - sum(amounts)))
        return amounts

    def _prepaid_dynamic_analytic_values(self):
        """Copy safe custom analytic dimensions when the same field exists on generated move lines."""
        self.ensure_one()
        values = {"analytic_distribution": self.analytic_distribution or False}
        for name, field in self._fields.items():
            if name in values or not field.store or field.compute or field.related or field.readonly:
                continue
            if not ("analytic" in name or name in ("branch_id", "project_id")):
                continue
            if name not in self.env["account.move.line"]._fields:
                continue
            value = self[name]
            if field.type == "many2one":
                values[name] = value.id or False
            elif field.type in ("char", "selection", "integer", "float", "boolean", "json"):
                values[name] = value
        return values

    def _prepaid_posted_totals(self):
        """Return the full prepaid-account valuation, including Odoo 19 discount allocation lines."""
        self.ensure_one()
        company_amount = abs(self.balance)
        currency_amount = abs(self.amount_currency)
        allocation_account = self.move_id._get_discount_allocation_account()
        if self.discount and allocation_account and self.account_id != allocation_account:
            discount_currency = self.currency_id.round(
                abs(self.quantity * self.price_unit * self.discount / 100.0)
            )
            discount_company = self.company_currency_id.round(
                discount_currency / self.currency_rate
            )
            company_amount += discount_company
            currency_amount += discount_currency
        return (
            self.company_currency_id.round(company_amount),
            self.currency_id.round(currency_amount),
        )

    def _prepaid_source_totals(self):
        """Return reliable source totals in draft and posted purchase documents."""
        self.ensure_one()
        if self.move_id.state == "posted":
            return self._prepaid_posted_totals()
        currency_amount = self.currency_id.round(abs(self.price_subtotal))
        company_amount = self.company_currency_id.round(self.currency_id._convert(
            currency_amount,
            self.company_currency_id,
            self.company_id,
            self.move_id.date or fields.Date.context_today(self),
        ))
        return company_amount, currency_amount


class AccountMove(models.Model):
    _inherit = "account.move"

    prepaid_schedule_ids = fields.One2many(
        "prepaid.expense.schedule",
        "move_id",
        string="Prepaid Expense Schedules",
        copy=False,
    )
    prepaid_schedule_count = fields.Integer(
        string="Prepaid Expense Schedule Count",
        compute="_compute_prepaid_schedule_count",
    )
    can_create_prepaid_expense = fields.Boolean(
        compute="_compute_can_create_prepaid_expense",
    )
    is_prepaid_purchase_document = fields.Boolean(
        compute="_compute_is_prepaid_purchase_document",
    )

    @api.depends(
        "prepaid_schedule_ids.line_ids",
        "invoice_line_ids.prepaid_refund_allocation_ids.schedule_line_id",
    )
    def _compute_prepaid_schedule_count(self):
        for move in self:
            refund_schedules = move.invoice_line_ids.prepaid_refund_allocation_ids.schedule_id
            move.prepaid_schedule_count = len(move.prepaid_schedule_ids | refund_schedules)

    @api.depends("move_type")
    def _compute_is_prepaid_purchase_document(self):
        for move in self:
            move.is_prepaid_purchase_document = move._is_prepaid_purchase_document()

    def _is_prepaid_purchase_document(self):
        self.ensure_one()
        return self.is_purchase_document(include_receipts=True) and self.move_type != "in_refund"

    def _prepaid_eligible_source_lines(self):
        self.ensure_one()
        return self.invoice_line_ids.filtered(
            lambda line: (
                line.display_type == "product"
                and not line.prepaid_schedule_id
                and not (self.state == "draft" and line.is_prepaid_expense)
                and line.currency_id.compare_amounts(abs(line.price_subtotal), 0.0) > 0
            )
        )

    @api.depends(
        "move_type", "state", "invoice_line_ids.display_type", "invoice_line_ids.price_subtotal",
        "invoice_line_ids.is_prepaid_expense", "invoice_line_ids.prepaid_schedule_id",
    )
    def _compute_can_create_prepaid_expense(self):
        for move in self:
            move.can_create_prepaid_expense = (
                move._is_prepaid_purchase_document()
                and move.state in ("draft", "posted")
                and bool(move._prepaid_eligible_source_lines())
            )

    def _prepaid_invoice_lines(self):
        return self.invoice_line_ids.filtered(
            lambda line: line.is_prepaid_expense and line.display_type == "product"
        )

    def _prepaid_validate_before_post(self):
        for move in self.filtered(lambda item: item.is_purchase_document(include_receipts=True)):
            lines = move._prepaid_invoice_lines()
            lines._check_prepaid_configuration()
            for line in lines:
                if move.move_type == "in_refund" and not line.prepaid_origin_line_id:
                    raise ValidationError(_("Select the original prepaid expense line on every prepaid vendor credit note line."))
                if line.prepaid_schedule_id and move._is_prepaid_purchase_document():
                    raise ValidationError(_("A prepaid expense schedule already exists for line '%s'.") % line.name)
                if line.account_id != line.prepaid_account_id:
                    line.account_id = line.prepaid_account_id

    def action_post(self):
        self._prepaid_validate_before_post()
        result = super().action_post()
        if isinstance(result, dict):
            return result
        for move in self.filtered(lambda item: item.state == "posted"):
            if move._is_prepaid_purchase_document():
                move._prepaid_create_schedules()
            elif move.move_type == "in_refund":
                move._prepaid_apply_refund()
        return result

    def _post(self, soft=True):
        self._prepaid_validate_before_post()
        posted_moves = super()._post(soft=soft)
        for move in posted_moves:
            if move._is_prepaid_purchase_document():
                move._prepaid_create_schedules()
            elif move.move_type == "in_refund":
                move._prepaid_apply_refund()
        return posted_moves

    def _prepaid_create_schedules(self):
        Schedule = self.env["prepaid.expense.schedule"]
        for move in self:
            for line in move._prepaid_invoice_lines().filtered(lambda item: not item.prepaid_schedule_id):
                _company_total, currency_total = line._prepaid_posted_totals()
                Schedule.create_from_source({
                    "source_type": "vendor_bill",
                    "source": move,
                    "source_line": line,
                    "amount": currency_total,
                    "start_date": line.prepaid_start_date,
                    "end_date": line.prepaid_end_date,
                    "distribution_method": line.prepaid_distribution_method,
                    "installment_count": line.prepaid_installment_count,
                    "actual_account": line.prepaid_actual_account_id,
                    "prepaid_account": line.prepaid_account_id,
                    "analytic_account": move.analytic_account_id,
                    "analytic_distribution": line.analytic_distribution,
                    "name": line.name,
                })

    def _reverse_moves(self, default_values_list=None, cancel=False):
        reverse_moves = super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)
        for original, reverse in zip(self, reverse_moves):
            original_lines = original.invoice_line_ids.filtered(lambda line: line.display_type == "product")
            reverse_lines = reverse.invoice_line_ids.filtered(lambda line: line.display_type == "product")
            for original_line, reverse_line in zip(original_lines, reverse_lines):
                if original_line.is_prepaid_expense:
                    reverse_line.prepaid_origin_line_id = original_line
        return reverse_moves

    def _prepaid_apply_refund(self):
        Allocation = self.env["prepaid.expense.refund.allocation"]
        for refund in self:
            for refund_line in refund._prepaid_invoice_lines():
                if refund_line.prepaid_refund_allocation_ids:
                    continue
                origin_line = refund_line.prepaid_origin_line_id
                schedule = origin_line.prepaid_schedule_id
                if not schedule:
                    raise ValidationError(_("The original prepaid expense line has no schedule."))
                company_refund_balance, refund_currency_amount = refund_line._prepaid_posted_totals()
                available_currency = schedule.original_amount_currency - schedule.refunded_amount_currency
                if float_compare(refund_currency_amount, available_currency, precision_rounding=refund_line.currency_id.rounding) > 0:
                    raise ValidationError(_("The credit note amount exceeds the unrefunded amount of the original prepaid expense."))
                ratio = refund_currency_amount / schedule.original_amount_currency
                refund_original_amount = schedule.company_currency_id.round(schedule.original_amount * ratio)
                to_allocate = refund_original_amount

                future_lines = schedule.line_ids.filtered(
                    lambda item: item.state == "draft" and item.net_amount > 0
                ).sorted(lambda item: (item.due_date, item.sequence), reverse=True)
                for schedule_line in future_lines:
                    if float_is_zero(to_allocate, precision_rounding=schedule.company_currency_id.rounding):
                        break
                    amount = min(to_allocate, schedule_line.net_amount)
                    currency_ratio = amount / schedule_line.net_amount if schedule_line.net_amount else 0.0
                    amount_currency = refund_line.currency_id.round(schedule_line.net_amount_currency * currency_ratio)
                    Allocation.create({
                        "refund_line_id": refund_line.id,
                        "schedule_line_id": schedule_line.id,
                        "schedule_id": schedule.id,
                        "kind": "future",
                        "amount": amount,
                        "amount_currency": amount_currency,
                    })
                    schedule_line._sync_draft_move()
                    to_allocate = schedule.company_currency_id.round(to_allocate - amount)

                if not float_is_zero(to_allocate, precision_rounding=schedule.company_currency_id.rounding):
                    Allocation.create({
                        "refund_line_id": refund_line.id,
                        "schedule_id": schedule.id,
                        "kind": "recognized",
                        "amount": to_allocate,
                        "amount_currency": refund_line.currency_id.round(refund_currency_amount * (to_allocate / refund_original_amount)),
                    })

                refund_line._prepaid_create_refund_adjustment(
                    recognized_amount=to_allocate,
                    refund_original_amount=refund_original_amount,
                    company_refund_balance=company_refund_balance,
                )
                schedule._check_totals(after_refund=True)

    def _prepaid_prepare_reset(self):
        for move in self:
            posted_schedule_moves = move.prepaid_schedule_ids.line_ids.accrual_move_id.filtered(
                lambda item: item.state == "posted"
            )
            allocations = move.invoice_line_ids.prepaid_refund_allocation_ids
            posted_adjustments = allocations.adjustment_move_id.filtered(lambda item: item.state == "posted")
            posted_reclassifications = move.prepaid_schedule_ids.reclassification_move_id.filtered(
                lambda item: item.state == "posted"
            )
            if posted_schedule_moves or posted_adjustments or posted_reclassifications:
                raise UserError(_(
                    "You cannot reset or cancel this document because prepaid expense entries have already been posted. "
                    "Create an explicit reversing journal entry or credit note instead."
                ))

            if allocations:
                affected_lines = allocations.schedule_line_id
                allocations.unlink()
                affected_lines._sync_draft_move()

            schedules = move.prepaid_schedule_ids
            if schedules:
                draft_moves = schedules.line_ids.accrual_move_id.filtered(lambda item: item.state == "draft")
                schedules.line_ids.accrual_move_id = False
                draft_moves.with_context(force_delete=True).unlink()
                move.invoice_line_ids.prepaid_schedule_id = False
                schedules.unlink()

    def button_draft(self):
        self._prepaid_prepare_reset()
        return super().button_draft()

    def button_cancel(self):
        self._prepaid_prepare_reset()
        return super().button_cancel()

    def action_open_prepaid_schedule(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "hosny_prepaid_expenses.action_prepaid_expense_report"
        )
        schedule_ids = (self.prepaid_schedule_ids | self.invoice_line_ids.prepaid_refund_allocation_ids.schedule_id).ids
        action["domain"] = [("id", "in", schedule_ids)]
        action["context"] = {}
        return action

    def action_create_prepaid_expense(self):
        self.ensure_one()
        if not self.can_create_prepaid_expense:
            raise UserError(_("There is no eligible purchase-document line for a new prepaid expense."))
        return {
            "type": "ir.actions.act_window",
            "name": "إنشاء مصروف مقدم",
            "res_model": "prepaid.expense.bill.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
        }

    def action_post_due_prepaid_entries(self):
        schedules = self.prepaid_schedule_ids.line_ids
        if self.move_type == "in_refund":
            schedules |= self.invoice_line_ids.prepaid_refund_allocation_ids.schedule_line_id
        schedules._post_due_entries()
        return True


class AccountMoveLineRefundAdjustment(models.Model):
    _inherit = "account.move.line"

    def _prepaid_create_refund_adjustment(self, recognized_amount, refund_original_amount, company_refund_balance):
        self.ensure_one()
        company = self.company_id
        currency = self.currency_id
        rounding = company.currency_id.rounding
        exchange_difference = company_refund_balance - refund_original_amount
        if float_is_zero(recognized_amount, precision_rounding=rounding) and float_is_zero(
            exchange_difference, precision_rounding=rounding
        ):
            return False

        move_values = {
            "move_type": "entry",
            "date": self.move_id.date,
            "journal_id": self.move_id.journal_id.id,
            "ref": _("Prepaid refund adjustment - %s") % self.move_id.name,
            "company_id": company.id,
        }
        if "analytic_account_id" in self.env["account.move"]._fields:
            move_values["analytic_account_id"] = self.move_id.analytic_account_id.id
        adjustment = self.env["account.move"].with_company(company).create(move_values)
        line_values = []
        analytic_values = self.prepaid_origin_line_id._prepaid_dynamic_analytic_values()

        if not float_is_zero(recognized_amount, precision_rounding=rounding):
            line_values += [
                {
                    "move_id": adjustment.id,
                    "name": _("Reverse recognized prepaid expense"),
                    "account_id": self.prepaid_account_id.id,
                    "debit": recognized_amount,
                    "credit": 0.0,
                    **analytic_values,
                },
                {
                    "move_id": adjustment.id,
                    "name": _("Reverse recognized prepaid expense"),
                    "account_id": self.prepaid_actual_account_id.id,
                    "debit": 0.0,
                    "credit": recognized_amount,
                    **analytic_values,
                },
            ]

        if not float_is_zero(exchange_difference, precision_rounding=rounding):
            if exchange_difference > 0:
                exchange_account = company.income_currency_exchange_account_id
                line_values += [
                    {
                        "move_id": adjustment.id,
                        "name": _("Prepaid expense exchange difference"),
                        "account_id": self.prepaid_account_id.id,
                        "debit": exchange_difference,
                        "credit": 0.0,
                    },
                    {
                        "move_id": adjustment.id,
                        "name": _("Prepaid expense exchange difference"),
                        "account_id": exchange_account.id,
                        "debit": 0.0,
                        "credit": exchange_difference,
                    },
                ]
            else:
                exchange_account = company.expense_currency_exchange_account_id
                difference = abs(exchange_difference)
                line_values += [
                    {
                        "move_id": adjustment.id,
                        "name": _("Prepaid expense exchange difference"),
                        "account_id": exchange_account.id,
                        "debit": difference,
                        "credit": 0.0,
                    },
                    {
                        "move_id": adjustment.id,
                        "name": _("Prepaid expense exchange difference"),
                        "account_id": self.prepaid_account_id.id,
                        "debit": 0.0,
                        "credit": difference,
                    },
                ]
            if not exchange_account:
                raise ValidationError(_("Configure the company's currency exchange gain/loss accounts before posting this credit note."))

        created_lines = self.env["account.move.line"].with_context(check_move_validity=False).create(line_values)
        for line in created_lines:
            if analytic_values.get("analytic_distribution"):
                line.analytic_distribution = analytic_values["analytic_distribution"]
        adjustment.action_post()
        self.prepaid_refund_allocation_ids.write({"adjustment_move_id": adjustment.id})
        return adjustment
