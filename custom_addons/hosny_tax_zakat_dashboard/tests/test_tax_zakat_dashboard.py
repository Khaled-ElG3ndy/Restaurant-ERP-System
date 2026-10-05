from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.fields import Domain
from odoo.tests import tagged


@tagged("post_install", "-at_install", "hosny_tax_zakat_dashboard")
class TestTaxZakatDashboard(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env.user)
        cls.zakat_journal = cls._get_or_create_zakat_journal(cls.company)
        cls.test_analytic_account = cls._get_or_create_analytic_account(cls.company)
        cls.other_currency = cls.setup_other_currency("EUR")

        cls.sale_tax_excluded = cls.tax_sale_a.copy({
            "name": "Test Sales VAT 15% Excluded",
            "amount": 15.0,
            "type_tax_use": "sale",
            "price_include_override": "tax_excluded",
        })
        cls.sale_tax_included = cls.tax_sale_a.copy({
            "name": "Test Sales VAT 15% Included",
            "amount": 15.0,
            "type_tax_use": "sale",
            "price_include_override": "tax_included",
        })
        cls.sale_tax_five = cls.tax_sale_a.copy({
            "name": "Test Sales VAT 5% Excluded",
            "amount": 5.0,
            "type_tax_use": "sale",
            "price_include_override": "tax_excluded",
        })
        cls.purchase_tax_excluded = cls.tax_purchase_a.copy({
            "name": "Test Purchase VAT 15% Excluded",
            "amount": 15.0,
            "type_tax_use": "purchase",
            "price_include_override": "tax_excluded",
        })

        cls.customer_invoice = cls._create_test_invoice(
            "out_invoice",
            amount=100.0,
            taxes=[cls.sale_tax_excluded],
            post=True,
        )
        cls.full_customer_credit = cls.customer_invoice._reverse_moves(
            [{"invoice_date": cls.today}],
            cancel=True,
        )
        cls.partial_customer_credit = cls._create_test_invoice(
            "out_refund",
            amount=40.0,
            taxes=[cls.sale_tax_excluded],
            post=True,
        )
        cls.vendor_bill = cls._create_test_invoice(
            "in_invoice",
            amount=100.0,
            taxes=[cls.purchase_tax_excluded],
            post=True,
        )
        cls.vendor_credit = cls._create_test_invoice(
            "in_refund",
            amount=100.0,
            taxes=[cls.purchase_tax_excluded],
            post=True,
        )
        cls.included_invoice = cls._create_test_invoice(
            "out_invoice",
            amount=115.0,
            taxes=[cls.sale_tax_included],
            post=True,
        )
        cls.multi_tax_invoice = cls._create_test_invoice(
            "out_invoice",
            amount=100.0,
            taxes=[cls.sale_tax_excluded, cls.sale_tax_five],
            post=True,
        )
        cls.draft_invoice = cls._create_test_invoice(
            "out_invoice",
            amount=100.0,
            taxes=[cls.sale_tax_excluded],
        )
        cls.no_tax_invoice = cls._create_test_invoice(
            "out_invoice",
            amount=100.0,
            taxes=[],
            post=True,
        )
        cls.foreign_invoice = cls._create_test_invoice(
            "out_invoice",
            amount=100.0,
            taxes=[cls.sale_tax_excluded],
            currency=cls.other_currency,
            post=True,
        )
        cls.manual_tax_move = cls._create_manual_tax_move(cls.sale_tax_excluded)

    @classmethod
    def _get_or_create_zakat_journal(cls, company):
        xmlid = f"account.{company.id}_zakat"
        journal = cls.env.ref(xmlid, raise_if_not_found=False)
        if journal:
            return journal
        journal = cls.env["account.journal"].with_company(company).create({
            "name": "Zakat",
            "code": "ZAKAT",
            "type": "general",
            "company_id": company.id,
            "show_on_dashboard": True,
        })
        cls.env["ir.model.data"].create({
            "module": "account",
            "name": f"{company.id}_zakat",
            "model": "account.journal",
            "res_id": journal.id,
            "noupdate": True,
        })
        return journal

    @classmethod
    def _get_or_create_analytic_account(cls, company):
        plan = cls.env["account.analytic.plan"].search([], limit=1)
        if not plan:
            plan = cls.env["account.analytic.plan"].create({
                "name": "Tax Zakat Test Plan",
            })
        return cls.env["account.analytic.account"].create({
            "name": f"Tax Zakat Test {company.name}",
            "plan_id": plan.id,
            "company_id": company.id,
        })

    @classmethod
    def _create_test_invoice(
        cls,
        move_type,
        amount,
        taxes,
        post=False,
        currency=None,
        company_data=None,
        analytic_account=None,
    ):
        company_data = company_data or cls.company_data
        company = company_data["company"]
        is_sale = move_type in ("out_invoice", "out_refund", "out_receipt")
        move_vals = {
            "move_type": move_type,
            "partner_id": cls.partner_a.id,
            "invoice_date": cls.today,
            "date": cls.today,
            "journal_id": (
                company_data["default_journal_sale"].id
                if is_sale
                else company_data["default_journal_purchase"].id
            ),
            "company_id": company.id,
            "currency_id": (currency or company.currency_id).id,
            "invoice_line_ids": [
                Command.create({
                    "name": "Tax Zakat test line",
                    "quantity": 1.0,
                    "price_unit": amount,
                    "account_id": (
                        company_data["default_account_revenue"].id
                        if is_sale
                        else company_data["default_account_expense"].id
                    ),
                    "tax_ids": [Command.set([tax.id for tax in taxes])],
                }),
            ],
        }
        if "analytic_account_id" in cls.env["account.move"]._fields:
            move_vals["analytic_account_id"] = (
                analytic_account or cls.test_analytic_account
            ).id
        move = cls.env["account.move"].with_company(company).create(move_vals)
        if post:
            move.action_post()
        return move

    @classmethod
    def _tax_lines(cls, move):
        return move.line_ids.filtered("tax_repartition_line_id")

    @classmethod
    def _create_manual_tax_move(cls, tax):
        repartition_line = tax.invoice_repartition_line_ids.filtered(
            lambda line: line.repartition_type == "tax"
        )[:1]
        move_vals = {
            "move_type": "entry",
            "date": cls.today,
            "journal_id": cls.company_data["default_journal_misc"].id,
            "ref": "TEST-MANUAL-TAX",
            "line_ids": [
                Command.create({
                    "name": "Manual taxable revenue",
                    "account_id": cls.company_data["default_account_revenue"].id,
                    "credit": 100.0,
                    "tax_ids": [Command.set(tax.ids)],
                }),
                Command.create({
                    "name": "Manual output tax",
                    "account_id": repartition_line.account_id.id,
                    "credit": 15.0,
                    "tax_repartition_line_id": repartition_line.id,
                    "tax_base_amount": -100.0,
                    "display_type": "tax",
                }),
                Command.create({
                    "name": "Manual receivable counterpart",
                    "account_id": cls.company_data["default_account_receivable"].id,
                    "debit": 115.0,
                }),
            ],
        }
        if "analytic_account_id" in cls.env["account.move"]._fields:
            move_vals["analytic_account_id"] = cls.test_analytic_account.id
        move = cls.env["account.move"].with_context(
            check_move_validity=False,
        ).create(move_vals)
        move.action_post()
        return move

    def _action_lines(self, journal=None, posted=True):
        journal = journal or self.zakat_journal
        action = journal.with_context(
            allowed_company_ids=self.env.companies.ids,
        ).action_open_tax_zakat_lines()
        domain = Domain(action["domain"])
        if posted:
            date_from = self.today.replace(month=1, day=1)
            domain &= (
                Domain("parent_state", "=", "posted")
                & Domain("date", ">=", date_from)
                & Domain("date", "<", date_from + relativedelta(years=1))
            )
        return self.env["account.move.line"].with_context(action["context"]).search(domain)

    def test_customer_invoice_full_and_partial_credit_notes(self):
        invoice_tax = self._tax_lines(self.customer_invoice)
        full_credit_tax = self._tax_lines(self.full_customer_credit)
        partial_credit_tax = self._tax_lines(self.partial_customer_credit)

        self.assertRecordValues(invoice_tax, [{
            "parent_state": "posted",
            "tax_line_id": self.sale_tax_excluded.id,
            "balance": -15.0,
            "tax_base_amount": -100.0,
        }])
        self.assertEqual(full_credit_tax.balance, 15.0)
        self.assertEqual(full_credit_tax.tax_base_amount, 100.0)
        self.assertEqual(partial_credit_tax.balance, 6.0)
        self.assertEqual(partial_credit_tax.tax_base_amount, 40.0)

    def test_vendor_bill_and_vendor_credit_note(self):
        bill_tax = self._tax_lines(self.vendor_bill)
        refund_tax = self._tax_lines(self.vendor_credit)
        self.assertEqual(bill_tax.balance, 15.0)
        self.assertEqual(bill_tax.tax_base_amount, 100.0)
        self.assertEqual(refund_tax.balance, -15.0)
        self.assertEqual(refund_tax.tax_base_amount, -100.0)

    def test_price_included_and_excluded_tax_bases(self):
        included_tax = self._tax_lines(self.included_invoice)
        excluded_tax = self._tax_lines(self.customer_invoice)
        self.assertEqual(abs(included_tax.tax_base_amount), 100.0)
        self.assertEqual(abs(included_tax.balance), 15.0)
        self.assertEqual(abs(excluded_tax.tax_base_amount), 100.0)
        self.assertEqual(abs(excluded_tax.balance), 15.0)

    def test_multiple_taxes_are_unique(self):
        tax_lines = self._tax_lines(self.multi_tax_invoice)
        self.assertEqual(len(tax_lines), 2)
        self.assertEqual(len(tax_lines.ids), len(set(tax_lines.ids)))
        self.assertEqual(set(tax_lines.mapped("tax_line_id")), {
            self.sale_tax_excluded,
            self.sale_tax_five,
        })
        self.assertEqual(sorted(abs(value) for value in tax_lines.mapped("balance")), [5.0, 15.0])

    def test_manual_tax_line_is_included_and_plain_entry_is_not(self):
        manual_tax_line = self._tax_lines(self.manual_tax_move)
        self.assertEqual(manual_tax_line.tax_zakat_kind, "output")
        self.assertIn(manual_tax_line, self._action_lines())

        plain_lines = self.no_tax_invoice.line_ids
        self.assertFalse(plain_lines & self._action_lines())

    def test_draft_is_hidden_by_default_but_available(self):
        draft_tax_line = self._tax_lines(self.draft_invoice)
        action = self.zakat_journal.action_open_tax_zakat_lines()
        self.assertEqual(action["context"]["search_default_posted"], 1)
        self.assertNotIn(draft_tax_line, self._action_lines(posted=True))
        all_states = self.env["account.move.line"].with_context(action["context"]).search(
            Domain(action["domain"])
        )
        self.assertIn(draft_tax_line, all_states)

    def test_foreign_currency_keeps_both_currencies(self):
        tax_line = self._tax_lines(self.foreign_invoice)
        self.assertEqual(tax_line.currency_id, self.other_currency)
        self.assertEqual(tax_line.company_currency_id, self.company.currency_id)
        self.assertNotEqual(abs(tax_line.amount_currency), abs(tax_line.balance))
        self.assertEqual(tax_line.tax_zakat_report_amount, -tax_line.balance)

    def test_zakat_requires_explicit_account_or_tag_configuration(self):
        zakat_account = self.company_data["default_account_expense"].copy({
            "name": "مصاريف الزكاة للاختبار",
            "code": "ZKTEST",
        })
        move_vals = {
            "move_type": "entry",
            "date": self.today,
            "journal_id": self.company_data["default_journal_misc"].id,
            "line_ids": [
                Command.create({
                    "name": "Named Zakat account",
                    "account_id": zakat_account.id,
                    "debit": 100.0,
                }),
                Command.create({
                    "name": "Counterpart",
                    "account_id": self.company_data["default_account_revenue"].id,
                    "credit": 100.0,
                }),
            ],
        }
        if "analytic_account_id" in self.env["account.move"]._fields:
            move_vals["analytic_account_id"] = self.test_analytic_account.id
        plain_zakat_named_move = self.env["account.move"].with_context(
            check_move_validity=False,
        ).create(move_vals)
        plain_zakat_named_move.action_post()
        zakat_line = plain_zakat_named_move.line_ids.filtered(
            lambda line: line.account_id == zakat_account
        )
        self.assertNotIn(zakat_line, self._action_lines())

        self.zakat_journal.tax_zakat_account_ids = zakat_account
        self.assertIn(zakat_line, self._action_lines())
        self.assertEqual(zakat_line.tax_zakat_kind, "zakat")
        self.assertEqual(zakat_line.tax_zakat_report_amount, 100.0)

        zakat_tag = self.env["account.account.tag"].create({
            "name": "Dedicated Zakat Test Tag",
            "applicability": "taxes",
            "country_id": self.company.account_fiscal_country_id.id,
        })
        self.zakat_journal.tax_zakat_tag_ids = zakat_tag
        tagged_line = plain_zakat_named_move.line_ids.filtered(
            lambda line: line.account_id != zakat_account
        )
        tagged_line.tax_tag_ids = zakat_tag
        self.assertIn(tagged_line, self._action_lines())
        self.assertEqual(tagged_line.tax_zakat_kind, "zakat")

    def test_multicompany_action_is_scoped_to_card_company(self):
        other_data = self.setup_other_company(name="Tax Zakat Other Company")
        other_company = other_data["company"]
        self.env.user.company_ids |= other_company
        other_tax = other_data["default_tax_sale"].copy({
            "name": "Other Company VAT 15%",
            "amount": 15.0,
            "type_tax_use": "sale",
            "price_include_override": "tax_excluded",
        })
        other_analytic = self._get_or_create_analytic_account(other_company)
        other_invoice = self._create_test_invoice(
            "out_invoice",
            amount=100.0,
            taxes=[other_tax],
            company_data=other_data,
            analytic_account=other_analytic,
            post=True,
        )
        other_tax_line = self._tax_lines(other_invoice)
        other_journal = self._get_or_create_zakat_journal(other_company)

        allowed_context = {"allowed_company_ids": [self.company.id, other_company.id]}
        own_lines = self.zakat_journal.with_context(**allowed_context).action_open_tax_zakat_lines()
        own_result = self.env["account.move.line"].with_context(
            **allowed_context,
            tax_zakat_journal_id=self.zakat_journal.id,
        ).search(Domain(own_lines["domain"]))
        self.assertNotIn(other_tax_line, own_result)

        other_action = other_journal.with_context(**allowed_context).action_open_tax_zakat_lines()
        other_result = self.env["account.move.line"].with_context(
            **allowed_context,
            tax_zakat_journal_id=other_journal.id,
        ).search(Domain(other_action["domain"]))
        self.assertIn(other_tax_line, other_result)

    def test_dashboard_total_matches_opened_lines(self):
        lines = self._action_lines()
        metrics = self.zakat_journal._get_tax_zakat_metrics()
        self.assertEqual(metrics["line_count"], len(lines))
        self.assertEqual(len(lines.ids), len(set(lines.ids)))
        self.assertAlmostEqual(
            metrics["net"],
            sum(lines.mapped("tax_zakat_report_amount")),
            places=2,
        )

    def test_dashboard_owl_condition_uses_client_negation(self):
        dashboard_view = self.env["account.journal"].get_view(
            view_id=self.env.ref(
                "account.account_journal_dashboard_kanban_view"
            ).id,
            view_type="kanban",
        )
        self.assertIn(
            "journal_type == 'general' and !is_tax_zakat_dashboard",
            dashboard_view["arch"],
        )
        self.assertNotIn(
            "journal_type == 'general' and not is_tax_zakat_dashboard",
            dashboard_view["arch"],
        )

    def test_all_standard_dashboard_amounts_are_ltr_and_negative_red(self):
        dashboard_view = self.env["account.journal"].get_view(
            view_id=self.env.ref(
                "account.account_journal_dashboard_kanban_view"
            ).id,
            view_type="kanban",
        )
        dashboard_arch = etree.fromstring(dashboard_view["arch"].encode())
        amount_fields = (
            "account_balance",
            "last_balance",
            "outstanding_pay_account_balance",
            "misc_operations_balance",
            "sum_draft",
            "sum_waiting",
            "sum_late",
            "to_check_balance",
        )

        for field_name in amount_fields:
            amount_nodes = dashboard_arch.xpath(
                f"//span[t[@t-out='dashboard.{field_name}']]"
            )
            self.assertEqual(
                len(amount_nodes),
                1,
                f"Expected one dashboard amount node for {field_name}",
            )
            amount_node = amount_nodes[0]
            self.assertEqual(amount_node.get("dir"), "ltr")
            self.assertIn(
                "o_hosny_dashboard_amount",
                amount_node.get("class", "").split(),
            )
            self.assertIn(
                "direction: ltr !important",
                amount_node.get("style", ""),
            )
            self.assertIn(
                "unicode-bidi: isolate",
                amount_node.get("style", ""),
            )
            self.assertIn(
                f"(dashboard.{field_name} || '').includes('-')",
                amount_node.get("t-att-class", ""),
            )
            self.assertIn(
                "text-danger",
                amount_node.get("t-att-class", ""),
            )

    def test_client_date_filters_use_server_computed_boundaries(self):
        action = self.zakat_journal.action_open_tax_zakat_lines()
        expected_context = {
            "tax_zakat_current_month_from",
            "tax_zakat_current_month_to",
            "tax_zakat_current_quarter_from",
            "tax_zakat_current_quarter_to",
            "tax_zakat_current_year_from",
            "tax_zakat_current_year_to",
        }
        self.assertTrue(expected_context.issubset(action["context"]))
        self.assertTrue(
            all(
                isinstance(action["context"][key], str)
                for key in expected_context
            )
        )

        search_view = self.env["account.move.line"].get_view(
            view_id=self.env.ref(
                "hosny_tax_zakat_dashboard.view_tax_zakat_move_line_search"
            ).id,
            view_type="search",
        )
        self.assertNotIn("context_today().replace(", search_view["arch"])
        for key in expected_context:
            self.assertIn(f"context.get('{key}')", search_view["arch"])

    def test_list_colors_and_optional_columns(self):
        list_view = self.env["account.move.line"].get_view(
            view_id=self.env.ref(
                "hosny_tax_zakat_dashboard.view_tax_zakat_move_line_list"
            ).id,
            view_type="list",
        )
        list_arch = etree.fromstring(list_view["arch"].encode())
        optional_fields = list_arch.xpath("//list/field")
        self.assertTrue(optional_fields)
        self.assertTrue(
            all(field.get("optional") in ("show", "hide") for field in optional_fields)
        )

        for field_name in (
            "tax_base_amount",
            "amount_currency",
            "tax_zakat_report_amount",
            "debit",
            "credit",
            "balance",
        ):
            field = list_arch.xpath(f"//list/field[@name='{field_name}']")[0]
            self.assertEqual(
                field.get("decoration-danger"),
                f"{field_name} < 0",
            )

        state_field = list_arch.xpath("//list/field[@name='parent_state']")[0]
        self.assertEqual(
            state_field.get("decoration-success"),
            "parent_state == 'posted'",
        )
        self.assertEqual(
            state_field.get("decoration-warning"),
            "parent_state == 'draft'",
        )
        self.assertEqual(
            state_field.get("decoration-danger"),
            "parent_state == 'cancel'",
        )

    def test_accounting_branch_fields_when_available(self):
        if "branch_id" not in self.env["account.move.line"]._fields:
            self.skipTest("No accounting branch field is installed in this system.")
        self.assertIn("branch_id", self.env["account.move"]._fields)

    def test_posted_pos_tax_move_is_reportable(self):
        pos_env = self.env(su=True)
        tax = self.sale_tax_excluded.copy({
            "name": "POS VAT 15% Test",
            "amount": 15.0,
            "price_include_override": "tax_excluded",
        })
        product = self.env["product.product"].create({
            "name": "Tax Zakat POS Product",
            "available_in_pos": True,
            "is_storable": False,
            "list_price": 100.0,
            "taxes_id": [Command.set(tax.ids)],
            "property_account_income_id": self.company_data["default_account_revenue"].id,
        })
        pricelist = self.env["product.pricelist"].create({
            "name": "Tax Zakat POS Pricelist",
            "currency_id": self.company.currency_id.id,
        })
        config_vals = {
            "name": "Tax Zakat POS Test",
            "company_id": self.company.id,
            "invoice_journal_id": self.company_data["default_journal_sale"].id,
            "available_pricelist_ids": [Command.link(pricelist.id)],
            "pricelist_id": pricelist.id,
        }
        if "analytic_account_id" in self.env["pos.config"]._fields:
            config_vals["analytic_account_id"] = self.test_analytic_account.id
        config = pos_env["pos.config"].create(config_vals)
        payment_method = config.payment_method_ids.filtered("is_cash_count")[:1]
        if not payment_method:
            payment_method = pos_env["pos.payment.method"].create({
                "name": "Tax Zakat Cash",
                "journal_id": self.company_data["default_journal_cash"].id,
                "receivable_account_id": self.company_data["default_account_receivable"].id,
                "company_id": self.company.id,
            })
            config.payment_method_ids = [Command.link(payment_method.id)]
        if "analytic_account_id" in payment_method.journal_id._fields:
            payment_method.journal_id.analytic_account_id = self.test_analytic_account

        config.open_ui()
        session = config.current_session_id
        session.set_opening_control(0, None)
        tax_values = tax.compute_all(
            100.0,
            self.company.currency_id,
            1.0,
            product=product,
        )
        total_excluded = tax_values["total_excluded"]
        total_included = tax_values["total_included"]
        order_data = {
            "amount_paid": total_included,
            "amount_return": 0.0,
            "amount_tax": total_included - total_excluded,
            "amount_total": total_included,
            "date_order": fields.Datetime.to_string(fields.Datetime.now()),
            "fiscal_position_id": config.default_fiscal_position_id.id,
            "pricelist_id": pricelist.id,
            "name": "Tax Zakat POS Test Order",
            "last_order_preparation_change": "{}",
            "lines": [
                Command.create({
                    "id": 999001,
                    "pack_lot_ids": [],
                    "price_unit": 100.0,
                    "product_id": product.id,
                    "price_subtotal": total_excluded,
                    "price_subtotal_incl": total_included,
                    "qty": 1.0,
                    "tax_ids": [Command.set(tax.ids)],
                }),
            ],
            "partner_id": False,
            "session_id": session.id,
            "payment_ids": [
                Command.create({
                    "amount": total_included,
                    "name": fields.Datetime.now(),
                    "payment_method_id": payment_method.id,
                }),
            ],
            "uuid": "tax-zakat-pos-test-0001",
            "user_id": self.env.uid,
            "to_invoice": False,
        }
        result = pos_env["pos.order"].sync_from_ui([order_data])
        self.assertTrue(result["pos.order"])

        cash_total = sum(
            session.order_ids.payment_ids.filtered(
                lambda payment: payment.payment_method_id.is_cash_count
            ).mapped("amount")
        )
        session.post_closing_cash_details(cash_total)
        session.close_session_from_ui()

        tax_lines = session.move_id.line_ids.filtered("tax_repartition_line_id")
        self.assertTrue(tax_lines)
        self.assertTrue(all(state == "posted" for state in tax_lines.mapped("parent_state")))
        self.assertIn(session, session.move_id.pos_session_ids)
        reportable = self.env["account.move.line"].search([
            ("tax_zakat_is_reportable", "=", True),
            ("id", "in", tax_lines.ids),
        ])
        self.assertEqual(reportable, tax_lines)
