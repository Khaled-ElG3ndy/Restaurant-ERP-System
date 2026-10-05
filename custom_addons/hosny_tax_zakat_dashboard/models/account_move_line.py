from odoo import api, fields, models
from odoo.fields import Domain


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    tax_zakat_is_reportable = fields.Boolean(
        string="Tax/Zakat Movement",
        compute="_compute_tax_zakat_display_fields",
        search="_search_tax_zakat_is_reportable",
    )
    tax_zakat_kind = fields.Selection(
        selection=[
            ("output", "Output Tax"),
            ("input", "Input Tax"),
            ("zakat", "Zakat"),
            ("other", "Other Tax"),
        ],
        string="Tax/Zakat Classification",
        compute="_compute_tax_zakat_display_fields",
        search="_search_tax_zakat_kind",
    )
    tax_zakat_label = fields.Char(
        string="Tax or Zakat",
        compute="_compute_tax_zakat_display_fields",
    )
    tax_zakat_report_amount = fields.Monetary(
        string="Net Tax/Zakat Amount",
        currency_field="company_currency_id",
        compute="_compute_tax_zakat_display_fields",
        help="Signed contribution to net due in company currency.",
    )
    tax_zakat_document_type = fields.Selection(
        related="move_id.move_type",
        string="Document Type",
        store=True,
        index=True,
    )

    @api.model
    def _tax_zakat_configuration_journals(self):
        journal_id = self.env.context.get("tax_zakat_journal_id")
        if journal_id:
            journal = self.env["account.journal"].browse(journal_id).exists()
            if (
                journal
                and journal.company_id in self.env.companies
                and journal.is_tax_zakat_dashboard
            ):
                return journal
            return self.env["account.journal"].browse()

        candidates = self.env["account.journal"].search([
            ("company_id", "in", self.env.companies.ids),
            ("type", "=", "general"),
            ("code", "=", "ZAKAT"),
        ])
        return candidates.filtered("is_tax_zakat_dashboard")

    @api.model
    def _tax_zakat_zakat_domain(self):
        domains = [
            journal._get_zakat_line_domain()
            & Domain("company_id", "=", journal.company_id.id)
            for journal in self._tax_zakat_configuration_journals()
        ]
        return Domain.OR(domains) if domains else Domain.FALSE

    @api.model
    def _tax_zakat_reportable_domain(self):
        return (
            Domain("tax_repartition_line_id", "!=", False)
            | self._tax_zakat_zakat_domain()
        )

    @api.model
    def _tax_zakat_kind_domain(self, kind):
        zakat_domain = self._tax_zakat_zakat_domain()
        if kind == "zakat":
            return zakat_domain
        if kind == "output":
            return (
                Domain("tax_repartition_line_id", "!=", False)
                & (
                    Domain("tax_line_id.type_tax_use", "=", "sale")
                    | Domain(
                        "tax_repartition_line_id.tax_id.type_tax_use",
                        "=",
                        "sale",
                    )
                )
                & ~zakat_domain
            )
        if kind == "input":
            return (
                Domain("tax_repartition_line_id", "!=", False)
                & (
                    Domain("tax_line_id.type_tax_use", "=", "purchase")
                    | Domain(
                        "tax_repartition_line_id.tax_id.type_tax_use",
                        "=",
                        "purchase",
                    )
                )
                & ~zakat_domain
            )
        if kind == "other":
            return (
                self._tax_zakat_reportable_domain()
                & ~self._tax_zakat_kind_domain("output")
                & ~self._tax_zakat_kind_domain("input")
                & ~zakat_domain
            )
        return Domain.FALSE

    @api.model
    def _search_tax_zakat_is_reportable(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            return NotImplemented
        domain = self._tax_zakat_reportable_domain()
        return domain if (operator == "=") == value else ~domain

    @api.model
    def _search_tax_zakat_kind(self, operator, value):
        if operator in ("=", "!="):
            domain = self._tax_zakat_kind_domain(value)
            return domain if operator == "=" else ~domain
        if operator in ("in", "not in") and isinstance(value, (list, tuple)):
            domain = Domain.OR(self._tax_zakat_kind_domain(item) for item in value)
            return domain if operator == "in" else ~domain
        return NotImplemented

    def _get_tax_zakat_journal_map(self):
        return {
            journal.company_id.id: journal
            for journal in self._tax_zakat_configuration_journals()
        }

    @api.depends(
        "balance",
        "account_id",
        "account_id.account_type",
        "tax_line_id",
        "tax_line_id.type_tax_use",
        "tax_repartition_line_id",
        "tax_tag_ids",
        "company_id",
    )
    def _compute_tax_zakat_display_fields(self):
        journals_by_company = self._get_tax_zakat_journal_map()
        for line in self:
            journal = journals_by_company.get(line.company_id.id)
            is_standard_tax = bool(line.tax_repartition_line_id)
            is_zakat = bool(journal and journal._line_is_configured_zakat(line))
            originator_tax = line.tax_line_id or line.tax_repartition_line_id.tax_id
            line.tax_zakat_is_reportable = is_standard_tax or is_zakat

            if journal:
                kind = journal._line_tax_zakat_kind(line)
                amount = journal._line_tax_zakat_report_amount(line)
            elif originator_tax.type_tax_use == "sale":
                kind = "output"
                amount = -line.balance
            elif originator_tax.type_tax_use == "purchase":
                kind = "input"
                amount = -line.balance
            else:
                kind = "other"
                amount = -line.balance
            line.tax_zakat_kind = kind
            line.tax_zakat_report_amount = amount

            if originator_tax:
                label = originator_tax.display_name
            elif is_zakat and line.tax_tag_ids:
                configured_tags = line.tax_tag_ids & journal.tax_zakat_tag_ids
                label = ", ".join(configured_tags.mapped("display_name"))
            elif is_zakat:
                label = line.account_id.display_name
            else:
                label = False
            line.tax_zakat_label = label
