# -*- coding: utf-8 -*-
from odoo import api, fields, models

# أنواع تُقدَّم خارج المطعم فلا طاولة لها. «سفري» (safari) هو نوع السفري المعتمد:
# هو ما تفتحه بطاقة «سفري» في شاشة اختيار المكان. أي نوع آخر (ومنه «محلي»)
# يُقدَّم على طاولة. نفس القائمة في static/src/app/order_type_rules.js.
TABLELESS_ORDER_TYPE_CODES = ("safari", "takeaway", "delivery")
TAKEAWAY_ORDER_TYPE_CODE = "safari"
LOCAL_ORDER_TYPE_CODE = "local"


class PosOrderType(models.Model):
    """نوع الفاتورة / الطلب — مكافئ «أنواع الفواتير» في FERP."""

    _name = "pos.order.type"
    _description = "POS Order Type"
    _inherit = ["pos.load.mixin"]
    _order = "sequence, id"

    name = fields.Char("النوع", required=True, translate=True)
    code = fields.Char("الكود", help="معرّف ثابت لا يتأثر بالترجمة")
    sequence = fields.Integer("ترتيب", default=10)
    active = fields.Boolean("نشط", default=True)
    is_default = fields.Boolean(
        "الافتراضي",
        help="النوع الذي يبدأ به أي طلب جديد. واحد فقط يكون افتراضياً.")
    company_id = fields.Many2one(
        "res.company", string="الشركة", default=lambda self: self.env.company)

    _code_uniq = models.Constraint(
        "unique(code, company_id)", "كود النوع مكرر.")

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("active", "=", True)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "code", "sequence", "is_default"]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._enforce_single_default()
        # كل طابعة قائمة تحصل على سطر للنوع الجديد فوراً
        self.env["pos.printer"].search([])._ensure_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.get("is_default"):
            self._enforce_single_default()
        return res

    def _hosny_requires_table(self):
        """محلي يُقدَّم على طاولة، والسفري والتوصيل بلا طاولة."""
        self.ensure_one()
        return self.code not in TABLELESS_ORDER_TYPE_CODES

    @api.model
    def _hosny_by_code(self, code, company=None):
        """نوع الشركة إن وُجد، وإلا أي نوع نشط بنفس الكود — نقطة البيع تحمّل
        الأنواع النشطة بدون تصفية بالشركة (_load_pos_data_domain)."""
        company = company or self.env.company
        return self.search(
            [("code", "=", code), ("company_id", "in", [company.id, False])],
            order="company_id", limit=1) or self.search([("code", "=", code)], limit=1)

    @api.model
    def _hosny_local_type(self, company=None):
        return self._hosny_by_code(LOCAL_ORDER_TYPE_CODE, company) or self.search(
            [("is_default", "=", True)], limit=1)

    @api.model
    def _hosny_takeaway_type(self, company=None):
        return self._hosny_by_code(TAKEAWAY_ORDER_TYPE_CODE, company)

    def _enforce_single_default(self):
        """نوع افتراضي واحد فقط لكل شركة."""
        for rec in self.filtered("is_default"):
            others = self.search([
                ("is_default", "=", True),
                ("id", "!=", rec.id),
                ("company_id", "=", rec.company_id.id),
            ])
            others.write({"is_default": False})
