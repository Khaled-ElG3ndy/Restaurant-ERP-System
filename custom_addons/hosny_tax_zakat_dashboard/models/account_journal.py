import ast
import json
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.fields import Domain
from odoo.tools.misc import format_date


class AccountJournal(models.Model):
    _inherit = "account.journal"

    is_tax_zakat_dashboard = fields.Boolean(
        string="Saudi Tax and Zakat Dashboard",
        compute="_compute_is_tax_zakat_dashboard",
    )
    tax_zakat_account_ids = fields.Many2many(
        comodel_name="account.account",
        relation="account_journal_tax_zakat_account_rel",
        column1="journal_id",
        column2="account_id",
        string="Zakat Accounts",
        check_company=True,
        help=(
            "Explicit Zakat control accounts to include. Select only the accounts "
            "whose movement represents the Zakat amount; names are never used for detection."
        ),
    )
    tax_zakat_tax_ids = fields.Many2many(
        comodel_name="account.tax",
        relation="account_journal_tax_zakat_tax_rel",
        column1="journal_id",
        column2="tax_id",
        string="Zakat Taxes",
        check_company=True,
        help="Taxes explicitly configured as Zakat or withholding movements.",
    )
    tax_zakat_tag_ids = fields.Many2many(
        comodel_name="account.account.tag",
        relation="account_journal_tax_zakat_tag_rel",
        column1="journal_id",
        column2="tag_id",
        string="Zakat Tags",
        help=(
            "Tax-grid tags explicitly dedicated to Zakat. Do not select ordinary "
            "VAT base tags because they identify the taxable base, not the tax amount."
        ),
    )
    tax_zakat_dashboard_data = fields.Text(
        compute="_compute_tax_zakat_dashboard",
    )
    tax_zakat_dashboard_graph = fields.Text(
        compute="_compute_tax_zakat_dashboard",
    )

    @api.depends("company_id", "code", "type")
    def _compute_is_tax_zakat_dashboard(self):
        external_ids = self.get_external_id()
        for journal in self:
            journal.is_tax_zakat_dashboard = (
                external_ids.get(journal.id)
                == f"account.{journal.company_id.id}_zakat"
            )

    def _get_zakat_line_domain(self):
        self.ensure_one()
        domains = []
        if self.tax_zakat_account_ids:
            domains.append(Domain("account_id", "in", self.tax_zakat_account_ids.ids))
        if self.tax_zakat_tax_ids:
            domains.append(
                Domain("tax_line_id", "in", self.tax_zakat_tax_ids.ids)
                | Domain(
                    "tax_repartition_line_id.tax_id",
                    "in",
                    self.tax_zakat_tax_ids.ids,
                )
            )
        if self.tax_zakat_tag_ids:
            domains.append(Domain("tax_tag_ids", "in", self.tax_zakat_tag_ids.ids))
        return Domain.OR(domains) if domains else Domain.FALSE

    def _get_tax_zakat_line_domain(self):
        self.ensure_one()
        return Domain("tax_repartition_line_id", "!=", False) | self._get_zakat_line_domain()

    def _line_is_configured_zakat(self, line):
        self.ensure_one()
        originator_tax = line.tax_line_id or line.tax_repartition_line_id.tax_id
        return bool(
            line.account_id in self.tax_zakat_account_ids
            or originator_tax in self.tax_zakat_tax_ids
            or line.tax_tag_ids & self.tax_zakat_tag_ids
        )

    def _line_tax_zakat_kind(self, line):
        self.ensure_one()
        if self._line_is_configured_zakat(line):
            return "zakat"
        originator_tax = line.tax_line_id or line.tax_repartition_line_id.tax_id
        if originator_tax.type_tax_use == "sale":
            return "output"
        if originator_tax.type_tax_use == "purchase":
            return "input"
        return "other"

    def _line_tax_zakat_report_amount(self, line):
        """Signed company-currency contribution to the dashboard net amount."""
        self.ensure_one()
        kind = self._line_tax_zakat_kind(line)
        if kind != "zakat":
            # Output tax is normally a credit (negative balance), while input tax
            # is normally a debit (positive balance). Negating balance therefore
            # gives output - input and naturally preserves refunds.
            return -line.balance

        # Zakat must be explicitly configured. Respect the natural sign of the
        # selected control account so either a payable or an expense control
        # account can be selected, without relying on its translated name.
        credit_nature_types = {
            "equity",
            "equity_unaffected",
            "income",
            "income_other",
            "liability_current",
            "liability_credit_card",
            "liability_non_current",
            "liability_payable",
        }
        return -line.balance if line.account_id.account_type in credit_nature_types else line.balance

    def _get_tax_zakat_period(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        date_from = date(today.year, 1, 1)
        return date_from, date_from + relativedelta(years=1)

    def _get_tax_zakat_metrics(self):
        self.ensure_one()
        date_from, date_to = self._get_tax_zakat_period()
        domain = (
            self._get_tax_zakat_line_domain()
            & Domain("company_id", "=", self.company_id.id)
            & Domain("parent_state", "=", "posted")
            & Domain("date", ">=", date_from)
            & Domain("date", "<", date_to)
        )
        lines = self.env["account.move.line"].search(domain)

        output_tax = input_tax = zakat = other = 0.0
        monthly_net = defaultdict(float)
        for line in lines:
            kind = self._line_tax_zakat_kind(line)
            report_amount = self._line_tax_zakat_report_amount(line)
            monthly_net[line.date.replace(day=1)] += report_amount
            if kind == "output":
                output_tax += report_amount
            elif kind == "input":
                input_tax -= report_amount
            elif kind == "zakat":
                zakat += report_amount
            else:
                other += report_amount

        return {
            "date_from": date_from,
            "date_to": date_to,
            "line_count": len(lines),
            "output_tax": output_tax,
            "input_tax": input_tax,
            "zakat": zakat,
            "other": other,
            "net": output_tax - input_tax + zakat + other,
            "monthly_net": monthly_net,
        }

    def _compute_tax_zakat_dashboard(self):
        for journal in self:
            if not journal.is_tax_zakat_dashboard:
                journal.tax_zakat_dashboard_data = False
                journal.tax_zakat_dashboard_graph = False
                continue

            metrics = journal._get_tax_zakat_metrics()
            currency = journal.company_id.currency_id
            period_label = str(metrics["date_from"].year)
            journal.tax_zakat_dashboard_data = json.dumps({
                "output_tax": currency.format(metrics["output_tax"]),
                "output_tax_raw": metrics["output_tax"],
                "input_tax": currency.format(metrics["input_tax"]),
                "input_tax_raw": metrics["input_tax"],
                "zakat": currency.format(metrics["zakat"]),
                "zakat_raw": metrics["zakat"],
                "net": currency.format(metrics["net"]),
                "net_raw": metrics["net"],
                "line_count": metrics["line_count"],
                "period_label": period_label,
                "has_zakat_configuration": bool(
                    journal.tax_zakat_account_ids
                    or journal.tax_zakat_tax_ids
                    or journal.tax_zakat_tag_ids
                ),
            })

            values = []
            month = metrics["date_from"]
            while month < metrics["date_to"]:
                values.append({
                    "x": format_date(journal.env, month, date_format="MMM"),
                    "y": currency.round(metrics["monthly_net"].get(month, 0.0)),
                    "name": format_date(journal.env, month, date_format="MMMM y"),
                })
                month += relativedelta(months=1)
            journal.tax_zakat_dashboard_graph = json.dumps([{
                "values": values,
                "title": _("Monthly net tax and Zakat movement"),
                "key": _("Net due"),
                "area": True,
                "color": "#7c7bad",
                "is_sample_data": False,
            }])

    def action_open_tax_zakat_lines(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "hosny_tax_zakat_dashboard.action_tax_zakat_move_lines"
        )
        action_domain = action.get("domain") or []
        if isinstance(action_domain, str):
            action_domain = ast.literal_eval(action_domain)
        action["domain"] = list(Domain.AND([
            Domain(action_domain),
            Domain("company_id", "=", self.company_id.id),
        ]))
        today = fields.Date.context_today(self)
        month_from = today.replace(day=1)
        quarter_from = today.replace(
            month=((today.month - 1) // 3) * 3 + 1,
            day=1,
        )
        year_from, year_to = self._get_tax_zakat_period()
        action_context = dict(self.env.context)
        action_context.update({
            "tax_zakat_journal_id": self.id,
            "tax_zakat_current_month_from": fields.Date.to_string(month_from),
            "tax_zakat_current_month_to": fields.Date.to_string(
                month_from + relativedelta(months=1)
            ),
            "tax_zakat_current_quarter_from": fields.Date.to_string(quarter_from),
            "tax_zakat_current_quarter_to": fields.Date.to_string(
                quarter_from + relativedelta(months=3)
            ),
            "tax_zakat_current_year_from": fields.Date.to_string(year_from),
            "tax_zakat_current_year_to": fields.Date.to_string(year_to),
            "search_default_posted": 1,
            "search_default_current_year": 1,
        })
        action["context"] = action_context
        return action
