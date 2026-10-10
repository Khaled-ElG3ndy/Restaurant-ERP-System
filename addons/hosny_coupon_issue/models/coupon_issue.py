from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .coupon_code import generate_code

PAYMENT_MODES = [("cash", "نقدي"), ("bank", "بنك"), ("later", "أجل")]


class HosnyCouponIssue(models.Model):
    """إصدار كوبونات خصم مدفوعة لعميل.

    المحاسبة (طلب 2026-10-10):
      • الإصدار: فاتورة عميل — مدين العميل / دائن حساب «كوبونات» (التزام)، بلا ضريبة:
        الضريبة تُحسب كاملة على الأكل وقت الاستخدام (قسيمة متعددة الأغراض).
      • نقدي / بنك: دفعة مسجلة ومطابقة مع الفاتورة — مدين الصندوق أو البنك / دائن العميل.
        أجل: تبقى الفاتورة مفتوحة على حساب العميل.
      • الاستخدام في نقطة البيع: سطر الكوبون بمنتج البرنامج وحسابه «كوبونات» — مدين الالتزام،
        فيُقفل ما سُجل دائناً عند الإصدار.
    """

    _name = "hosny.coupon.issue"
    _description = "إصدار كوبونات الخصم"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="رقم الإصدار", default="/", readonly=True, copy=False, tracking=True)
    state = fields.Selection(
        [("draft", "مسودة"), ("issued", "صادر"), ("cancelled", "ملغي")],
        default="draft", required=True, tracking=True, copy=False, string="الحالة",
    )
    date = fields.Date(string="التاريخ", required=True, default=fields.Date.context_today, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    partner_id = fields.Many2one("res.partner", string="العميل", required=True, tracking=True)
    pos_config_id = fields.Many2one(
        "pos.config", string="الفرع", required=True, tracking=True,
        domain="[('company_id', '=', company_id)]",
        help="الفرع الذي باع الكوبون: منه الحساب التحليلي للفاتورة، وصندوقه أو بنكه للدفعة.",
    )
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="الحساب التحليلي",
        compute="_compute_analytic_account_id", store=True, readonly=False,
    )
    user_id = fields.Many2one("res.users", string="أصدره", default=lambda self: self.env.user, readonly=True)
    program_id = fields.Many2one(
        "loyalty.program", string="البرنامج", required=True,
        default=lambda self: self.env.company.hosny_coupon_program_id,
        domain="[('program_type', '=', 'gift_card')]",
    )
    coupon_value = fields.Monetary(string="قيمة الكوبون", required=True, default=100.0, tracking=True)
    quantity = fields.Integer(string="عدد الكوبونات", required=True, default=1, tracking=True)
    amount_total = fields.Monetary(string="الإجمالي", compute="_compute_amount_total", store=True)
    expiration_date = fields.Date(string="تاريخ الانتهاء", tracking=True, help="فارغ = بدون انتهاء")
    payment_mode = fields.Selection(PAYMENT_MODES, string="طريقة الدفع", required=True, default="cash", tracking=True)
    journal_id = fields.Many2one(
        "account.journal", string="الصندوق / البنك",
        domain="[('company_id', '=', company_id), ('type', 'in', ['cash', 'bank'])]",
        tracking=True,
    )
    note = fields.Text(string="ملاحظات")

    invoice_id = fields.Many2one("account.move", string="الفاتورة", readonly=True, copy=False)
    payment_ids = fields.Many2many("account.payment", string="الدفعات", readonly=True, copy=False)
    payment_state = fields.Selection(related="invoice_id.payment_state", string="حالة السداد")
    card_ids = fields.One2many("loyalty.card", "hosny_issue_id", string="الكوبونات", readonly=True)
    card_count = fields.Integer(compute="_compute_usage")
    used_amount = fields.Monetary(string="المستخدم", compute="_compute_usage")
    remaining_amount = fields.Monetary(string="المتبقي", compute="_compute_usage")

    _check_quantity = models.Constraint("CHECK(quantity > 0 AND quantity <= 1000)", "عدد الكوبونات من 1 إلى 1000.")
    _check_value = models.Constraint("CHECK(coupon_value > 0)", "قيمة الكوبون لازم تكون أكبر من صفر.")

    @api.depends("coupon_value", "quantity")
    def _compute_amount_total(self):
        for issue in self:
            issue.amount_total = issue.currency_id.round((issue.coupon_value or 0.0) * (issue.quantity or 0))

    @api.depends("card_ids.points", "card_ids.hosny_initial_value")
    def _compute_usage(self):
        for issue in self:
            cards = issue.card_ids
            issue.card_count = len(cards)
            issue.remaining_amount = sum(max(c.points, 0.0) for c in cards) if issue.state == "issued" else 0.0
            issue.used_amount = sum(c.hosny_used_value for c in cards)

    @api.depends("pos_config_id")
    def _compute_analytic_account_id(self):
        for issue in self:
            config = issue.pos_config_id
            issue.analytic_account_id = config.analytic_account_id if "analytic_account_id" in config._fields else False

    @api.onchange("payment_mode", "pos_config_id")
    def _onchange_payment_mode(self):
        """صندوق الفرع أو بنكه (من طرق دفع نقطة البيع)."""
        if self.payment_mode == "later":
            self.journal_id = False
            return
        Journal = self.env["account.journal"]
        if self.payment_mode == "cash":
            # نقدية الكوبونات في خزنة الفرع — لا في درج نقطة البيع
            safe = self.pos_config_id.hosny_safe_account_id if "hosny_safe_account_id" in self.pos_config_id._fields else False
            branch_journals = Journal.search(
                [("company_id", "=", self.company_id.id), ("type", "=", "cash"), ("default_account_id", "=", safe.id)], limit=1
            ) if safe else Journal
        else:
            branch_journals = self.pos_config_id.payment_method_ids.journal_id.filtered(lambda j: j.type == "bank")
        if branch_journals:
            self.journal_id = branch_journals[:1]
        elif not self.journal_id or self.journal_id.type != self.payment_mode:
            self.journal_id = self.env["account.journal"].search(
                [("company_id", "=", self.company_id.id), ("type", "=", self.payment_mode)], limit=1
            )

    # ── التحقق ───────────────────────────────────────────────────────────
    def _coupon_product(self):
        self.ensure_one()
        reward = self.program_id.reward_ids.filtered(lambda r: r.reward_type == "discount")[:1]
        return reward.discount_line_product_id

    def _check_setup(self):
        """الإعداد الذي يجعل قيد الإصدار وقيد الاستخدام يقفلان بعضهما."""
        self.ensure_one()
        account = self.company_id.hosny_coupon_account_id
        if not account:
            raise UserError(_("حدد «حساب الكوبونات (التزام)» للشركة أولاً."))
        if self.program_id.program_type != "gift_card":
            raise UserError(_("برنامج الكوبونات لازم يكون من نوع الرصيد (بطاقات هدايا في أودو)."))
        product = self._coupon_product()
        if not product:
            raise UserError(_("برنامج «%s» ليس له منتج خصم.", self.program_id.name))
        income = product.with_company(self.company_id).property_account_income_id
        if income != account:
            raise UserError(_(
                "منتج الكوبون «%(product)s» حساب إيراده «%(income)s» — لازم يكون «%(account)s» "
                "حتى يُقفل استخدام الكوبون في نقطة البيع نفس الالتزام.",
                product=product.display_name, income=income.display_name or "-", account=account.display_name,
            ))
        if product.taxes_id.filtered(lambda t: t.company_id == self.company_id and t.amount):
            raise UserError(_("منتج الكوبون «%s» عليه ضريبة — الضريبة تُحسب عند الاستخدام، فاحذفها من المنتج.", product.display_name))
        if self.payment_mode != "later":
            if not self.journal_id:
                raise UserError(_("اختر الصندوق أو البنك الذي استلم المبلغ."))
            if self.journal_id.type != self.payment_mode:
                raise UserError(_("طريقة الدفع «%s» لا تطابق الدفتر «%s».",
                                  dict(PAYMENT_MODES)[self.payment_mode], self.journal_id.display_name))
            pos_drawers = self.env["pos.payment.method"].sudo().search([("journal_id.type", "=", "cash")]).journal_id
            if self.journal_id in pos_drawers:
                raise UserError(_(
                    "«%s» هو صندوق درج نقطة البيع، ويُعدّ ويُسلَّم مع كل وردية — نقدية الكوبونات تُستلم في خزنة الفرع.",
                    self.journal_id.display_name,
                ))
            line = self.journal_id.inbound_payment_method_line_ids[:1]
            if not line.payment_account_id:
                raise UserError(_(
                    "دفتر «%s» ليس له حساب للمقبوضات في طريقة الدفع «%s» — بدونه لا يُسجَّل قيد الدفعة. "
                    "اضبطه من المحاسبة ← الإعدادات ← الدفاتر.", self.journal_id.display_name, line.name or "-",
                ))

    # ── الإصدار ──────────────────────────────────────────────────────────
    def action_issue(self):
        for issue in self:
            if issue.state != "draft":
                continue
            if not self.env.user.has_group("account.group_account_invoice"):
                raise UserError(_("إصدار الكوبونات ينشئ فاتورة ودفعة — يحتاج صلاحية الفواتير."))
            issue._check_setup()
            if issue.name == "/":
                issue.name = self.env["ir.sequence"].with_company(issue.company_id).next_by_code("hosny.coupon.issue") or "/"
            invoice = issue._create_invoice()
            issue.invoice_id = invoice
            if issue.payment_mode != "later":
                issue.payment_ids = issue._register_payment(invoice)
            issue._create_cards()
            issue.state = "issued"
            issue.message_post(body=_(
                "صدر %(qty)s كوبون × %(value)s — الفاتورة %(invoice)s.",
                qty=issue.quantity, value=issue.currency_id.format(issue.coupon_value), invoice=invoice._get_html_link(),
            ))
        return True

    def _create_invoice(self):
        self.ensure_one()
        product = self._coupon_product()
        vals = {
            "move_type": "out_invoice",
            "partner_id": self.partner_id.id,
            "invoice_date": self.date,
            "ref": self.name,
            "invoice_origin": self.name,
            "narration": self.note or False,
            "invoice_line_ids": [(0, 0, {
                "product_id": product.id,
                "name": _("كوبونات خصم %(name)s: %(qty)s × %(value)s", name=self.name, qty=self.quantity,
                          value=self.currency_id.format(self.coupon_value)),
                "quantity": self.quantity,
                "price_unit": self.coupon_value,
                "account_id": self.company_id.hosny_coupon_account_id.id,
                "tax_ids": [(6, 0, [])],
            })],
        }
        Move = self.env["account.move"].with_company(self.company_id)
        if "analytic_account_id" in Move._fields:
            if not self.analytic_account_id:
                raise UserError(_("الفرع «%s» ليس له حساب تحليلي.", self.pos_config_id.display_name))
            vals["analytic_account_id"] = self.analytic_account_id.id
        invoice = Move.create(vals)
        invoice.action_post()
        return invoice

    def _register_payment(self, invoice):
        self.ensure_one()
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=invoice.ids,
        ).create({
            "journal_id": self.journal_id.id,
            "payment_date": self.date,
            "amount": invoice.amount_residual,
            "communication": self.name,
        })
        payments = wizard._create_payments()
        if invoice.payment_state not in ("paid", "in_payment"):
            raise UserError(_("لم تُطابق الدفعة مع فاتورة الكوبونات — راجع إعداد الدفتر «%s».", self.journal_id.display_name))
        return payments

    def _create_cards(self):
        """كل كوبون: كود الفرع + 7 أرقام عشوائية + رقم تحقق (coupon_code.py)."""
        self.ensure_one()
        Card = self.env["loyalty.card"].sudo().with_context(active_test=False)
        prefix = self.pos_config_id.hosny_coupon_prefix
        codes = []
        for _i in range(self.quantity):
            codes.append(generate_code(prefix, lambda c: c in codes or bool(Card.search_count([("code", "=", c)]))))
        self.env["loyalty.card"].create([{
            "code": code,
            "program_id": self.program_id.id,
            "partner_id": self.partner_id.id,
            "points": self.coupon_value,
            "hosny_initial_value": self.coupon_value,
            "expiration_date": self.expiration_date or False,
            "hosny_issue_id": self.id,
        } for code in codes])

    # ── الإلغاء: قبل أي استخدام فقط ──────────────────────────────────────
    def action_cancel(self):
        for issue in self:
            if issue.state != "issued":
                continue
            if any(c.hosny_used_value > 0.0001 for c in issue.card_ids):
                raise UserError(_("لا يمكن إلغاء إصدار استُخدم منه كوبون. أوقف الكوبونات المتبقية بدلاً من ذلك."))
            for payment in issue.payment_ids:
                payment.action_draft()
                payment.action_cancel()
            if issue.invoice_id.state == "posted":
                issue.invoice_id.button_draft()
            issue.invoice_id.button_cancel()
            issue.card_ids.write({"points": 0.0, "expiration_date": fields.Date.context_today(self)})
            issue.state = "cancelled"
            issue.message_post(body=_("أُلغي الإصدار: أُلغيت الفاتورة والدفعة وأُوقفت الكوبونات."))
        return True

    # ── أزرار ────────────────────────────────────────────────────────────
    def action_view_invoice(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": "account.move", "res_id": self.invoice_id.id, "view_mode": "form"}

    def action_view_cards(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("الكوبونات"),
            "res_model": "loyalty.card",
            "view_mode": "list,form",
            "views": [(self.env.ref("hosny_coupon_issue.view_loyalty_card_list_hosny").id, "list"), (False, "form")],
            "domain": [("hosny_issue_id", "=", self.id)],
        }

    def action_print(self):
        return self.env.ref("hosny_coupon_issue.action_report_hosny_coupons").report_action(self)

    def unlink(self):
        if any(issue.state == "issued" for issue in self):
            raise UserError(_("لا يمكن حذف إصدار صادر — ألغِه أولاً."))
        return super().unlink()

    @api.constrains("expiration_date", "date")
    def _check_expiration(self):
        for issue in self:
            if issue.expiration_date and issue.expiration_date < issue.date:
                raise ValidationError(_("تاريخ الانتهاء قبل تاريخ الإصدار."))
