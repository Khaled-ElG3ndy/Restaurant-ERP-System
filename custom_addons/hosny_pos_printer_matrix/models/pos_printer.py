# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

REPORT_TEMPLATES = [
    ("ferp", "نسخة المطبخ (تصميم FERP)"),
    ("standard", "التذكرة القياسية"),
    ("compact", "مختصرة (بدون ملاحظات)"),
]


class PosPrinterLine(models.Model):
    """سطر لكل (طابعة × نوع فاتورة) — مكافئ تبويب «أنواع الفواتير» في FERP."""

    _name = "pos.printer.line"
    _description = "POS Printer / Order Type Setting"
    _inherit = ["pos.load.mixin"]
    _order = "order_type_id"

    printer_id = fields.Many2one(
        "pos.printer", string="الطابعة", required=True, ondelete="cascade")
    order_type_id = fields.Many2one(
        "pos.order.type", string="نوع الفاتورة", required=True,
        ondelete="cascade")
    enabled = fields.Boolean("تطبع", default=True)
    copies = fields.Integer("عدد النسخ", default=1)
    report_template = fields.Selection(
        REPORT_TEMPLATES, string="اسم التقرير", default="ferp",
        required=True)

    bundled = fields.Boolean(
        "Bundeled Receipt",
        help="تذكرة مجمّعة تحتوي أصناف كل المحطات، وليس أصناف هذه الطابعة فقط.")
    bundled_copies = fields.Integer("نسخ المجمّعة", default=1)
    bundled_report = fields.Selection(
        REPORT_TEMPLATES, string="تقرير المجمّعة", default="ferp")

    _printer_type_uniq = models.Constraint(
        "unique(printer_id, order_type_id)",
        "لا يمكن تكرار نفس نوع الفاتورة على نفس الطابعة.")
    _copies_positive = models.Constraint(
        "check(copies >= 0)", "عدد النسخ لا يمكن أن يكون سالباً.")
    _bundled_copies_positive = models.Constraint(
        "check(bundled_copies >= 0)",
        "عدد نسخ التذكرة المجمّعة لا يمكن أن يكون سالباً.")

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("printer_id", "in", config.printer_ids.ids)]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "printer_id", "order_type_id", "enabled", "copies",
                "report_template", "bundled", "bundled_copies",
                "bundled_report"]


class PosPrinter(models.Model):
    _inherit = "pos.printer"

    is_chief = fields.Boolean(
        "Is Chief",
        help="طابعة رئيسية (شيف / تمرير): تستقبل أصناف كل الأقسام بغض النظر "
             "عن الأقسام المحددة لها.")
    line_ids = fields.One2many(
        "pos.printer.line", "printer_id", string="إعدادات أنواع الفواتير")

    # تبويب «الأصناف»: اختيار صنف بصنف، فوق ما تختاره مجموعات الوجبات.
    product_ids = fields.Many2many(
        "product.template", "pos_printer_product_rel", "printer_id",
        "product_id", string="الأصناف",
        domain=[("available_in_pos", "=", True)],
        help="أصناف تُطبع على هذه الطابعة حتى لو لم تكن مجموعتها مختارة.")
    excluded_product_ids = fields.Many2many(
        "product.template", "pos_printer_product_excl_rel", "printer_id",
        "product_id", string="استثناءات",
        domain=[("available_in_pos", "=", True)],
        help="أصناف لا تُطبع هنا إطلاقاً، حتى لو كانت مجموعتها مختارة.")
    effective_product_ids = fields.Many2many(
        "product.template", string="ما يُطبع فعلياً",
        compute="_compute_effective_product_ids")

    @api.depends("product_categories_ids", "product_ids",
                 "excluded_product_ids", "is_chief")
    def _compute_effective_product_ids(self):
        """نفس قاعدة المطابقة في الشاشة، محسوبة هنا للمراجعة قبل الخدمة."""
        Product = self.env["product.template"]
        for printer in self:
            if printer.is_chief:
                domain = [("available_in_pos", "=", True)]
            else:
                cats = printer.product_categories_ids
                # الأقسام الفرعية تُطابق أيضاً كما في الشاشة
                if cats:
                    cats = self.env["pos.category"].search(
                        [("id", "child_of", cats.ids)])
                domain = ["|",
                          ("pos_categ_ids", "in", cats.ids),
                          ("id", "in", printer.product_ids.ids)]
            products = Product.search(domain)
            printer.effective_product_ids = products - printer.excluded_product_ids

    @api.constrains("product_ids")
    def _check_products_have_category(self):
        """صنف بلا مجموعة لا تكتشفه الشاشة كتغيير، فلا يصل لأي طابعة."""
        for printer in self:
            orphans = printer.product_ids.filtered(lambda p: not p.pos_categ_ids)
            if orphans:
                raise ValidationError(_(
                    "هذه الأصناف بلا مجموعة وجبات فلن تصل لأي طابعة: %s\n"
                    "أضف لها مجموعة أولاً من بطاقة الصنف.",
                    ", ".join(orphans.mapped("name"))))

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + [
            "is_chief", "product_ids", "excluded_product_ids"]

    @api.model
    def _load_pos_data_read(self, records, config):
        """طابعة الشيف تستقبل كل الأقسام.

        نوسّع الأقسام هنا وقت التحميل بدل تعديل بيانات الطابعة نفسها، حتى
        يبقى ما يراه المستخدم في الشاشة هو ما اختاره فعلاً.
        """
        result = super()._load_pos_data_read(records, config)
        chief_ids = set(records.filtered("is_chief").ids)
        if not chief_ids:
            return result
        all_categories = self.env["pos.category"].search([]).ids
        for row in result:
            if row.get("id") in chief_ids:
                row["product_categories_ids"] = all_categories
        return result

    def _ensure_lines(self):
        """يضمن وجود سطر لكل نوع فاتورة نشط على كل طابعة."""
        types = self.env["pos.order.type"].search([])
        for printer in self:
            missing = types - printer.line_ids.order_type_id
            if missing:
                printer.line_ids = [
                    (0, 0, {"order_type_id": t.id}) for t in missing]

    @api.model_create_multi
    def create(self, vals_list):
        printers = super().create(vals_list)
        printers._ensure_lines()
        return printers
