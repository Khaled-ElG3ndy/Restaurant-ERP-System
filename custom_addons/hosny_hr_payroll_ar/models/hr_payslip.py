from calendar import monthrange

from odoo import fields, models, _
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    hosny_adjustment_ids = fields.Many2many(
        "hosny.hr.salary.adjustment",
        "hosny_salary_adjustment_payslip_rel",
        "payslip_id",
        "adjustment_id",
        string="تعديلات الرواتب المحتسبة",
        copy=False,
        readonly=True,
    )
    hosny_work_entry_ids = fields.Many2many(
        "hr.work.entry",
        "hosny_payslip_work_entry_rel",
        "payslip_id",
        "work_entry_id",
        string="قيود العمل المحتسبة",
        copy=False,
        readonly=True,
    )

    def _hosny_get_period_adjustments(self):
        self.ensure_one()
        if not self.contract_id or not self.date_from or not self.date_to:
            return self.env["hosny.hr.salary.adjustment"]

        date_from = fields.Date.to_date(self.date_from)
        date_to = fields.Date.to_date(self.date_to)
        month_start = date_from.replace(day=1)
        month_end = date_from.replace(
            day=monthrange(date_from.year, date_from.month)[1]
        )
        adjustments = self.contract_id.sudo().hosny_salary_adjustment_ids.filtered(
            lambda adjustment: adjustment._is_effective_for_period(
                date_from, date_to
            )
        )
        eligible = self.env["hosny.hr.salary.adjustment"].sudo()
        for adjustment in adjustments:
            used_slips = adjustment.hosny_payslip_ids.filtered(
                lambda slip: slip.id != self.id and slip.state != "cancel"
            )
            if adjustment.recurrence == "once":
                if not used_slips:
                    eligible |= adjustment
                continue
            used_in_month = used_slips.filtered(
                lambda slip: (
                    slip.date_from
                    and slip.date_to
                    and slip.date_from <= month_end
                    and slip.date_to >= month_start
                )
            )
            if not used_in_month:
                eligible |= adjustment
        return eligible

    def _hosny_sync_adjustment_inputs(self):
        self.ensure_one()
        candidates = self.contract_id.sudo().hosny_salary_adjustment_ids.filtered(
            lambda adjustment: adjustment._is_effective_for_period(
                self.date_from, self.date_to
            )
        )
        if candidates:
            self.env.cr.execute(
                """
                    SELECT id
                      FROM hosny_hr_salary_adjustment
                     WHERE id IN %s
                     FOR UPDATE
                """,
                [tuple(candidates.ids)],
            )
            candidates.invalidate_recordset(["hosny_payslip_ids"])

        adjustments = self._hosny_get_period_adjustments()
        self.hosny_adjustment_ids = [fields.Command.set(adjustments.ids)]
        amounts = {
            "HOSNY_ADD": sum(
                adjustments.filtered(
                    lambda adjustment: adjustment.adjustment_type == "addition"
                ).mapped("amount")
            ),
            "HOSNY_DED": sum(
                adjustments.filtered(
                    lambda adjustment: adjustment.adjustment_type == "deduction"
                ).mapped("amount")
            ),
        }
        labels = {
            "HOSNY_ADD": _("إجمالي الإضافات المعتمدة"),
            "HOSNY_DED": _("إجمالي الاستقطاعات المعتمدة"),
        }
        for code, amount in amounts.items():
            matching_lines = self.input_line_ids.filtered(
                lambda line, input_code=code: line.code == input_code
            )
            if matching_lines:
                matching_lines[0].write(
                    {
                        "name": labels[code],
                        "amount": amount,
                        "contract_id": self.contract_id.id,
                    }
                )
                matching_lines[1:].unlink()
            else:
                self.env["hr.payslip.input"].create(
                    {
                        "name": labels[code],
                        "code": code,
                        "amount": amount,
                        "contract_id": self.contract_id.id,
                        "payslip_id": self.id,
                    }
                )

    def _hosny_sync_work_entries(self):
        self.ensure_one()
        worked_day_values = self.get_worked_day_lines(
            self.contract_id, self.date_from, self.date_to
        )
        work_entries = self.env["hr.work.entry"].search(
            [
                ("version_id", "=", self.contract_id.id),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("active", "=", True),
                ("state", "!=", "cancelled"),
            ]
        )
        other_payslips = self.search(
            [
                ("id", "!=", self.id),
                ("state", "!=", "cancel"),
                ("hosny_work_entry_ids", "in", work_entries.ids),
            ],
            limit=1,
        )
        if other_payslips:
            raise UserError(
                _(
                    "توجد قيود عمل للفترة مرتبطة بالفعل بقسيمة راتب أخرى: %(slip)s",
                    slip=other_payslips.display_name,
                )
            )
        self.hosny_work_entry_ids = [fields.Command.set(work_entries.ids)]
        self.worked_days_line_ids = [
            fields.Command.clear(),
            *[
                fields.Command.create(values)
                for values in worked_day_values
            ],
        ]

    def get_inputs(self, contracts, date_from, date_to):
        result = super().get_inputs(contracts, date_from, date_to)
        totals = {"HOSNY_ADD": 0.0, "HOSNY_DED": 0.0}
        for contract in contracts:
            components = contract.sudo()._hosny_get_payroll_components(
                date_from, date_to
            )
            totals["HOSNY_ADD"] += components["additions"]
            totals["HOSNY_DED"] += components["deductions"]
        for values in result:
            if values.get("code") in totals:
                values["amount"] = totals[values["code"]]
        return result

    def compute_sheet(self):
        for payslip in self:
            if not payslip.contract_id:
                contract_ids = payslip.get_contract(
                    payslip.employee_id,
                    payslip.date_from,
                    payslip.date_to,
                )
                if not contract_ids:
                    raise UserError(
                        _("لا يوجد عقد فعال للموظف خلال فترة قسيمة الراتب.")
                    )
                payslip.contract_id = contract_ids[0]
            if not payslip.struct_id:
                payslip.struct_id = payslip.contract_id.struct_id
            if not payslip.struct_id:
                raise UserError(
                    _("حدد هيكل الراتب في نسخة عقد الموظف قبل احتساب القسيمة.")
                )
            payslip._hosny_sync_adjustment_inputs()
            payslip._hosny_sync_work_entries()
        return super().compute_sheet()

    def action_payslip_done(self):
        self.compute_sheet()
        for payslip in self:
            work_entries = payslip.hosny_work_entry_ids.filtered(
                lambda entry: entry.state != "validated"
            )
            if work_entries and not work_entries.action_validate():
                raise UserError(
                    _(
                        "تعذر اعتماد قيود العمل المرتبطة بالقسيمة. "
                        "راجع التعارضات في تطبيق قيود العمل أولًا."
                    )
                )
        return super(
            HrPayslip,
            self.with_context(without_compute_sheet=True),
        ).action_payslip_done()

    def action_payslip_cancel(self):
        result = super().action_payslip_cancel()
        self.write(
            {
                "hosny_adjustment_ids": [fields.Command.clear()],
                "hosny_work_entry_ids": [fields.Command.clear()],
            }
        )
        return result


