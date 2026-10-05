from collections import defaultdict
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain


TIMELINE_BUS_CHANNEL = "hosny.attendance.timeline"
TIMELINE_BUS_EVENT = "hosny_attendance_timeline/changed"
MAX_TIMELINE_DAYS = 32
MAX_EMPLOYEE_BATCH = 200
WEEK_LOCATION_FIELDS = {
    0: "monday_location_id",
    1: "tuesday_location_id",
    2: "wednesday_location_id",
    3: "thursday_location_id",
    4: "friday_location_id",
    5: "saturday_location_id",
    6: "sunday_location_id",
}


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="employee_id.company_id",
        readonly=True,
    )

    @api.model
    def _timeline_employee_domain(self, attendance_domain):
        employee_model = self.env["hr.employee"]
        direct_mapping = {
            "department_id": "department_id",
            "company_id": "company_id",
            "work_location_id": "work_location_id",
            "manager_id": "parent_id",
            "attendance_manager_id": "attendance_manager_id",
        }
        has_active_filter = False

        def map_condition(condition):
            nonlocal has_active_filter
            field_name = condition.field_expr
            target_name = direct_mapping.get(field_name)
            if field_name == "employee_id":
                if condition.operator in (
                    "like",
                    "ilike",
                    "not like",
                    "not ilike",
                ):
                    target_name = "name"
                else:
                    target_name = "id"
            elif field_name.startswith("employee_id."):
                target_name = field_name.removeprefix("employee_id.")
            if target_name == "active":
                has_active_filter = True
            if target_name not in employee_model._fields:
                target_name = "__timeline_ignored__"
            return Domain(
                target_name, condition.operator, condition.value
            )

        mapped_domain = Domain(attendance_domain).map_conditions(map_condition)

        def filter_domain(domain, ignored):
            if hasattr(domain, "OPERATOR"):
                if domain.OPERATOR in ("&", "|"):
                    domain = domain.apply(
                        filter_domain(child, domain.ZERO)
                        for child in domain.children
                    )
                elif domain.OPERATOR == "!":
                    domain = ~filter_domain(~domain, ~ignored)
            else:
                domain = domain.map_conditions(
                    lambda condition: (
                        condition
                        if condition.field_expr in employee_model._fields
                        else ignored
                    )
                )
            return (
                ignored
                if domain.is_true() or domain.is_false()
                else domain
            )

        employee_domain = filter_domain(
            mapped_domain, ignored=Domain.TRUE
        )
        if not has_active_filter:
            employee_domain &= Domain("active", "=", True)
        allowed_company_ids = self.env.context.get("allowed_company_ids")
        if allowed_company_ids:
            employee_domain &= Domain(
                "company_id", "in", allowed_company_ids
            )
        if not self.env.user.has_group(
            "hr_attendance.group_hr_attendance_user"
        ):
            employee_domain &= Domain(
                "attendance_manager_id", "=", self.env.user.id
            )
        return employee_domain

    @api.model
    def get_timeline_employees(self, domain, focus_date=False):
        if not isinstance(domain, list):
            raise ValidationError(_("The timeline domain must be a list."))

        target_date = fields.Date.to_date(focus_date) or fields.Date.context_today(self)
        employee_model = self.env["hr.employee"]
        employee_domain = self._timeline_employee_domain(domain)
        candidate_fields = [
            "name",
            "department_id",
            "company_id",
            "work_location_id",
            "attendance_manager_id",
            "job_id",
            "barcode",
            "identification_id",
            "employee_code",
            "code",
            "attendance_state",
            "last_check_in",
            "last_check_out",
            "hours_today",
            "resource_calendar_id",
            "tz",
            "color",
            *WEEK_LOCATION_FIELDS.values(),
        ]
        readable_fields = set(
            employee_model.fields_get(candidate_fields)
        )
        employees = (
            employee_model
            .with_context(active_test=False)
            .search_fetch(
                employee_domain,
                [
                    field_name
                    for field_name in candidate_fields
                    if field_name in readable_fields
                ],
                order="name, id",
            )
        )
        status_by_employee = self._timeline_employee_statuses(
            employees, readable_fields, target_date
        )
        employee_code_field = next(
            (
                field_name
                for field_name in (
                    "employee_code",
                    "code",
                    "identification_id",
                )
                if field_name in readable_fields
            ),
            False,
        )
        attendance_create = self.browse().has_access("create")
        employee_read = employee_model.browse().has_access("read")

        return {
            "employees": [
                {
                    "id": employee.id,
                    "name": employee.name,
                    "department": self._timeline_many2one(
                        employee.department_id
                    ),
                    "company": self._timeline_many2one(
                        employee.company_id
                    ),
                    "work_location": self._timeline_many2one(
                        self._timeline_employee_work_location(
                            employee, target_date, readable_fields
                        )
                    ),
                    "attendance_manager": self._timeline_many2one(
                        employee.attendance_manager_id
                    )
                    if "attendance_manager_id" in readable_fields
                    else False,
                    "job": self._timeline_many2one(employee.job_id)
                    if "job_id" in readable_fields
                    else False,
                    "barcode": employee.barcode
                    if "barcode" in readable_fields
                    else False,
                    "employee_code": employee[employee_code_field]
                    if employee_code_field
                    else False,
                    "color": employee.color,
                    "can_open": employee_read,
                    "can_check_in": (
                        attendance_create
                        and not status_by_employee[employee.id][
                            "has_open_attendance"
                        ]
                    ),
                    **status_by_employee[employee.id],
                }
                for employee in employees
            ],
            "work_location_options": self._timeline_work_location_options(),
            "permissions": {
                "create": attendance_create,
                "write": self.browse().has_access("write"),
                "unlink": self.browse().has_access("unlink"),
                "employee_read": employee_read,
            },
        }

    @api.model
    def _timeline_work_location_options(self):
        WorkLocation = self.env["hr.work.location"].sudo()
        domain = [("active", "=", True)]
        if "hosny_branch_code" in WorkLocation._fields:
            domain.append(("hosny_branch_code", "!=", False))
        options_by_key = {}
        for location in WorkLocation.search(domain, order="name, id"):
            option = self._timeline_many2one(location)
            if option:
                options_by_key.setdefault(option["filter_key"], option)
        branch_order = {
            "branch:jeddah": 0,
            "branch:madinah": 1,
            "branch:riyadh": 2,
        }
        return sorted(
            options_by_key.values(),
            key=lambda option: (
                branch_order.get(option["filter_key"], 99),
                option["name"],
            ),
        )

    @api.model
    def _timeline_employee_work_location(
        self, employee, target_date, readable_fields
    ):
        employee.ensure_one()
        weekday_field = WEEK_LOCATION_FIELDS.get(target_date.weekday())
        if weekday_field in readable_fields and employee[weekday_field]:
            return employee[weekday_field]

        version = employee._get_version(target_date)
        if version and version.work_location_id:
            return version.work_location_id

        if "work_location_id" in readable_fields:
            return employee.work_location_id
        return self.env["hr.work.location"]

    @api.model
    def _timeline_employee_statuses(
        self, employees, readable_fields, target_date
    ):
        if not employees:
            return {}

        now = fields.Datetime.now()
        now_utc = pytz.UTC.localize(now)
        day_bounds = {}
        schedule_groups = {}
        empty_employees = self.env["hr.employee"]
        can_read_calendar = "resource_calendar_id" in readable_fields

        for employee in employees:
            timezone = pytz.timezone(
                employee.tz
                if "tz" in readable_fields and employee.tz
                else self.env.user.tz or "UTC"
            )
            local_now = now_utc.astimezone(timezone)
            local_start = timezone.localize(
                datetime.combine(target_date, time.min)
            )
            local_end = local_start + timedelta(days=1)
            start_utc = local_start.astimezone(pytz.UTC)
            end_utc = local_end.astimezone(pytz.UTC)
            day_bounds[employee.id] = {
                "start": start_utc.replace(tzinfo=None),
                "end": end_utc.replace(tzinfo=None),
                "start_aware": start_utc,
                "end_aware": end_utc,
                "is_current_day": target_date == local_now.date(),
                "is_past_day": target_date < local_now.date(),
            }
            calendar = (
                employee.resource_calendar_id
                if can_read_calendar
                else False
            )
            if calendar:
                key = (calendar, start_utc, end_utc)
                schedule_groups[key] = (
                    schedule_groups.get(key, empty_employees)
                    | employee
                )

        min_start = min(
            bounds["start"] for bounds in day_bounds.values()
        )
        max_end = max(
            bounds["end"] for bounds in day_bounds.values()
        )
        attendances = self.search(
            Domain("employee_id", "in", employees.ids)
            & Domain("check_in", "<", max_end)
            & (
                Domain("check_out", ">", min_start)
                | Domain("check_out", "=", False)
            ),
            order="employee_id, check_in, id",
        )
        attendances_by_employee = defaultdict(
            lambda: self.env["hr.attendance"]
        )
        for attendance in attendances:
            attendances_by_employee[
                attendance.employee_id.id
            ] |= attendance

        last_check_out = {
            employee.id: check_out
            for employee, check_out in self._read_group(
                [
                    ("employee_id", "in", employees.ids),
                    ("check_out", "!=", False),
                ],
                ["employee_id"],
                ["check_out:max"],
            )
        }

        schedule_by_employee = {
            employee.id: {
                "start": False,
                "end": False,
                "hours": 0.0,
            }
            for employee in employees
        }
        for (
            calendar,
            start_aware,
            end_aware,
        ), grouped_employees in schedule_groups.items():
            try:
                intervals_by_resource = (
                    calendar._work_intervals_batch(
                        start_aware,
                        end_aware,
                        resources=grouped_employees.resource_id,
                    )
                )
            except AccessError:
                intervals_by_resource = (
                    calendar._attendance_intervals_batch(
                        start_aware,
                        end_aware,
                        resources=grouped_employees.resource_id,
                    )
                )
            for employee in grouped_employees:
                intervals = list(
                    intervals_by_resource.get(
                        employee.resource_id.id, []
                    )
                )
                if intervals:
                    schedule_by_employee[employee.id] = {
                        "start": intervals[0][0]
                        .astimezone(pytz.UTC)
                        .replace(tzinfo=None),
                        "end": intervals[-1][1]
                        .astimezone(pytz.UTC)
                        .replace(tzinfo=None),
                        "hours": sum(
                            (stop - start).total_seconds()
                            / 3600
                            for start, stop, _meta in intervals
                        ),
                    }

        write_access = self.browse().has_access("write")
        statuses = {}
        for employee in employees:
            bounds = day_bounds[employee.id]
            employee_attendances = attendances_by_employee[
                employee.id
            ]
            today_attendances = employee_attendances.filtered(
                lambda attendance: (
                    attendance.check_in < bounds["end"]
                    and (
                        not attendance.check_out
                        or attendance.check_out > bounds["start"]
                    )
                )
            )
            open_attendance = (
                today_attendances.filtered(
                    lambda attendance: not attendance.check_out
                )[:1]
                if bounds["is_current_day"] or bounds["is_past_day"]
                else self.env["hr.attendance"]
            )
            first_check_in = (
                min(today_attendances.mapped("check_in"))
                if today_attendances
                else False
            )
            schedule = schedule_by_employee[employee.id]
            reference_now = (
                now
                if bounds["is_current_day"]
                else bounds["end"]
                if bounds["is_past_day"]
                else bounds["start"]
            )
            worked_today = (
                employee.hours_today
                if bounds["is_current_day"] and "hours_today" in readable_fields
                else sum(
                    (
                        (
                            min(
                                attendance.check_out or reference_now,
                                bounds["end"],
                            )
                            - max(
                                attendance.check_in,
                                bounds["start"],
                            )
                        ).total_seconds()
                        / 3600
                    )
                    for attendance in today_attendances
                )
            )
            overtime_today = sum(
                attendance.overtime_hours
                for attendance in today_attendances
            )
            has_problem = any(
                attendance.color == 1
                for attendance in today_attendances
            )
            has_missing_checkout = bool(
                open_attendance
                and open_attendance.check_in < bounds["start"]
            )
            is_checked_in = bool(
                open_attendance and not has_problem
            )
            is_late = bool(
                schedule["start"]
                and reference_now > schedule["start"]
                and (
                    not first_check_in
                    or first_check_in > schedule["start"]
                )
            )
            is_incomplete = bool(
                not has_problem
                and not is_checked_in
                and today_attendances
                and schedule["end"]
                and reference_now >= schedule["end"]
                and worked_today + (1 / 60)
                < schedule["hours"]
            )
            if has_problem:
                status = "problem"
            elif is_incomplete:
                status = "incomplete"
            elif is_checked_in:
                status = "working"
            else:
                status = "not_working"

            can_check_out = bool(
                open_attendance
                and write_access
                and open_attendance
                in open_attendance._filtered_access("write")
            )
            statuses[employee.id] = {
                "status": status,
                "is_checked_in": is_checked_in,
                "has_open_attendance": bool(open_attendance),
                "is_late": is_late,
                "has_missing_checkout": has_missing_checkout,
                "has_overtime": overtime_today > 0,
                "has_attendance_today": bool(today_attendances),
                "has_incomplete_attendance": is_incomplete,
                "last_check_in": self._timeline_datetime(
                    employee.last_check_in
                    if "last_check_in" in readable_fields
                    else first_check_in
                ),
                "last_check_out": self._timeline_datetime(
                    last_check_out.get(employee.id)
                ),
                "worked_today": worked_today,
                "overtime_today": overtime_today,
                "expected_hours_today": schedule["hours"],
                "can_check_out": can_check_out,
            }
        return statuses

    @api.model
    def timeline_toggle_employee_attendance(
        self, employee_id, action
    ):
        if (
            type(employee_id) is not int
            or action not in ("check_in", "check_out")
        ):
            raise ValidationError(
                _("The employee attendance action is not valid.")
            )
        employee = self.env["hr.employee"].search(
            self._timeline_employee_domain([])
            & Domain("id", "=", employee_id),
            limit=1,
        )
        if not employee:
            raise AccessError(
                _("You cannot access this employee.")
            )

        open_attendance = self.search(
            [
                ("employee_id", "=", employee.id),
                ("check_out", "=", False),
            ],
            limit=1,
        )
        if action == "check_in":
            if open_attendance:
                raise UserError(
                    _("%s is already checked in.", employee.display_name)
                )
            if not self.browse().has_access("create"):
                raise AccessError(
                    _("You cannot create attendance records.")
                )
        else:
            if not open_attendance:
                raise UserError(
                    _("%s is not currently checked in.", employee.display_name)
                )
            if (
                not self.browse().has_access("write")
                or open_attendance
                not in open_attendance._filtered_access("write")
            ):
                raise AccessError(
                    _("You cannot update this attendance record.")
                )

        attendance = employee._attendance_action_change()
        return {
            "id": attendance.id,
            "employee_id": employee.id,
            "check_in": self._timeline_datetime(
                attendance.check_in
            ),
            "check_out": self._timeline_datetime(
                attendance.check_out
            ),
        }

    @api.model
    def get_timeline_attendances(
        self, domain, range_start, range_end, employee_ids
    ):
        start, end = self._timeline_validate_range(
            range_start, range_end
        )
        if not isinstance(domain, list):
            raise ValidationError(_("The timeline domain must be a list."))
        if (
            not isinstance(employee_ids, list)
            or any(
                not isinstance(employee_id, int)
                for employee_id in employee_ids
            )
        ):
            raise ValidationError(
                _("Timeline employee identifiers must be integers.")
            )
        employee_ids = list(dict.fromkeys(employee_ids))
        if len(employee_ids) > MAX_EMPLOYEE_BATCH:
            raise ValidationError(
                _(
                    "A timeline request cannot load more than %s employees.",
                    MAX_EMPLOYEE_BATCH,
                )
            )

        result = {str(employee_id): [] for employee_id in employee_ids}
        if not employee_ids:
            return result

        range_domain = (
            Domain("employee_id", "in", employee_ids)
            & Domain("check_in", "<", end)
            & (
                Domain("check_out", ">", start)
                | Domain("check_out", "=", False)
            )
        )
        attendances = self.search(
            Domain(domain) & range_domain,
            order="employee_id, check_in, id",
        )
        writable_ids = (
            set(attendances._filtered_access("write").ids)
            if self.browse().has_access("write")
            else set()
        )
        unlinkable_ids = (
            set(attendances._filtered_access("unlink").ids)
            if self.browse().has_access("unlink")
            else set()
        )

        for attendance in attendances:
            raw_end = attendance.check_out or fields.Datetime.now()
            if attendance.color == 1:
                status = "error"
            elif not attendance.check_out:
                status = "active"
            elif attendance.check_in < start or raw_end > end:
                status = "partial"
            else:
                status = "completed"
            historical_work_location = (
                attendance.work_location_id
                if "work_location_id" in attendance._fields
                else False
            )
            work_location = (
                historical_work_location.display_name
                if historical_work_location
                else attendance.in_location
                or attendance.out_location
                or False
            )
            result[str(attendance.employee_id.id)].append(
                {
                    "id": attendance.id,
                    "employee_id": attendance.employee_id.id,
                    "employee_name": attendance.employee_id.display_name,
                    "check_in": fields.Datetime.to_string(
                        attendance.check_in
                    ),
                    "check_out": (
                        fields.Datetime.to_string(attendance.check_out)
                        if attendance.check_out
                        else False
                    ),
                    "worked_hours": attendance.worked_hours,
                    "overtime_hours": attendance.overtime_hours,
                    "work_location": work_location,
                    "status": status,
                    "can_write": attendance.id in writable_ids,
                    "can_unlink": attendance.id in unlinkable_ids,
                }
            )
        return result

    @api.model
    def _timeline_validate_range(self, range_start, range_end):
        start = fields.Datetime.to_datetime(range_start)
        end = fields.Datetime.to_datetime(range_end)
        if not start or not end or end <= start:
            raise ValidationError(
                _("The timeline date range is not valid.")
            )
        if (end - start).total_seconds() > MAX_TIMELINE_DAYS * 86400:
            raise ValidationError(
                _(
                    "The timeline cannot load more than %s days at once.",
                    MAX_TIMELINE_DAYS,
                )
            )
        return start, end

    @api.model
    def _timeline_many2one(self, record):
        if not record:
            return False
        filter_key = str(record.id)
        if (
            "hosny_branch_code" in record._fields
            and record.hosny_branch_code
        ):
            filter_key = f"branch:{record.hosny_branch_code}"
        return {
            "id": record.id,
            "name": record.display_name,
            "filter_key": filter_key,
        }

    @api.model
    def _timeline_datetime(self, value):
        return (
            fields.Datetime.to_string(value)
            if value
            else False
        )

    def _notify_attendance_timeline(self):
        if not self.env.context.get(
            "hosny_attendance_timeline_no_notify"
        ):
            self.env["bus.bus"]._sendone(
                TIMELINE_BUS_CHANNEL,
                TIMELINE_BUS_EVENT,
                {},
            )

    @api.model_create_multi
    def create(self, vals_list):
        attendances = super().create(vals_list)
        attendances._notify_attendance_timeline()
        return attendances

    def write(self, vals):
        result = super().write(vals)
        self._notify_attendance_timeline()
        return result

    def unlink(self):
        result = super().unlink()
        self._notify_attendance_timeline()
        return result
