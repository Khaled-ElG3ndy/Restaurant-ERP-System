from odoo import _, api, fields, models
from odoo.exceptions import UserError

# تصنيفات القواعد التي تمثل مجاميع وسيطة ولا تُرحَّل محاسبيًا،
# لأن مكوناتها مُرحَّلة بالفعل كل على حدة.
HOSNY_SUBTOTAL_CATEGORIES = {"GROSS"}


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    journal_id = fields.Many2one(
        "account.journal",
        string="يومية الرواتب",
        check_company=True,
        domain="[('type', '=', 'general')]",
        copy=False,
        default=lambda self: self.env.company.hosny_payroll_journal_id,
        help="اليومية التي يُرحَّل إليها قيد هذه القسيمة.",
    )
    move_id = fields.Many2one(
        "account.move",
        string="قيد اليومية",
        readonly=True,
        copy=False,
        check_company=True,
        help="القيد المحاسبي الذي أنشأته هذه القسيمة عند الاعتماد.",
    )
    hosny_reversal_move_id = fields.Many2one(
        "account.move",
        string="القيد العكسي",
        readonly=True,
        copy=False,
        check_company=True,
        help="القيد العكسي الذي أُنشئ عند إلغاء القسيمة بعد اعتمادها.",
    )
    hosny_accounting_date = fields.Date(
        string="تاريخ القيد",
        copy=False,
        help="اتركه فارغًا لاستخدام تاريخ نهاية فترة القسيمة.",
    )
    hosny_move_state = fields.Selection(
        related="move_id.state",
        string="حالة القيد",
        readonly=True,
    )
    hosny_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="الحساب التحليلي",
        check_company=True,
        copy=False,
        compute="_compute_hosny_analytic_account_id",
        store=True,
        readonly=False,
        help=(
            "الفرع الذي تُحمَّل عليه تكلفة هذه القسيمة. يُقترح تلقائيًا من موقع "
            "عمل الموظف، ويمكن تعديله قبل الاعتماد."
        ),
    )

    @api.depends("employee_id", "contract_id", "company_id")
    def _compute_hosny_analytic_account_id(self):
        for payslip in self:
            if payslip.hosny_analytic_account_id:
                continue
            payslip.hosny_analytic_account_id = payslip._hosny_default_analytic_account()

    def _hosny_default_analytic_account(self):
        """الحساب التحليلي المقترح: من موقع عمل الموظف، ثم الافتراضي للشركة."""
        self.ensure_one()
        location = self.env["hr.work.location"]
        # يوفر hosny_hr_work_location لقطة لموقع العمل على القسيمة نفسها.
        if "work_location_id" in self._fields:
            location = self.work_location_id
        if not location:
            location = self.contract_id.sudo().work_location_id
        if not location:
            location = self.employee_id.sudo().work_location_id
        return (
            location.sudo().hosny_analytic_account_id
            or self.company_id.hosny_payroll_analytic_account_id
        )

    # ------------------------------------------------------------------
    # مساعدات
    # ------------------------------------------------------------------

    def _hosny_get_accounting_date(self):
        self.ensure_one()
        return self.hosny_accounting_date or self.date_to or fields.Date.context_today(self)

    def _hosny_get_payroll_journal(self):
        self.ensure_one()
        journal = self.journal_id or self.company_id.hosny_payroll_journal_id
        if not journal:
            raise UserError(
                _(
                    "لم تُحدَّد يومية للرواتب. اضبطها من إعدادات المحاسبة أو "
                    "من حقل «يومية الرواتب» في القسيمة."
                )
            )
        return journal

    def _hosny_get_department(self):
        """قسم الموظف المعتمد في القسيمة، من نسخة العقد أولًا ثم من بطاقة الموظف."""
        self.ensure_one()
        return (
            self.contract_id.sudo().department_id
            or self.employee_id.sudo().department_id
        )

    def _hosny_resolve_debit_account(self, rule_account):
        """تطبيق حساب مصروف القسم على البنود ذات الطبيعة المصروفية فقط.

        الحسابات غير المصروفية (الاستقطاعات، التأمينات، المستحق للموظفين)
        تبقى كما عُرِّفت في قاعدة الراتب.
        """
        self.ensure_one()
        if not rule_account or not rule_account.account_type.startswith("expense"):
            return rule_account
        override = self._hosny_get_department().sudo().hosny_payroll_expense_account_id
        if override and override.with_company(self.company_id).code:
            return override
        return rule_account

    def _hosny_prepare_move_line_values(self):
        """بناء قيم بنود القيد من بنود القسيمة.

        الاتفاقية المتبعة (نفس اتفاقية أودو القياسية): القيمة الموجبة تُسجَّل
        في الطرف المحدد، والقيمة السالبة تُقلب تلقائيًا إلى الطرف المقابل.
        بذلك تُسجَّل الاستقطاعات — وقيمتها سالبة — دائنةً في حساباتها.
        """
        self.ensure_one()
        currency = self.company_id.currency_id
        partner = self.employee_id.sudo().work_contact_id
        date = self._hosny_get_accounting_date()

        line_values = []
        unmapped = []
        for line in self.line_ids:
            amount = -line.total if self.credit_note else line.total
            if currency.is_zero(amount):
                continue

            rule = line.salary_rule_id.sudo()
            if rule.category_id.code in HOSNY_SUBTOTAL_CATEGORIES:
                continue

            debit_account = self._hosny_resolve_debit_account(rule.account_debit)
            credit_account = rule.account_credit
            if not debit_account and not credit_account:
                unmapped.append("%s (%s)" % (line.name, line.code))
                continue

            common = {
                "name": line.name,
                "partner_id": partner.id or False,
                "date": date,
            }
            if debit_account:
                line_values.append({
                    **common,
                    "account_id": debit_account.id,
                    "debit": amount if amount > 0.0 else 0.0,
                    "credit": -amount if amount < 0.0 else 0.0,
                })
            if credit_account:
                line_values.append({
                    **common,
                    "account_id": credit_account.id,
                    "debit": -amount if amount < 0.0 else 0.0,
                    "credit": amount if amount > 0.0 else 0.0,
                })

        if unmapped:
            raise UserError(
                _(
                    "لا يمكن ترحيل القسيمة %(slip)s لأن القواعد التالية لها قيمة "
                    "ولم تُحدَّد لها حسابات محاسبية:\n\n%(rules)s\n\n"
                    "افتح إعداد قواعد الراتب وحدِّد الحساب المدين أو الدائن لكل قاعدة.",
                    slip=self.display_name,
                    rules="\n".join("• %s" % name for name in unmapped),
                )
            )
        return line_values

    def _hosny_prepare_move_values(self, line_values):
        self.ensure_one()
        journal = self._hosny_get_payroll_journal()
        values = {
            "move_type": "entry",
            "journal_id": journal.id,
            "company_id": self.company_id.id,
            "date": self._hosny_get_accounting_date(),
            "ref": self.number or self.name,
            "partner_id": self.employee_id.sudo().work_contact_id.id or False,
            "line_ids": [fields.Command.create(values) for values in line_values],
        }
        # الحساب التحليلي إلزامي على قيود اليومية في هذا النظام
        # (hosny_account_analytic_header).
        if "analytic_account_id" in self.env["account.move"]._fields:
            analytic = (
                self.hosny_analytic_account_id
                or self._hosny_default_analytic_account()
            )
            if not analytic:
                raise UserError(
                    _(
                        "لا يمكن ترحيل القسيمة %(slip)s بدون حساب تحليلي. "
                        "حدِّد الحساب التحليلي في القسيمة، أو اربط موقع عمل "
                        "الموظف بحساب تحليلي، أو اضبط الحساب الافتراضي في "
                        "إعدادات الرواتب.",
                        slip=self.display_name,
                    )
                )
            values["analytic_account_id"] = analytic.id
        return values

    # ------------------------------------------------------------------
    # الترحيل والعكس
    # ------------------------------------------------------------------

    def _hosny_create_payslip_move(self):
        """إنشاء وترحيل قيد الراتب. آمنة عند التكرار: لا تُنشئ قيدًا مزدوجًا."""
        for payslip in self:
            if payslip.move_id and not payslip.hosny_reversal_move_id:
                # القسيمة مُرحَّلة بالفعل ولم يُعكس قيدها.
                continue

            line_values = payslip._hosny_prepare_move_line_values()
            if not line_values:
                continue

            currency = payslip.company_id.currency_id
            total_debit = sum(values["debit"] for values in line_values)
            total_credit = sum(values["credit"] for values in line_values)
            if not currency.is_zero(total_debit - total_credit):
                raise UserError(
                    _(
                        "قيد القسيمة %(slip)s غير متوازن: "
                        "إجمالي المدين %(debit)s مقابل إجمالي الدائن %(credit)s.\n\n"
                        "راجع الحسابات المحددة في قواعد الراتب — الغالب أن قاعدة "
                        "تدخل في صافي الراتب لم يُحدَّد لها حساب مصروف.",
                        slip=payslip.display_name,
                        debit=total_debit,
                        credit=total_credit,
                    )
                )

            move = self.env["account.move"].with_company(payslip.company_id).create(
                payslip._hosny_prepare_move_values(line_values)
            )
            move.action_post()
            payslip.write({
                "move_id": move.id,
                "journal_id": move.journal_id.id,
                "hosny_reversal_move_id": False,
            })
        return True

    def _hosny_reverse_payslip_move(self):
        """عكس قيد الراتب المرحَّل مع الإبقاء على القيد الأصلي للمراجعة."""
        for payslip in self:
            move = payslip.move_id
            if not move or payslip.hosny_reversal_move_id:
                continue

            if move.state == "draft":
                move.unlink()
                payslip.move_id = False
                continue

            reversal = move._reverse_moves(default_values_list=[{
                "date": payslip._hosny_get_accounting_date(),
                "ref": _("عكس قيد الراتب %s", payslip.number or payslip.name),
            }])
            reversal.action_post()
            payslip.hosny_reversal_move_id = reversal
        return True

    # ------------------------------------------------------------------
    # ربط دورة حياة القسيمة
    # ------------------------------------------------------------------

    def action_payslip_done(self):
        result = super().action_payslip_done()
        self._hosny_create_payslip_move()
        return result

    def action_payslip_cancel(self):
        done_slips = self.filtered(lambda slip: slip.state == "done")
        done_slips._hosny_reverse_payslip_move()
        # القاعدة الأصلية تمنع إلغاء قسيمة معتمدة. بعد عكس القيد نُرجِع الحالة
        # إلى «قيد الانتظار» لتمر عبر السلسلة الأصلية كاملةً، فيُنفَّذ معها
        # تنظيف تعديلات الرواتب وقيود العمل المعرَّف في hosny_hr_payroll_ar.
        if done_slips:
            done_slips.write({"state": "verify"})
        return super().action_payslip_cancel()

    def action_payslip_draft(self):
        blocked = self.filtered(
            lambda slip: slip.move_id
            and slip.move_id.state == "posted"
            and not slip.hosny_reversal_move_id
        )
        if blocked:
            raise UserError(
                _(
                    "لا يمكن إرجاع القسائم التالية إلى مسودة لوجود قيود محاسبية "
                    "مرحَّلة لها. ألغِ القسيمة أولًا ليُنشأ القيد العكسي:\n\n%(slips)s",
                    slips="\n".join(
                        "• %s" % name for name in blocked.mapped("display_name")
                    ),
                )
            )
        result = super().action_payslip_draft()
        # القيد الأصلي وعكسه يبقيان في اليومية للمراجعة، ويظل الربط بينهما
        # قائمًا عبر reversed_entry_id ومرجع القيد. فك الارتباط هنا يسمح
        # بإنشاء قيد جديد نظيف عند إعادة الاعتماد دون تكرار.
        self.filtered("hosny_reversal_move_id").write({
            "move_id": False,
            "hosny_reversal_move_id": False,
        })
        return result

    def unlink(self):
        moves = self.mapped("move_id") | self.mapped("hosny_reversal_move_id")
        posted = moves.filtered(lambda move: move.state == "posted")
        if posted:
            raise UserError(
                _(
                    "لا يمكن حذف قسيمة لها قيود محاسبية مرحَّلة: %(moves)s",
                    moves=", ".join(posted.mapped("name")),
                )
            )
        return super().unlink()

    # ------------------------------------------------------------------
    # أزرار
    # ------------------------------------------------------------------

    def action_hosny_open_move(self):
        self.ensure_one()
        moves = self.move_id | self.hosny_reversal_move_id
        if not moves:
            raise UserError(_("لا يوجد قيد محاسبي مرتبط بهذه القسيمة."))
        if len(moves) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("قيد الراتب"),
                "res_model": "account.move",
                "view_mode": "form",
                "res_id": moves.id,
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("قيود الراتب"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", moves.ids)],
        }

    @api.onchange("employee_id")
    def _onchange_hosny_payroll_journal(self):
        for payslip in self:
            if not payslip.journal_id:
                payslip.journal_id = payslip.company_id.hosny_payroll_journal_id