class HosnyHrSalaryAdjustment(models.Model):
    _inherit = "hosny.hr.salary.adjustment"

    hosny_payslip_ids = fields.Many2many(
        "hr.payslip",
        "hosny_salary_adjustment_payslip_rel",
        "adjustment_id",
        "payslip_id",
        string="قسائم الراتب المحتسبة",
        copy=False,
        readonly=True,
    )
    hosny_payslip_count = fields.Integer(
        string="عدد قسائم الراتب",
        compute="_compute_hosny_payslip_count",
    )

    def _compute_hosny_payslip_count(self):
        for adjustment in self:
            adjustment.hosny_payslip_count = len(
                adjustment.hosny_payslip_ids.filtered(
                    lambda payslip: payslip.state != "cancel"
                )
            )

    def _hosny_check_no_done_payslips(self):
        done_payslips = self.mapped("hosny_payslip_ids").filtered(
            lambda payslip: payslip.state == "done"
        )
        if done_payslips:
            raise UserError(
                _(
                    "لا يمكن تغيير تعديل راتب استُخدم في قسيمة معتمدة: %(slips)s",
                    slips=", ".join(done_payslips.mapped("display_name")),
                )
            )

    def action_cancel(self):
        self._hosny_check_no_done_payslips()
        draft_payslips = self.mapped("hosny_payslip_ids").filtered(
            lambda payslip: payslip.state != "done"
        )
        result = super().action_cancel()
        for payslip in draft_payslips:
            payslip.hosny_adjustment_ids = [
                fields.Command.unlink(adjustment.id)
                for adjustment in self
                if adjustment in payslip.hosny_adjustment_ids
            ]
        return result

    def action_reset_to_draft(self):
        self._hosny_check_no_done_payslips()
        draft_payslips = self.mapped("hosny_payslip_ids").filtered(
            lambda payslip: payslip.state != "done"
        )
        result = super().action_reset_to_draft()
        for payslip in draft_payslips:
            payslip.hosny_adjustment_ids = [
                fields.Command.unlink(adjustment.id)
                for adjustment in self
                if adjustment in payslip.hosny_adjustment_ids
            ]
        return result

    def action_hosny_open_payslips(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("قسائم الراتب المحتسبة"),
            "res_model": "hr.payslip",
            "view_mode": "list,form",
            "domain": [("id", "in", self.hosny_payslip_ids.ids)],
        }
