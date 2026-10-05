from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HosnyPackagingType(models.Model):
    _name = "hosny.packaging.type"
    _description = "Packaging Type"
    _order = "sequence, name, id"
    _check_company_auto = True

    name = fields.Char(string="Packaging Type", required=True, translate=True, index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                hosny_packaging_type_name_company_uniq
            ON hosny_packaging_type
                (LOWER(COALESCE(name->>'en_US', '')), COALESCE(company_id, 0))
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        seen = set()
        for vals in vals_list:
            name = (vals.get("name") or "").strip()
            company_id = vals.get("company_id") or False
            key = (name.casefold(), company_id)
            if key in seen or self.with_context(active_test=False).search_count(
                [("name", "=ilike", name), ("company_id", "=", company_id)], limit=1
            ):
                raise ValidationError(_("A packaging type with this name already exists for the company."))
            seen.add(key)
        return super().create(vals_list)

    def write(self, vals):
        if {"name", "company_id"} & set(vals):
            seen = set()
            for packaging_type in self:
                name = (vals.get("name", packaging_type.name) or "").strip()
                company_id = vals.get("company_id", packaging_type.company_id.id) or False
                key = (name.casefold(), company_id)
                if key in seen or self.with_context(active_test=False).search_count(
                    [
                        ("id", "not in", self.ids),
                        ("name", "=ilike", name),
                        ("company_id", "=", company_id),
                    ],
                    limit=1,
                ):
                    raise ValidationError(_("A packaging type with this name already exists for the company."))
                seen.add(key)
        result = super().write(vals)
        if "name" in vals:
            self.env["hosny.purchase.packaging"].search(
                [("packaging_type_id", "in", self.ids)]
            )._sync_managed_uom()
        return result


class UomUom(models.Model):
    _inherit = "uom.uom"

    hosny_is_technical_purchase_packaging = fields.Boolean(
        string="Technical Purchase Packaging Unit",
        default=False,
        copy=False,
        index=True,
    )
