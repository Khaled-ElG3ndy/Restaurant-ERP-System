from odoo import api, fields, models


def _snapshot_field():
    return fields.Many2one(
        "hr.work.location",
        string="Work Location",
        readonly=True,
        copy=False,
        index=True,
        check_company=True,
        help=(
            "Work location captured from the employee/contract when this record "
            "was created. It does not follow later employee changes."
        ),
    )


def _location_from_values(env, vals, version_field=None, date_field=None):
    if vals.get("work_location_id"):
        return vals["work_location_id"]

    if version_field and vals.get(version_field):
        version = env["hr.version"].sudo().browse(vals[version_field]).exists()
        if version.work_location_id:
            return version.work_location_id.id

    employee = env["hr.employee"].sudo().browse(vals.get("employee_id")).exists()
    if not employee:
        return False

    if date_field and vals.get(date_field):
        value_date = fields.Date.to_date(vals[date_field])
        version = employee._get_version(value_date)
        if version and version.work_location_id:
            return version.work_location_id.id
    return employee.work_location_id.id


def _prepare_snapshots(env, vals_list, version_field=None, date_field=None):
    for vals in vals_list:
        if not env.context.get("hosny_allow_work_location_snapshot"):
            vals.pop("work_location_id", None)
        location_id = _location_from_values(
            env,
            vals,
            version_field=version_field,
            date_field=date_field,
        )
        if location_id:
            vals.setdefault("work_location_id", location_id)


def _protected_snapshot_values(env, vals):
    if (
        "work_location_id" in vals
        and not env.context.get("hosny_allow_work_location_snapshot")
    ):
        vals = {key: value for key, value in vals.items() if key != "work_location_id"}
    return vals


class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"
    _check_company_auto = True

    work_location_id = _snapshot_field()

    @api.model_create_multi
    def create(self, vals_list):
        _prepare_snapshots(
            self.env, vals_list, version_field="version_id", date_field="date"
        )
        return super().create(vals_list)

    def write(self, vals):
        return super().write(_protected_snapshot_values(self.env, vals))

    @api.onchange("employee_id", "version_id", "date")
    def _onchange_hosny_work_location_snapshot(self):
        for record in self:
            record.work_location_id = (
                record.version_id.work_location_id
                or record.employee_id.work_location_id
            )


class HrLeave(models.Model):
    _inherit = "hr.leave"
    _check_company_auto = True

    work_location_id = _snapshot_field()

    @api.model_create_multi
    def create(self, vals_list):
        _prepare_snapshots(self.env, vals_list, date_field="request_date_from")
        return super().create(vals_list)

    def write(self, vals):
        return super().write(_protected_snapshot_values(self.env, vals))

    @api.onchange("employee_id", "request_date_from")
    def _onchange_hosny_work_location_snapshot(self):
        for record in self:
            location_id = _location_from_values(
                self.env,
                {
                    "employee_id": record.employee_id.id,
                    "request_date_from": record.request_date_from,
                },
                date_field="request_date_from",
            )
            record.work_location_id = location_id


class HrLeaveAllocation(models.Model):
    _inherit = "hr.leave.allocation"
    _check_company_auto = True

    work_location_id = _snapshot_field()

    @api.model_create_multi
    def create(self, vals_list):
        _prepare_snapshots(self.env, vals_list, date_field="date_from")
        return super().create(vals_list)

    def write(self, vals):
        return super().write(_protected_snapshot_values(self.env, vals))

    @api.onchange("employee_id", "date_from")
    def _onchange_hosny_work_location_snapshot(self):
        for record in self:
            location_id = _location_from_values(
                self.env,
                {
                    "employee_id": record.employee_id.id,
                    "date_from": record.date_from,
                },
                date_field="date_from",
            )
            record.work_location_id = location_id


class HrPayslip(models.Model):
    _inherit = "hr.payslip"
    _check_company_auto = True

    work_location_id = _snapshot_field()

    @api.model_create_multi
    def create(self, vals_list):
        _prepare_snapshots(
            self.env,
            vals_list,
            version_field="contract_id",
            date_field="date_from",
        )
        return super().create(vals_list)

    def write(self, vals):
        return super().write(_protected_snapshot_values(self.env, vals))

    @api.onchange("employee_id", "contract_id", "date_from")
    def _onchange_hosny_work_location_snapshot(self):
        for record in self:
            location_id = _location_from_values(
                self.env,
                {
                    "employee_id": record.employee_id.id,
                    "contract_id": record.contract_id.id,
                    "date_from": record.date_from,
                },
                version_field="contract_id",
                date_field="date_from",
            )
            record.work_location_id = location_id


class HrPayslipLine(models.Model):
    _inherit = "hr.payslip.line"

    work_location_id = fields.Many2one(
        "hr.work.location",
        related="slip_id.work_location_id",
        string="Work Location",
        store=True,
        readonly=True,
        index=True,
    )


class HosnyHrSalaryAdjustment(models.Model):
    _inherit = "hosny.hr.salary.adjustment"

    work_location_id = _snapshot_field()

    @api.model_create_multi
    def create(self, vals_list):
        _prepare_snapshots(self.env, vals_list, version_field="version_id")
        return super().create(vals_list)

    def write(self, vals):
        return super().write(_protected_snapshot_values(self.env, vals))

    @api.onchange("employee_id", "version_id")
    def _onchange_hosny_work_location_snapshot(self):
        for record in self:
            record.work_location_id = (
                record.version_id.work_location_id
                or record.employee_id.work_location_id
            )
