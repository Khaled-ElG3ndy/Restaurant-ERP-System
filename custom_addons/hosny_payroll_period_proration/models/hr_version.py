from calendar import monthrange
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models


class HrVersion(models.Model):
    _inherit = "hr.version"

    _HOSNY_PRORATED_COMPONENTS = frozenset(
        {"base", "housing", "transport", "other"}
    )

    def _hosny_get_salary_rule_amount(self, component):
        monthly_amount = super()._hosny_get_salary_rule_amount(component)
        payslip_id = self.env.context.get("hosny_proration_payslip_id")
        if component not in self._HOSNY_PRORATED_COMPONENTS or not payslip_id:
            return monthly_amount

        self.ensure_one()
        payslip = self.env["hr.payslip"].browse(payslip_id).exists()
        if not payslip or not payslip.date_from or not payslip.date_to:
            return monthly_amount

        cache = self.env.context.get("hosny_proration_cache")
        cache_key = (self.id, payslip.id)
        if isinstance(cache, dict) and cache_key in cache:
            factor = cache[cache_key]
        else:
            factor = self._hosny_get_payslip_proration_factor(payslip)
            if isinstance(cache, dict):
                cache[cache_key] = factor
        return monthly_amount * factor

    def _hosny_get_payslip_proration_factor(self, payslip):
        self.ensure_one()
        payslip.ensure_one()
        period_start = fields.Date.to_date(payslip.date_from)
        period_end = fields.Date.to_date(payslip.date_to)
        if not period_start or not period_end or period_end < period_start:
            return 1.0

        calendar = self.resource_calendar_id or self.company_id.resource_calendar_id
        work_entries = payslip.hosny_work_entry_ids.filtered(
            lambda entry: entry.version_id == self
        )
        factor = 0.0
        month_start = period_start.replace(day=1)
        while month_start <= period_end:
            month_end = month_start.replace(
                day=monthrange(month_start.year, month_start.month)[1]
            )
            selected_start = max(period_start, month_start)
            selected_end = min(period_end, month_end)
            scheduled_hours = self._hosny_get_month_scheduled_hours(
                calendar, month_start, month_end
            )
            if scheduled_hours > 0.0:
                payable_hours = sum(
                    self._hosny_get_payable_work_entry_hours(entry)
                    for entry in work_entries
                    if selected_start <= entry.date <= selected_end
                )
                factor += min(max(payable_hours / scheduled_hours, 0.0), 1.0)
            else:
                factor += self._hosny_get_calendar_day_factor(
                    selected_start, selected_end, month_start, month_end
                )
            month_start = month_end + timedelta(days=1)
        return factor

    def _hosny_get_month_scheduled_hours(self, calendar, month_start, month_end):
        self.ensure_one()
        if not calendar:
            return 0.0
        timezone = pytz.timezone(
            calendar.tz or self.employee_id.tz or self.env.user.tz or "UTC"
        )
        local_start = timezone.localize(datetime.combine(month_start, time.min))
        local_end = timezone.localize(
            datetime.combine(month_end + timedelta(days=1), time.min)
        )
        return calendar.get_work_hours_count(
            local_start.astimezone(pytz.utc),
            local_end.astimezone(pytz.utc),
            compute_leaves=False,
        )

    def _hosny_get_payable_work_entry_hours(self, work_entry):
        self.ensure_one()
        work_entry_type = work_entry.work_entry_type_id
        code = (work_entry_type.code or "").upper()
        if (
            code == "OUT"
            or "OVERTIME" in code
            or work_entry_type.is_extra_hours
        ):
            return 0.0

        leave = work_entry.leave_id
        if leave and leave.holiday_status_id.unpaid:
            return 0.0

        rate = work_entry.amount_rate
        return work_entry.duration * min(max(rate, 0.0), 1.0)

    def _hosny_get_calendar_day_factor(
        self, selected_start, selected_end, month_start, month_end
    ):
        self.ensure_one()
        active_start = max(selected_start, self.date_start or selected_start)
        active_end = min(selected_end, self.date_end or selected_end)
        if active_end < active_start:
            return 0.0
        active_days = (active_end - active_start).days + 1
        month_days = (month_end - month_start).days + 1
        return active_days / month_days

