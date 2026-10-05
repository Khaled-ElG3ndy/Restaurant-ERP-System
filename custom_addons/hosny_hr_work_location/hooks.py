import logging
import re

from odoo import fields

_logger = logging.getLogger(__name__)

_BRANCHES = {
    "jeddah": {
        "name": "Jeddah",
        "arabic_name": "جدة",
        "address_name": "Jeddah Branch",
        "aliases": ("jeddah", "jiddah", "jidda", "jedda", "جدة", "جده"),
    },
    "madinah": {
        "name": "Madinah",
        "arabic_name": "المدينة",
        "address_name": "Madinah Branch",
        "aliases": (
            "madinah",
            "medinah",
            "medina",
            "al madinah",
            "المدينة",
            "المدينه",
            "المدينة المنورة",
        ),
    },
    "riyadh": {
        "name": "Riyadh",
        "arabic_name": "الرياض",
        "address_name": "Riyadh Branch",
        "aliases": ("riyadh", "al riyadh", "الرياض", "رياض"),
    },
}


def _normalized(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[\s_-]+", " ", value)
    return value.replace("ة", "ه")


def _branch_from_text(value):
    normalized = _normalized(value)
    for code, branch in _BRANCHES.items():
        if any(_normalized(alias) in normalized for alias in branch["aliases"]):
            return code
    return False


def _set_xmlid(env, name, record):
    xmlid = env["ir.model.data"].sudo().search(
        [("module", "=", "hosny_hr_work_location"), ("name", "=", name)],
        limit=1,
    )
    values = {
        "model": record._name,
        "res_id": record.id,
        "noupdate": False,
    }
    if xmlid:
        xmlid.write(values)
    else:
        env["ir.model.data"].sudo().create(
            {
                "module": "hosny_hr_work_location",
                "name": name,
                **values,
            }
        )


def pre_init_hook(env):
    """Adopt existing branch records before XML data is loaded.

    This prevents duplicate branch records on the first install.
    Existing contacts are kept and only receive an external ID.
    """
    company = env.ref("base.main_company")
    WorkLocation = env["hr.work.location"].sudo().with_company(company)
    Partner = env["res.partner"].sudo().with_company(company)

    for code, branch in _BRANCHES.items():
        location = WorkLocation.search([("company_id", "=", company.id)]).filtered(
            lambda item: _branch_from_text(item.name) == code
        )[:1]
        address = location.address_id if location else Partner.browse()
        if not address:
            address = Partner.search(
                [
                    ("company_id", "in", [False, company.id]),
                    ("name", "ilike", branch["name"]),
                ],
                limit=1,
            )
        if not address:
            address = Partner.search(
                [
                    ("company_id", "in", [False, company.id]),
                    ("name", "ilike", branch["arabic_name"]),
                ],
                limit=1,
            )
        if not address:
            address = Partner.create(
                {
                    "name": branch["address_name"],
                    "company_id": company.id,
                    "parent_id": company.partner_id.id,
                    "type": "other",
                }
            )

        _set_xmlid(env, f"work_address_{code}", address)
        if location:
            _set_xmlid(env, f"work_location_{code}", location)
            _logger.info(
                "Adopted existing work location %s (%s) as %s",
                location.display_name,
                location.id,
                code,
            )


def _snapshot_from_version(record, version_field=None, date_field=None):
    version = (
        record[version_field]
        if version_field and version_field in record._fields
        else record.env["hr.version"]
    )
    if version and version.work_location_id:
        return version.work_location_id

    employee = (
        record.employee_id
        if "employee_id" in record._fields
        else record.env["hr.employee"]
    )
    value_date = (
        fields.Date.to_date(record[date_field])
        if date_field and record[date_field]
        else False
    )
    if employee and value_date:
        effective_version = employee._get_version(value_date)
        if effective_version and effective_version.work_location_id:
            return effective_version.work_location_id
    return record.env["hr.work.location"]


def _backfill_historical_snapshots(env):
    """Backfill only when a historical contract/version provides the location."""
    specifications = (
        ("hr.work.entry", "version_id", "date"),
        ("hr.payslip", "contract_id", "date_from"),
        ("hosny.hr.salary.adjustment", "version_id", "date_start"),
        ("hr.leave", None, "request_date_from"),
        ("hr.leave.allocation", None, "date_from"),
    )
    results = {}
    for model_name, version_field, date_field in specifications:
        if model_name not in env:
            continue
        records = env[model_name].sudo().search([("work_location_id", "=", False)])
        updated = 0
        for record in records:
            location = _snapshot_from_version(
                record,
                version_field=version_field,
                date_field=date_field,
            )
            if location:
                record.with_context(
                    hosny_allow_work_location_snapshot=True
                ).write({"work_location_id": location.id})
                updated += 1
        results[model_name] = updated
    return results


def post_init_hook(env):
    companies = env["res.company"].sudo().search([])
    companies._hosny_ensure_employee_work_locations()

    WorkLocation = env["hr.work.location"].sudo()
    MigrationLog = env["hosny.hr.work.location.migration.log"].sudo()
    employees = env["hr.employee"].sudo().with_context(active_test=False).search([])

    for employee in employees:
        old_address = employee.address_id
        if employee.work_location_id:
            state = "already_assigned"
            message = "Employee already had a valid work location; no migration was needed."
            location = employee.work_location_id
        else:
            searchable_text = " ".join(
                filter(
                    None,
                    (
                        old_address.name,
                        old_address.city,
                        old_address.street,
                        old_address.display_name,
                    ),
                )
            )
            branch_code = _branch_from_text(searchable_text)
            location = WorkLocation.search(
                [
                    ("company_id", "=", employee.company_id.id),
                    ("hosny_branch_code", "=", branch_code),
                ],
                limit=1,
            )
            if branch_code and location:
                employee.write({"work_location_id": location.id})
                state = "migrated"
                message = "Mapped from the previous work address/contact by a clear branch name."
            elif old_address:
                state = "unresolved"
                message = (
                    "The previous work address/contact did not identify a known "
                    "branch unambiguously; it was preserved and no location was assigned."
                )
            else:
                state = "no_legacy_value"
                message = "No previous work address/contact was set."

        values = {
            "employee_id": employee.id,
            "company_id": employee.company_id.id,
            "old_address_id": old_address.id,
            "old_value": old_address.display_name,
            "work_location_id": location.id,
            "state": state,
            "message": message,
        }
        existing = MigrationLog.search([("employee_id", "=", employee.id)], limit=1)
        if existing:
            existing.write(values)
        else:
            MigrationLog.create(values)

    backfilled = _backfill_historical_snapshots(env)
    unresolved = MigrationLog.search_count([("state", "=", "unresolved")])
    _logger.info(
        "Employee work-location migration completed: %s unresolved; historical "
        "snapshot backfill=%s",
        unresolved,
        backfilled,
    )
