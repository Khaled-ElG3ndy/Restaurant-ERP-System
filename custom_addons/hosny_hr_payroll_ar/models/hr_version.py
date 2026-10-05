from calendar import monthrange

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


class HrVersion(models.Model):
    _inherit = "hr.version"

    def _default_hosny_salary_structure(self):
        return self.env.ref(
            "hosny_hr_payroll_ar.hosny_payroll_structure_ar",
            raise_if_not_found=False,
        )

    def _default_hosny_annual_leave_type(self):
        return self.env["hr.leave.type"].search(
            [
                ("company_id", "in", [False, self.env.company.id]),
                ("requires_allocation", "=", True),
                ("unpaid", "=", False),
                ("request_unit", "in", ["day", "half_day"]),
            ],
            limit=1,
        )

    struct_id = fields.Many2one(
        "hr.payroll.structure",
        string="هيكل الراتب",
        default=_default_hosny_salary_structure,
        tracking=True,
        groups="hr.group_hr_manager,bi_hr_payroll.group_hr_payroll_user",
    )
    hosny_wage_type = fields.Selection(
        [
            ("fixed", "أجر ثابت"),
            ("hourly", "أجر بالساعة"),
        ],
        string="نوع الأجر",
        required=True,
        default="fixed",
        tracking=True,
        groups="hr.group_hr_manager",
    )
    hosny_payroll_reference = fields.Char(
        string="المرجع",
        tracking=True,
        groups="hr.group_hr_manager",
        help="مرجع داخلي للربط والمراجعة في ملفات الرواتب.",
    )
    hosny_housing_allowance = fields.Monetary(
        string="بدل السكن",
        currency_field="currency_id",
        tracking=True,
        groups="hr.group_hr_manager",
    )
    hosny_transport_allowance = fields.Monetary(
        string="بدل النقل",
        currency_field="currency_id",
        tracking=True,
        groups="hr.group_hr_manager",
    )
    hosny_other_allowance = fields.Monetary(
        string="بدلات أخرى",
        currency_field="currency_id",
        tracking=True,
        groups="hr.group_hr_manager",
    )
    hosny_total_allowances = fields.Monetary(
        string="إجمالي البدلات",
        compute="_compute_hosny_salary_totals",
        store=True,
        currency_field="currency_id",
        groups="hr.group_hr_manager",
    )
    hosny_estimated_monthly_wage = fields.Monetary(
        string="الراتب الأساسي",
        compute="_compute_hosny_salary_totals",
        store=True,
        currency_field="currency_id",
        groups="hr.group_hr_manager",
        help="للأجر بالساعة: الأجر × ساعات الأسبوع × 52 ÷ 12.",
    )
    hosny_total_fixed_compensation = fields.Monetary(
        string="إجمالي التعويض الشهري الثابت",
        compute="_compute_hosny_salary_totals",
        store=True,
        currency_field="currency_id",
        groups="hr.group_hr_manager",
        help="الأجر الأساسي الشهري المحتسب مضافًا إليه البدلات الشهرية.",
    )
    hosny_social_insurance_reference = fields.Monetary(
        string="الأجر الخاضع للتأمينات الاجتماعية",
        currency_field="currency_id",
        tracking=True,
        groups="hr.group_hr_manager",
        help="القيمة المرجعية التي تستخدمها قواعد التأمينات في احتساب الاشتراك.",
    )
    hosny_annual_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="نوع الإجازة السنوية",
        default=_default_hosny_annual_leave_type,
        tracking=True,
        groups="hr.group_hr_manager",
        domain=(
            "[('company_id', 'in', [False, company_id]), "
            "('requires_allocation', '=', True), "
            "('unpaid', '=', False), "
            "('request_unit', 'in', ['day', 'half_day'])]"
        ),
    )
    hosny_annual_leave_days = fields.Float(
        string="عدد أيام الإجازة السنوية",
        default=21.0,
        tracking=True,
        groups="hr.group_hr_manager",
        help="الاستحقاق المطلوب لهذه النسخة من العقد. استخدم زر التخصيص لمزامنته مع تطبيق الإجازات.",
    )
    hosny_annual_leave_allocation_ids = fields.One2many(
        "hr.leave.allocation",
        "hosny_contract_version_id",
        string="تخصيصات الإجازة السنوية",
        groups="hr.group_hr_manager",
    )
    hosny_allocated_annual_leave_days = fields.Float(
        string="الأيام المعتمدة",
        compute="_compute_hosny_leave_totals",
        groups="hr.group_hr_manager",
    )
    hosny_pending_annual_leave_days = fields.Float(
        string="الأيام قيد الاعتماد",
        compute="_compute_hosny_leave_totals",
        groups="hr.group_hr_manager",
    )
    hosny_remaining_annual_leave_days = fields.Float(
        string="الرصيد المتبقي",
        compute="_compute_hosny_leave_totals",
        groups="hr.group_hr_manager",
    )
    hosny_salary_adjustment_ids = fields.One2many(
        "hosny.hr.salary.adjustment",
        "version_id",
        string="تعديلات الرواتب",
        groups="hr.group_hr_manager",
    )
    hosny_current_additions = fields.Monetary(
        string="إجمالي الإضافات المعتمدة",
        compute="_compute_hosny_current_adjustments",
        currency_field="currency_id",
        groups="hr.group_hr_manager",
    )
    hosny_current_deductions = fields.Monetary(
        string="إجمالي الاستقطاعات المعتمدة",
        compute="_compute_hosny_current_adjustments",
        currency_field="currency_id",
        groups="hr.group_hr_manager",
    )
    hosny_current_net_compensation = fields.Monetary(
        string="صافي الراتب قبل الضرائب والتأمينات",
        compute="_compute_hosny_current_adjustments",
        currency_field="currency_id",
        groups="hr.group_hr_manager",
    )

    @api.depends(
        "wage",
        "hosny_wage_type",
        "resource_calendar_id.hours_per_week",
        "hosny_housing_allowance",
        "hosny_transport_allowance",
        "hosny_other_allowance",
    )
    def _compute_hosny_salary_totals(self):
        for version in self:
            allowances = (
                version.hosny_housing_allowance
                + version.hosny_transport_allowance
                + version.hosny_other_allowance
            )
            if version.hosny_wage_type == "hourly":
                weekly_hours = version.resource_calendar_id.hours_per_week or 0.0
                monthly_wage = version.wage * weekly_hours * 52.0 / 12.0
            else:
                monthly_wage = version.wage
            version.hosny_total_allowances = allowances
            version.hosny_estimated_monthly_wage = monthly_wage
            version.hosny_total_fixed_compensation = monthly_wage + allowances

    @api.depends(
        "hosny_annual_leave_type_id",
        "hosny_annual_leave_allocation_ids.holiday_status_id",
        "hosny_annual_leave_allocation_ids.state",
        "hosny_annual_leave_allocation_ids.number_of_days",
        "hosny_annual_leave_allocation_ids.virtual_remaining_leaves",
    )
    def _compute_hosny_leave_totals(self):
        for version in self:
            allocations = version.hosny_annual_leave_allocation_ids.filtered(
                lambda allocation: (
                    allocation.holiday_status_id == version.hosny_annual_leave_type_id
                    and allocation.state != "refuse"
                )
            )
            approved = allocations.filtered(lambda allocation: allocation.state == "validate")
            pending = allocations - approved
            version.hosny_allocated_annual_leave_days = sum(
                approved.mapped("number_of_days")
            )
            version.hosny_pending_annual_leave_days = sum(
                pending.mapped("number_of_days")
            )
            version.hosny_remaining_annual_leave_days = sum(
                approved.mapped("virtual_remaining_leaves")
            )

    @api.depends(
        "hosny_total_fixed_compensation",
        "hosny_salary_adjustment_ids.state",
        "hosny_salary_adjustment_ids.adjustment_type",
        "hosny_salary_adjustment_ids.amount",
        "hosny_salary_adjustment_ids.recurrence",
        "hosny_salary_adjustment_ids.date_start",
        "hosny_salary_adjustment_ids.date_end",
    )
    def _compute_hosny_current_adjustments(self):
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)
        month_end = today.replace(day=monthrange(today.year, today.month)[1])
        for version in self:
            components = version._hosny_get_payroll_components(
                month_start, month_end
            )
            version.hosny_current_additions = components["additions"]
            version.hosny_current_deductions = components["deductions"]
            version.hosny_current_net_compensation = components[
                "net_before_tax_and_insurance"
            ]

    @api.constrains(
        "wage",
        "hosny_housing_allowance",
        "hosny_transport_allowance",
        "hosny_other_allowance",
        "hosny_social_insurance_reference",
        "hosny_annual_leave_days",
    )
    def _check_hosny_non_negative_values(self):
        field_labels = {
            "wage": _("الأجر"),
            "hosny_housing_allowance": _("بدل السكن"),
            "hosny_transport_allowance": _("بدل النقل"),
            "hosny_other_allowance": _("البدلات الأخرى"),
            "hosny_social_insurance_reference": _(
                "الأجر الخاضع للتأمينات الاجتماعية"
            ),
            "hosny_annual_leave_days": _("عدد أيام الإجازة السنوية"),
        }
        for version in self:
            for field_name, label in field_labels.items():
                if version[field_name] < 0:
                    raise ValidationError(
                        _("%(field)s لا يمكن أن يكون أقل من صفر.", field=label)
                    )
            if (
                version.hosny_social_insurance_reference
                and float_compare(
                    version.hosny_social_insurance_reference,
                    version.hosny_total_fixed_compensation,
                    precision_rounding=version.currency_id.rounding,
                )
                > 0
            ):
                raise ValidationError(
                    _(
                        "الأجر الخاضع للتأمينات لا يمكن أن يتجاوز إجمالي التعويض الشهري الثابت."
                    )
                )

    @api.model
    def _get_whitelist_fields_from_template(self):
        return super()._get_whitelist_fields_from_template() + [
            "hosny_wage_type",
            "hosny_payroll_reference",
            "hosny_housing_allowance",
            "hosny_transport_allowance",
            "hosny_other_allowance",
            "hosny_social_insurance_reference",
            "hosny_annual_leave_type_id",
            "hosny_annual_leave_days",
        ]

    @api.model_create_multi
    def create(self, vals_list):
        template_default_fields = [
            "hosny_wage_type",
            "hosny_annual_leave_type_id",
            "hosny_annual_leave_days",
            "struct_id",
        ]
        defaults = self.default_get(template_default_fields)
        for values in vals_list:
            if not values.get("contract_template_id"):
                continue
            for field_name in template_default_fields:
                if (
                    field_name in values
                    and field_name in defaults
                    and values[field_name] == defaults[field_name]
                ):
                    values.pop(field_name)
        return super().create(vals_list)

    def _hosny_get_payroll_components(self, date_from=None, date_to=None):
        self.ensure_one()
        date_from = fields.Date.to_date(date_from) or fields.Date.context_today(self)
        date_to = fields.Date.to_date(date_to) or date_from
        effective_adjustments = self.hosny_salary_adjustment_ids.filtered(
            lambda adjustment: adjustment._is_effective_for_period(
                date_from, date_to
            )
        )
        additions = sum(
            effective_adjustments.filtered(
                lambda adjustment: adjustment.adjustment_type == "addition"
            ).mapped("amount")
        )
        deductions = sum(
            effective_adjustments.filtered(
                lambda adjustment: adjustment.adjustment_type == "deduction"
            ).mapped("amount")
        )
        insurance = self._hosny_get_social_insurance_amounts()
        return {
            "base_wage": self.hosny_estimated_monthly_wage,
            "housing_allowance": self.hosny_housing_allowance,
            "transport_allowance": self.hosny_transport_allowance,
            "other_allowance": self.hosny_other_allowance,
            "total_allowances": self.hosny_total_allowances,
            "fixed_compensation": self.hosny_total_fixed_compensation,
            "additions": additions,
            "deductions": deductions,
            "social_insurance_reference": self.hosny_social_insurance_reference,
            "social_insurance_base": insurance["base"],
            "employee_social_insurance": insurance["employee"],
            "employer_social_insurance": insurance["employer"],
            "net_before_tax_and_insurance": (
                self.hosny_total_fixed_compensation + additions - deductions
            ),
        }

    def _hosny_get_social_insurance_amounts(self):
        self.ensure_one()
        version = self.sudo()
        company = version.company_id
        result = {"base": 0.0, "employee": 0.0, "employer": 0.0}
        if (
            not company.hosny_social_insurance_enabled
            or not version.hosny_social_insurance_reference
        ):
            return result

        insurance_base = max(
            version.hosny_social_insurance_reference,
            company.hosny_social_insurance_minimum_base,
        )
        if company.hosny_social_insurance_maximum_base:
            insurance_base = min(
                insurance_base,
                company.hosny_social_insurance_maximum_base,
            )
        currency = version.currency_id or company.currency_id
        result["base"] = currency.round(insurance_base)
        result["employee"] = currency.round(
            insurance_base
            * company.hosny_social_insurance_employee_rate
            / 100.0
        )
        result["employer"] = currency.round(
            insurance_base
            * company.hosny_social_insurance_employer_rate
            / 100.0
        )
        return result

    def _hosny_get_salary_rule_amount(self, component):
        self.ensure_one()
        version = self.sudo()
        amounts = {
            "base": version.hosny_estimated_monthly_wage,
            "housing": version.hosny_housing_allowance,
            "transport": version.hosny_transport_allowance,
            "other": version.hosny_other_allowance,
        }
        if component in ("employee_insurance", "employer_insurance"):
            insurance = version._hosny_get_social_insurance_amounts()
            return insurance[
                "employee" if component == "employee_insurance" else "employer"
            ]
        return amounts.get(component, 0.0)

    @api.model
    def _hosny_assign_default_salary_structure(self):
        structure = self.env.ref(
            "hosny_hr_payroll_ar.hosny_payroll_structure_ar",
            raise_if_not_found=False,
        )
        if structure:
            self.search([("struct_id", "=", False)]).write(
                {"struct_id": structure.id}
            )
        return True

    def action_hosny_sync_annual_leave(self):
        self.ensure_one()
        if not self.employee_id:
            raise UserError(
                _("لا يمكن تخصيص إجازة من قالب عقد غير مرتبط بموظف.")
            )
        if not self.hosny_annual_leave_type_id:
            raise UserError(_("اختر نوع الإجازة السنوية أولًا."))
        if not self.hosny_annual_leave_days:
            raise UserError(
                _("أدخل عدد أيام إجازة أكبر من صفر قبل إنشاء التخصيص.")
            )

        active_allocations = self.hosny_annual_leave_allocation_ids.filtered(
            lambda allocation: allocation.state != "refuse"
        )
        if len(active_allocations) > 1:
            raise UserError(
                _(
                    "توجد عدة تخصيصات إجازة نشطة مرتبطة بنسخة العقد. افتح التخصيصات وراجعها قبل المزامنة."
                )
            )

        allocation_values = {
            "name": _("استحقاق الإجازة السنوية - %(employee)s", employee=self.employee_id.name),
            "employee_id": self.employee_id.id,
            "holiday_status_id": self.hosny_annual_leave_type_id.id,
            "allocation_type": "regular",
            "date_from": self.contract_date_start
            or self.date_version
            or fields.Date.context_today(self),
            "date_to": self.contract_date_end or False,
            "number_of_days_display": self.hosny_annual_leave_days,
            "number_of_days": self.hosny_annual_leave_days,
            "hosny_contract_version_id": self.id,
        }
        if active_allocations:
            allocation = active_allocations
            if (
                allocation.holiday_status_id != self.hosny_annual_leave_type_id
                and allocation.leaves_taken
            ):
                raise UserError(
                    _(
                        "لا يمكن تغيير نوع تخصيص استُخدمت منه إجازات. أنشئ تخصيصًا جديدًا من تطبيق الإجازات."
                    )
                )
            allocation.write(allocation_values)
        else:
            allocation = self.env["hr.leave.allocation"].create(allocation_values)

        return {
            "type": "ir.actions.act_window",
            "name": _("تخصيص الإجازة السنوية"),
            "res_model": "hr.leave.allocation",
            "view_mode": "form",
            "res_id": allocation.id,
            "target": "current",
        }

    def action_hosny_open_annual_leave_allocations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("تخصيصات الإجازة السنوية"),
            "res_model": "hr.leave.allocation",
            "view_mode": "list,form",
            "domain": [("hosny_contract_version_id", "=", self.id)],
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_holiday_status_id": self.hosny_annual_leave_type_id.id,
                "default_number_of_days_display": self.hosny_annual_leave_days,
                "default_number_of_days": self.hosny_annual_leave_days,
                "default_hosny_contract_version_id": self.id,
            },
        }

    def action_hosny_open_salary_adjustments(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("تعديلات الرواتب"),
            "res_model": "hosny.hr.salary.adjustment",
            "view_mode": "list,form",
            "domain": [("version_id", "=", self.id)],
            "context": {
                "default_employee_id": self.employee_id.id,
                "default_version_id": self.id,
                "default_company_id": self.company_id.id,
            },
        }


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    struct_id = fields.Many2one(
        related="version_id.struct_id",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager,bi_hr_payroll.group_hr_payroll_user",
    )
    schedule_pay = fields.Selection(
        related="version_id.schedule_pay",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager,bi_hr_payroll.group_hr_payroll_user",
    )
    hosny_wage_type = fields.Selection(
        related="version_id.hosny_wage_type",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_payroll_reference = fields.Char(
        related="version_id.hosny_payroll_reference",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_housing_allowance = fields.Monetary(
        related="version_id.hosny_housing_allowance",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_transport_allowance = fields.Monetary(
        related="version_id.hosny_transport_allowance",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_other_allowance = fields.Monetary(
        related="version_id.hosny_other_allowance",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_total_allowances = fields.Monetary(
        related="version_id.hosny_total_allowances",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_estimated_monthly_wage = fields.Monetary(
        related="version_id.hosny_estimated_monthly_wage",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_total_fixed_compensation = fields.Monetary(
        related="version_id.hosny_total_fixed_compensation",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_social_insurance_reference = fields.Monetary(
        related="version_id.hosny_social_insurance_reference",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_annual_leave_type_id = fields.Many2one(
        related="version_id.hosny_annual_leave_type_id",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_annual_leave_days = fields.Float(
        related="version_id.hosny_annual_leave_days",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_annual_leave_allocation_ids = fields.One2many(
        related="version_id.hosny_annual_leave_allocation_ids",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_allocated_annual_leave_days = fields.Float(
        related="version_id.hosny_allocated_annual_leave_days",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_pending_annual_leave_days = fields.Float(
        related="version_id.hosny_pending_annual_leave_days",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_remaining_annual_leave_days = fields.Float(
        related="version_id.hosny_remaining_annual_leave_days",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_salary_adjustment_ids = fields.One2many(
        related="version_id.hosny_salary_adjustment_ids",
        readonly=False,
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_current_additions = fields.Monetary(
        related="version_id.hosny_current_additions",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_current_deductions = fields.Monetary(
        related="version_id.hosny_current_deductions",
        inherited=True,
        groups="hr.group_hr_manager",
    )
    hosny_current_net_compensation = fields.Monetary(
        related="version_id.hosny_current_net_compensation",
        inherited=True,
        groups="hr.group_hr_manager",
    )

    def action_hosny_sync_annual_leave(self):
        return self.version_id.action_hosny_sync_annual_leave()

    def action_hosny_open_annual_leave_allocations(self):
        return self.version_id.action_hosny_open_annual_leave_allocations()

    def action_hosny_open_salary_adjustments(self):
        return self.version_id.action_hosny_open_salary_adjustments()

    def _hosny_get_payroll_components(self, date_from=None, date_to=None):
        self.ensure_one()
        return self.version_id._hosny_get_payroll_components(date_from, date_to)
