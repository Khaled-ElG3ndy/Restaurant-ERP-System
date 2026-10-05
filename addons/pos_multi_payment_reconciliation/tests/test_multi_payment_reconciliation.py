# -*- coding: utf-8 -*-

import odoo

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestMultiPaymentReconciliation(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.product100 = self.create_product("Product_100", self.categ_basic, 100, 50)
        self.config.write({"payment_method_ids": [(6, 0, (self.cash_pm1 | self.bank_pm1).ids)]})
        income_account = self.env["account.account"].search(
            [
                ("company_id", "=", self.company.id),
                ("account_type", "in", ("income", "income_other")),
            ],
            limit=1,
        )
        expense_account = self.env["account.account"].search(
            [
                ("company_id", "=", self.company.id),
                ("account_type", "=", "expense"),
            ],
            limit=1,
        )
        self.bank_pm1.journal_id.write(
            {
                "profit_account_id": income_account.id,
                "loss_account_id": expense_account.id,
            }
        )

    def test_action_multi_cash_in_out_creates_entries_per_method(self):
        session = self.open_new_session(50)
        order_data = self.create_ui_order_data(
            pos_order_lines_ui_args=[(self.product100, 1)],
            payments=[(self.cash_pm1, 60), (self.bank_pm1, 40)],
            customer=self.customer,
            uid="MPR-0001",
        )
        self.env["pos.order"].create_from_ui([order_data])

        opening_data = session.get_multi_cash_in_out_data()
        opening_by_method = {
            line["payment_method_id"]: line["expected"] for line in opening_data["lines"]
        }
        self.assertAlmostEqual(opening_by_method[self.cash_pm1.id], 110.0)
        self.assertAlmostEqual(opening_by_method[self.bank_pm1.id], 40.0)

        result = session.action_multi_cash_in_out(
            [
                {
                    "payment_method_id": self.cash_pm1.id,
                    "counted": 100.0,
                    "reason": "Cash shortage",
                },
                {
                    "payment_method_id": self.bank_pm1.id,
                    "counted": 35.0,
                    "reason": "Terminal variance",
                },
            ]
        )

        self.assertEqual(result["created_count"], 2)
        result_by_method = {
            line["payment_method_id"]: line for line in result["processed_lines"]
        }
        self.assertAlmostEqual(result_by_method[self.cash_pm1.id]["expected"], 110.0)
        self.assertAlmostEqual(result_by_method[self.cash_pm1.id]["counted"], 100.0)
        self.assertAlmostEqual(result_by_method[self.cash_pm1.id]["difference"], -10.0)
        self.assertAlmostEqual(result_by_method[self.bank_pm1.id]["expected"], 40.0)
        self.assertAlmostEqual(result_by_method[self.bank_pm1.id]["counted"], 35.0)
        self.assertAlmostEqual(result_by_method[self.bank_pm1.id]["difference"], -5.0)

        cash_adjustment = self.env["account.move"].search(
            [
                ("pos_session_id", "=", session.id),
                ("is_pos_payment_adjustment", "=", True),
                ("pos_payment_method_id", "=", self.cash_pm1.id),
            ],
            limit=1,
        )
        self.assertTrue(cash_adjustment)
        self.assertEqual(cash_adjustment.state, "posted")
        self.assertAlmostEqual(cash_adjustment.pos_adjustment_amount, -10.0)
        self.assertAlmostEqual(sum(cash_adjustment.line_ids.mapped("debit")), 100.0)
        self.assertAlmostEqual(sum(cash_adjustment.line_ids.mapped("credit")), 100.0)

        bank_adjustment = self.env["account.move"].search(
            [
                ("pos_session_id", "=", session.id),
                ("is_pos_payment_adjustment", "=", True),
                ("pos_payment_method_id", "=", self.bank_pm1.id),
            ],
            limit=1,
        )
        self.assertTrue(bank_adjustment)
        self.assertEqual(bank_adjustment.state, "posted")
        self.assertAlmostEqual(bank_adjustment.pos_adjustment_amount, -5.0)
        self.assertAlmostEqual(sum(bank_adjustment.line_ids.mapped("debit")), 35.0)
        self.assertAlmostEqual(sum(bank_adjustment.line_ids.mapped("credit")), 35.0)

        refreshed_data = session.get_multi_cash_in_out_data()
        refreshed_by_method = {
            line["payment_method_id"]: line["expected"] for line in refreshed_data["lines"]
        }
        self.assertAlmostEqual(refreshed_by_method[self.cash_pm1.id], 100.0)
        self.assertAlmostEqual(refreshed_by_method[self.bank_pm1.id], 35.0)

        closing_data = session.get_closing_control_data()
        self.assertAlmostEqual(closing_data["default_cash_details"]["amount"], 100.0)
        closing_bank_method = next(
            payment_method
            for payment_method in closing_data["other_payment_methods"]
            if payment_method["id"] == self.bank_pm1.id
        )
        self.assertAlmostEqual(closing_bank_method["amount"], 35.0)

    def test_get_multi_cash_in_out_data_includes_methods_without_activity(self):
        self.config.write(
            {"payment_method_ids": [(6, 0, (self.cash_pm1 | self.cash_pm2 | self.bank_pm1).ids)]}
        )
        session = self.open_new_session(50)

        opening_data = session.get_multi_cash_in_out_data()
        opening_by_method = {
            line["payment_method_id"]: line["expected"] for line in opening_data["lines"]
        }

        self.assertIn(self.cash_pm1.id, opening_by_method)
        self.assertIn(self.cash_pm2.id, opening_by_method)
        self.assertIn(self.bank_pm1.id, opening_by_method)
        self.assertAlmostEqual(opening_by_method[self.cash_pm1.id], 50.0)
        self.assertAlmostEqual(opening_by_method[self.cash_pm2.id], 0.0)
        self.assertAlmostEqual(opening_by_method[self.bank_pm1.id], 0.0)

    def test_action_multi_cash_in_out_creates_entries_for_no_change_lines(self):
        session = self.open_new_session(50)
        order_data = self.create_ui_order_data(
            pos_order_lines_ui_args=[(self.product100, 1)],
            payments=[(self.cash_pm1, 60), (self.bank_pm1, 40)],
            customer=self.customer,
            uid="MPR-0002",
        )
        self.env["pos.order"].create_from_ui([order_data])

        result = session.action_multi_cash_in_out(
            [
                {
                    "payment_method_id": self.cash_pm1.id,
                    "counted": 110.0,
                    "reason": "Matched cash balance",
                },
                {
                    "payment_method_id": self.bank_pm1.id,
                    "counted": 40.0,
                    "reason": "Matched bank balance",
                },
            ]
        )

        self.assertEqual(result["created_count"], 2)

        cash_adjustment = self.env["account.move"].search(
            [
                ("pos_session_id", "=", session.id),
                ("is_pos_payment_adjustment", "=", True),
                ("pos_payment_method_id", "=", self.cash_pm1.id),
                ("pos_adjustment_reason", "=", "Matched cash balance"),
            ],
            limit=1,
        )
        self.assertTrue(cash_adjustment)
        self.assertEqual(cash_adjustment.state, "posted")
        self.assertAlmostEqual(cash_adjustment.pos_adjustment_amount, 0.0)
        self.assertAlmostEqual(sum(cash_adjustment.line_ids.mapped("debit")), 110.0)
        self.assertAlmostEqual(sum(cash_adjustment.line_ids.mapped("credit")), 110.0)

        bank_adjustment = self.env["account.move"].search(
            [
                ("pos_session_id", "=", session.id),
                ("is_pos_payment_adjustment", "=", True),
                ("pos_payment_method_id", "=", self.bank_pm1.id),
                ("pos_adjustment_reason", "=", "Matched bank balance"),
            ],
            limit=1,
        )
        self.assertTrue(bank_adjustment)
        self.assertEqual(bank_adjustment.state, "posted")
        self.assertAlmostEqual(bank_adjustment.pos_adjustment_amount, 0.0)
        self.assertAlmostEqual(sum(bank_adjustment.line_ids.mapped("debit")), 40.0)
        self.assertAlmostEqual(sum(bank_adjustment.line_ids.mapped("credit")), 40.0)
