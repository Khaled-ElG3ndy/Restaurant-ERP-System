import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    # كود قاعدة الراتب -> (كود الحساب المدين، كود الحساب الدائن)
    # يُطبَّق أولًا وله الأولوية على التعيين حسب التصنيف.
    HOSNY_RULE_ACCOUNT_MAP = {
        "NET": (False, "210006"),
        "HOSNY_INS_EMP": ("210016", False),
        "HOSNY_INS_COMP": ("350001", "210016"),
    }

    # كود تصنيف قاعدة الراتب -> (كود الحساب المدين، كود الحساب الدائن)
    # يُستخدم كتعيين افتراضي لأي قاعدة لم تَرِد في الخريطة أعلاه، بما في ذلك
    # القواعد التي ينشئها المستخدم لاحقًا.
    # تصنيف GROSS مستبعد عمدًا لأنه مجموع وسيط وترحيله يُكرِّر المبالغ.
    HOSNY_CATEGORY_ACCOUNT_MAP = {
        # الأغلبية عمّال تشغيل، والأقسام الإدارية تُستثنى بحساب مصروف على
        # مستوى القسم (hr.department.hosny_payroll_expense_account_id).
        "BASIC": ("320033", False),
        "ALW": ("330001", False),
        "ADD": ("330026", False),
        "DED": ("141501", False),
        "NET": (False, "210006"),
        "COMP": ("350001", "210016"),
    }

    hosny_payroll_journal_id = fields.Many2one(
        "account.journal",
        string="يومية الرواتب",
        check_company=True,
        domain="[('type', '=', 'general')]",
        help="اليومية الافتراضية التي تُرحَّل إليها قيود قسائم الرواتب.",
    )
    hosny_payroll_analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="الحساب التحليلي الافتراضي للرواتب",
        check_company=True,
        help=(
            "يُستخدم في قيد الراتب عندما لا يكون لموقع عمل الموظف حساب تحليلي "
            "محدد. الحساب التحليلي إلزامي على قيود اليومية في هذا النظام."
        ),
    )

    @staticmethod
    def _hosny_normalize_arabic(value):
        """توحيد صور الحروف العربية لمطابقة الأسماء مطابقةً متساهلة."""
        if not value:
            return ""
        replacements = {
            "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي",
        }
        text = value.strip()
        for source, target in replacements.items():
            text = text.replace(source, target)
        return " ".join(text.split())

    def _hosny_map_work_location_analytic_accounts(self, force=False):
        """ربط مواقع العمل بالحسابات التحليلية بمطابقة الاسم.

        المطابقة متساهلة تجاه اختلاف صور الحروف العربية (المدينة/المدينه).
        تُسجَّل كل عملية ربط في السجل لمراجعتها، ولا يُستبدل أي ربط قائم
        إلا عند تمرير ``force``.
        """
        self.ensure_one()
        locations = self.env["hr.work.location"].search([("company_id", "=", self.id)])
        analytic_accounts = self.env["account.analytic.account"].search([
            ("company_id", "in", [False, self.id]),
        ])
        if not locations or not analytic_accounts:
            return

        # الأسماء مترجمة: نجمع كل صور الاسم بكل اللغات المثبّتة، لأن اسم موقع
        # العمل قد يكون إنجليزيًا بينما اسم الحساب التحليلي عربي.
        lang_codes = [code for code, _name in self.env["res.lang"].get_installed()]
        lang_codes = lang_codes or [self.env.lang or "en_US"]

        def name_variants(record):
            values = set()
            for lang in lang_codes:
                value = record.with_context(lang=lang).name
                normalized = self._hosny_normalize_arabic(value)
                if len(normalized) >= 3:
                    values.add(normalized)
            return values

        analytic_variants = {
            account: name_variants(account) for account in analytic_accounts
        }

        for location in locations:
            if location.hosny_analytic_account_id and not force:
                continue
            needles = name_variants(location)
            if not needles:
                continue
            match = analytic_accounts.filtered(
                lambda account: any(
                    needle in variant
                    for needle in needles
                    for variant in analytic_variants[account]
                )
            )
            if len(match) == 1:
                location.hosny_analytic_account_id = match
                _logger.info(
                    "hosny_payroll_account: رُبط موقع العمل «%s» بالحساب التحليلي «%s»",
                    location.name, match.name,
                )
            elif len(match) > 1:
                _logger.warning(
                    "hosny_payroll_account: موقع العمل «%s» طابق أكثر من حساب تحليلي، "
                    "يلزم تحديده يدويًا",
                    location.name,
                )

    def _hosny_find_account(self, code):
        """إرجاع حساب الشركة بالكود المحدد، أو سجل فارغ إن لم يوجد."""
        self.ensure_one()
        if not code:
            return self.env["account.account"]
        return self.env["account.account"].with_company(self).search(
            [("code", "=", code)],
            limit=1,
        )

    def _hosny_get_or_create_payroll_journal(self):
        """إرجاع يومية الرواتب، وإنشاؤها إن لم تكن موجودة."""
        self.ensure_one()
        if self.hosny_payroll_journal_id:
            return self.hosny_payroll_journal_id

        journal = self.env["account.journal"].search(
            [("company_id", "=", self.id), ("type", "=", "general"), ("code", "=", "PAY")],
            limit=1,
        )
        if not journal:
            journal = self.env["account.journal"].create({
                "name": _("الرواتب"),
                "code": "PAY",
                "type": "general",
                "company_id": self.id,
            })
        self.hosny_payroll_journal_id = journal
        return journal

    def _hosny_setup_payroll_accounting(self, force=False):
        """تهيئة يومية الرواتب وتعيين الحسابات الافتراضية لقواعد الراتب.

        لا تُستبدل أي حسابات معيَّنة مسبقًا إلا عند تمرير ``force``، حتى لا
        تُفقد تعديلات المستخدم عند ترقية الوحدة.
        """
        for company in self:
            company._hosny_get_or_create_payroll_journal()
            company._hosny_map_work_location_analytic_accounts(force=force)

            rules = self.env["hr.salary.rule"].with_context(active_test=False).search([
                ("company_id", "in", [False, company.id]),
            ])
            for rule in rules:
                category_code = rule.category_id.code
                mapping = company.HOSNY_RULE_ACCOUNT_MAP.get(rule.code)
                if mapping is None:
                    mapping = company.HOSNY_CATEGORY_ACCOUNT_MAP.get(category_code)
                if mapping is None:
                    continue

                debit_code, credit_code = mapping
                values = {}
                if debit_code and (force or not rule.account_debit):
                    account = company._hosny_find_account(debit_code)
                    if account:
                        values["account_debit"] = account.id
                    else:
                        _logger.warning(
                            "hosny_payroll_account: لم يُعثر على الحساب %s للشركة %s",
                            debit_code, company.display_name,
                        )
                if credit_code and (force or not rule.account_credit):
                    account = company._hosny_find_account(credit_code)
                    if account:
                        values["account_credit"] = account.id
                    else:
                        _logger.warning(
                            "hosny_payroll_account: لم يُعثر على الحساب %s للشركة %s",
                            credit_code, company.display_name,
                        )
                if values:
                    rule.write(values)
        return True


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hosny_payroll_journal_id = fields.Many2one(
        related="company_id.hosny_payroll_journal_id",
        readonly=False,
    )
    hosny_payroll_analytic_account_id = fields.Many2one(
        related="company_id.hosny_payroll_analytic_account_id",
        readonly=False,
    )
