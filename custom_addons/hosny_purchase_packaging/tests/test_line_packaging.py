from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseLinePackaging(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.kg = cls.env.ref("uom.product_uom_kgm")
        cls.gram = cls.env.ref("uom.product_uom_gram")
        cls.unit = cls.env.ref("uom.product_uom_unit")
        payable_account = cls.env["account.account"].search(
            [
                ("account_type", "=", "liability_payable"),
                ("company_ids", "in", cls.company.id),
            ],
            limit=1,
        )
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Line Packaging Test Vendor",
                "supplier_rank": 1,
                "property_account_payable_id": payable_account.id,
                "property_supplier_payment_term_id": cls.env.ref(
                    "account.account_payment_term_immediate"
                ).id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Line Packaging Test Product",
                "purchase_ok": True,
                "sale_ok": False,
                "is_storable": True,
                "uom_id": cls.kg.id,
                "purchase_method": "purchase",
            }
        )
        Type = cls.env["hosny.packaging.type"]
        cls.bag_type = Type.create(
            {"name": "Test Bag Per Line", "company_id": cls.company.id}
        )
        cls.carton_type = Type.create(
            {"name": "Test Carton Per Line", "company_id": cls.company.id}
        )
        cls.box_type = Type.create(
            {"name": "Test Box Per Line", "company_id": cls.company.id}
        )
        cls.shrink_type = Type.create(
            {"name": "Test Shrink Per Line", "company_id": cls.company.id}
        )
        cls.pallet_type = Type.create(
            {"name": "Test Pallet Per Line", "company_id": cls.company.id}
        )

    def _new_order(self):
        values = {
            "partner_id": self.vendor.id,
            "company_id": self.company.id,
            "payment_term_id": self.env.ref(
                "account.account_payment_term_immediate"
            ).id,
        }
        if "analytic_account_id" in self.env["purchase.order"]._fields:
            analytic = self.env["account.analytic.account"].search(
                [("company_id", "in", [False, self.company.id])], limit=1
            )
            if analytic:
                values["analytic_account_id"] = analytic.id
        return self.env["purchase.order"].create(values)

    def _create_packaging_line(
        self,
        order,
        *,
        outer_qty,
        content_qty,
        content_uom,
        price_method="package",
        input_price=20.0,
        inner_qty=0.0,
    ):
        values = {
            "order_id": order.id,
            "product_id": self.product.id,
            "hosny_line_packaging_enabled": True,
            "hosny_outer_packaging_type_id": (
                self.carton_type.id if inner_qty else self.bag_type.id
            ),
            "hosny_outer_package_qty": outer_qty,
            "hosny_line_content_qty": content_qty,
            "hosny_line_content_uom_id": content_uom.id,
            "hosny_packaging_price_method": price_method,
            "hosny_packaging_input_price": input_price,
        }
        if inner_qty:
            values.update(
                hosny_has_inner_packaging=True,
                hosny_inner_packaging_type_id=self.bag_type.id,
                hosny_inner_package_qty=inner_qty,
            )
        return self.env["purchase.order.line"].create(values)

    def _create_saved_template(self, name, grams):
        return self.env["hosny.purchase.packaging.template"].create(
            {
                "name": name,
                "product_tmpl_id": self.product.product_tmpl_id.id,
                "company_id": self.company.id,
                "main_packaging_type_id": self.carton_type.id,
                "line_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "content_type": "packaging",
                            "packaging_type_id": self.box_type.id,
                            "quantity": 6,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "content_type": "base_uom",
                            "quantity": grams,
                            "final_uom_id": self.gram.id,
                        }
                    ),
                ],
            }
        )

    def test_saved_templates_switch_and_purchase_snapshot_are_independent(self):
        template_600 = self._create_saved_template("Carton 6 x 600", 600)
        template_800 = self._create_saved_template("Carton 6 x 800", 800)

        self.assertAlmostEqual(template_600.final_base_qty, 3.6)
        self.assertAlmostEqual(template_800.final_base_qty, 4.8)
        self.assertAlmostEqual(
            template_600.line_ids.filtered("is_final_level").base_uom_factor,
            0.001,
        )
        self.assertTrue(template_600.details_button)
        self.assertIn(self.carton_type.display_name, template_600.summary)
        self.assertIn(self.box_type.display_name, template_600.summary)
        self.assertIn("600", template_600.summary)

        draft_line = self.env["purchase.order.line"].new(
            {
                "order_id": self._new_order().id,
                "product_id": self.product.id,
                "hosny_outer_package_qty": 2,
                "hosny_packaging_price_method": "package",
                "hosny_packaging_input_price": 20,
            }
        )
        draft_line.hosny_purchase_packaging_template_id = template_600
        draft_line._onchange_hosny_purchase_packaging_template_id()
        self.assertAlmostEqual(draft_line.hosny_line_base_qty, 7.2)

        draft_line.hosny_purchase_packaging_template_id = template_800
        draft_line._onchange_hosny_purchase_packaging_template_id()
        self.assertAlmostEqual(draft_line.hosny_line_base_qty, 9.6)
        self.assertEqual(draft_line.hosny_outer_package_qty, 2)

        saved_line = self.env["purchase.order.line"].create(
            {
                "order_id": self._new_order().id,
                "product_id": self.product.id,
                "hosny_purchase_packaging_template_id": template_800.id,
                "hosny_line_packaging_enabled": True,
                "hosny_outer_packaging_type_id": template_800.main_packaging_type_id.id,
                "hosny_outer_package_qty": 2,
                "hosny_packaging_level_ids": template_800._snapshot_level_commands(),
                "hosny_packaging_price_method": "package",
                "hosny_packaging_input_price": 20,
            }
        )
        self.assertAlmostEqual(saved_line.product_qty, 9.6)
        saved_line.hosny_packaging_level_ids.filtered("is_final_level").write(
            {"quantity": 750}
        )
        self.assertAlmostEqual(saved_line.product_qty, 9.0)
        self.assertEqual(
            template_800.line_ids.filtered("is_final_level").quantity,
            800,
        )

        template_800.line_ids.filtered("is_final_level").write({"quantity": 700})
        self.assertAlmostEqual(template_800.final_base_qty, 4.2)
        self.assertAlmostEqual(saved_line.product_qty, 9.0)

        saved_line.hosny_purchase_packaging_template_id = False
        saved_line._onchange_hosny_purchase_packaging_template_id()
        self.assertAlmostEqual(saved_line.product_qty, 9.0)
        self.assertEqual(len(saved_line.hosny_packaging_level_ids), 2)

    def test_simple_gram_to_kg_and_package_price(self):
        line = self._create_packaging_line(
            self._new_order(),
            outer_qty=10,
            content_qty=600,
            content_uom=self.gram,
            price_method="package",
            input_price=20,
        )
        self.assertEqual(line.product_uom_id, self.kg)
        self.assertAlmostEqual(line.product_qty, 6.0)
        self.assertAlmostEqual(line.product_uom_qty, 6.0)
        self.assertAlmostEqual(line.price_unit, 200.0 / 6.0)
        self.assertAlmostEqual(line.price_subtotal, 200.0)
        self.assertIn("= 6", line.hosny_line_packaging_summary)

    def test_reopen_update_and_disable_keeps_standard_line_editable(self):
        line = self._create_packaging_line(
            self._new_order(),
            outer_qty=10,
            content_qty=600,
            content_uom=self.gram,
            price_method="package",
            input_price=20,
        )
        line_id = line.id
        reopened = self.env["purchase.order.line"].browse(line_id)
        self.assertEqual(reopened.hosny_outer_package_qty, 10)
        self.assertEqual(reopened.hosny_line_content_qty, 600)
        self.assertEqual(reopened.hosny_line_content_uom_id, self.gram)
        self.assertEqual(reopened.hosny_packaging_input_price, 20)

        reopened.write({"hosny_outer_package_qty": 12})
        self.assertAlmostEqual(reopened.product_qty, 7.2)
        self.assertAlmostEqual(reopened.price_subtotal, 240.0)
        self.assertIn("= 7.2", reopened.hosny_line_packaging_summary)

        reopened.write({"hosny_line_packaging_enabled": False})
        self.assertFalse(reopened.hosny_outer_packaging_type_id)
        self.assertEqual(reopened.hosny_outer_package_qty, 0.0)
        self.assertFalse(reopened.hosny_has_inner_packaging)
        self.assertFalse(reopened.hosny_inner_packaging_type_id)
        self.assertEqual(reopened.hosny_inner_package_qty, 0.0)
        self.assertEqual(reopened.hosny_line_content_qty, 0.0)
        self.assertFalse(reopened.hosny_line_content_uom_id)
        self.assertEqual(reopened.hosny_packaging_input_price, 0.0)
        self.assertFalse(reopened.hosny_line_packaging_summary)

        reopened.write(
            {
                "product_qty": 3,
                "product_uom_id": self.kg.id,
                "price_unit": 11,
            }
        )
        self.assertEqual(reopened.product_qty, 3)
        self.assertEqual(reopened.price_subtotal, 33)

    def test_hierarchy_and_base_uom_price(self):
        line = self._create_packaging_line(
            self._new_order(),
            outer_qty=4,
            inner_qty=6,
            content_qty=600,
            content_uom=self.gram,
            price_method="base_uom",
            input_price=30,
        )
        self.assertAlmostEqual(line.product_qty, 14.4)
        self.assertAlmostEqual(line.price_unit, 30.0)
        self.assertAlmostEqual(line.price_subtotal, 432.0)
        self.assertIn("4", line.hosny_line_packaging_summary)
        self.assertIn("6", line.hosny_line_packaging_summary)
        self.assertIn("14.4", line.hosny_line_packaging_summary)

    def test_carton_six_boxes_six_hundred_grams_reopens_unchanged(self):
        line = self.env["purchase.order.line"].create(
            {
                "order_id": self._new_order().id,
                "product_id": self.product.id,
                "hosny_line_packaging_enabled": True,
                "hosny_outer_packaging_type_id": self.carton_type.id,
                "hosny_outer_package_qty": 1,
                "hosny_packaging_level_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "content_type": "packaging",
                            "packaging_type_id": self.box_type.id,
                            "quantity": 6,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "content_type": "base_uom",
                            "quantity": 600,
                            "final_uom_id": self.gram.id,
                        }
                    ),
                ],
                "hosny_packaging_price_method": "package",
                "hosny_packaging_input_price": 20,
            }
        )

        line.flush_recordset()
        line.invalidate_recordset()
        reopened = self.env["purchase.order.line"].browse(line.id)
        levels = reopened.hosny_packaging_level_ids.sorted("sequence")
        self.assertEqual(len(levels), 2)
        self.assertEqual(levels[0].content_type, "packaging")
        self.assertEqual(levels[0].packaging_type_id, self.box_type)
        self.assertEqual(levels[0].quantity, 6)
        self.assertEqual(levels[1].content_type, "base_uom")
        self.assertFalse(levels[1].packaging_type_id)
        self.assertEqual(levels[1].quantity, 600)
        self.assertEqual(levels[1].final_uom_id, self.gram)
        self.assertAlmostEqual(reopened.hosny_main_package_base_qty, 3.6)
        self.assertAlmostEqual(reopened.product_qty, 3.6)

    def test_final_reference_ux_scenario_and_tax_totals(self):
        purchase_tax = self.env["account.tax"].create(
            {
                "name": "Packaging UX Purchase 15%",
                "amount": 15,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "company_id": self.company.id,
            }
        )
        line = self.env["purchase.order.line"].create(
            {
                "order_id": self._new_order().id,
                "product_id": self.product.id,
                "hosny_line_packaging_enabled": True,
                "hosny_outer_packaging_type_id": self.carton_type.id,
                "hosny_outer_package_qty": 10,
                "hosny_packaging_level_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "content_type": "packaging",
                            "packaging_type_id": self.shrink_type.id,
                            "quantity": 6,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "content_type": "packaging",
                            "packaging_type_id": self.bag_type.id,
                            "quantity": 6,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 30,
                            "content_type": "base_uom",
                            "quantity": 400,
                            "final_uom_id": self.gram.id,
                        }
                    ),
                ],
                "hosny_packaging_price_method": "package",
                "hosny_packaging_input_price": 100,
                "tax_ids": [Command.set(purchase_tax.ids)],
            }
        )
        self.assertAlmostEqual(line.hosny_main_package_base_qty, 14.4)
        self.assertAlmostEqual(line.product_qty, 144.0)
        self.assertAlmostEqual(line.price_unit, 100 / 14.4)
        self.assertAlmostEqual(line.price_subtotal, 1000.0)
        self.assertAlmostEqual(line.price_total, 1150.0)
        self.assertIn("10", line.hosny_line_packaging_summary)
        self.assertIn("144", line.hosny_line_packaging_summary)
        self.assertIn("14.4000", line.hosny_summary_package_content)
        self.assertIn("1,150.00", line.hosny_summary_total)

        with self.assertRaises(ValidationError):
            line.write(
                {
                    "hosny_packaging_level_ids": [
                        Command.update(
                            line.hosny_packaging_level_ids[-1].id,
                            {"sequence": 5},
                        )
                    ]
                }
            )

        with self.assertRaises(ValidationError):
            line.write(
                {
                    "hosny_packaging_level_ids": [
                        Command.create(
                            {
                                "sequence": 25,
                                "content_type": "packaging",
                                "packaging_type_id": self.carton_type.id,
                                "quantity": 2,
                            }
                        )
                    ]
                }
            )

    def test_unlimited_line_levels_recalculate_recursively(self):
        line = self.env["purchase.order.line"].create(
            {
                "order_id": self._new_order().id,
                "product_id": self.product.id,
                "hosny_line_packaging_enabled": True,
                "hosny_outer_packaging_type_id": self.pallet_type.id,
                "hosny_outer_package_qty": 2,
                "hosny_packaging_level_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "content_type": "packaging",
                            "packaging_type_id": self.carton_type.id,
                            "quantity": 50,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 20,
                            "content_type": "packaging",
                            "packaging_type_id": self.shrink_type.id,
                            "quantity": 4,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 30,
                            "content_type": "packaging",
                            "packaging_type_id": self.bag_type.id,
                            "quantity": 6,
                        }
                    ),
                    Command.create(
                        {
                            "sequence": 40,
                            "content_type": "base_uom",
                            "quantity": 600,
                            "final_uom_id": self.gram.id,
                        }
                    ),
                ],
                "hosny_packaging_price_method": "package",
                "hosny_packaging_input_price": 100,
            }
        )
        self.assertEqual(len(line.hosny_packaging_level_ids), 4)
        self.assertAlmostEqual(line.product_qty, 1440.0)
        self.assertAlmostEqual(line.price_subtotal, 200.0)
        levels = line.hosny_packaging_level_ids.sorted("sequence")
        self.assertEqual(levels[0].content_type, "packaging")
        self.assertEqual(levels[0].packaging_type_id, self.carton_type)
        self.assertEqual(levels[-1].content_type, "base_uom")
        self.assertEqual(levels[-1].final_uom_id, self.gram)
        self.assertAlmostEqual(line.hosny_main_package_base_qty, 720.0)
        for name in ("Pallet", "Carton", "Shrink", "Bag"):
            self.assertIn(name, line.hosny_line_packaging_summary)

        carton = line.hosny_packaging_level_ids.filtered(
            lambda level: level.packaging_type_id == self.carton_type
        )
        carton.write({"quantity": 60})
        self.assertAlmostEqual(line.product_qty, 1728.0)
        self.assertAlmostEqual(line.price_subtotal, 200.0)

        with self.assertRaises(ValidationError):
            line.write(
                {
                    "hosny_packaging_level_ids": [
                        Command.create(
                            {
                                "sequence": 50,
                                "content_type": "packaging",
                                "packaging_type_id": self.bag_type.id,
                                "quantity": 2,
                            }
                        )
                    ]
                }
            )

    def test_levels_enable_packaging_automatically_and_clear_disables_it(self):
        line = self.env["purchase.order.line"].create(
            {
                "order_id": self._new_order().id,
                "product_id": self.product.id,
                "hosny_outer_packaging_type_id": self.bag_type.id,
                "hosny_outer_package_qty": 10,
                "hosny_packaging_level_ids": [
                    Command.create(
                        {
                            "sequence": 10,
                            "content_type": "base_uom",
                            "quantity": 600,
                            "final_uom_id": self.gram.id,
                        }
                    )
                ],
                "hosny_packaging_price_method": "package",
                "hosny_packaging_input_price": 20,
            }
        )
        self.assertTrue(line.hosny_line_packaging_enabled)
        self.assertEqual(line.hosny_line_content_qty, 600)
        self.assertEqual(line.hosny_line_content_uom_id, self.gram)
        self.assertEqual(line.hosny_packaging_input_price, 20)
        self.assertAlmostEqual(line.product_qty, 6.0)
        self.assertAlmostEqual(line.price_subtotal, 200.0)

        line.write({"hosny_packaging_level_ids": [Command.clear()]})
        self.assertFalse(line.hosny_line_packaging_enabled)
        self.assertFalse(line.hosny_packaging_level_ids)
        self.assertFalse(line.hosny_line_packaging_summary)

    def test_legacy_two_level_values_are_upgraded_to_level_records(self):
        line = self._create_packaging_line(
            self._new_order(),
            outer_qty=4,
            inner_qty=6,
            content_qty=600,
            content_uom=self.gram,
        )
        self.assertEqual(len(line.hosny_packaging_level_ids), 2)
        levels = line.hosny_packaging_level_ids.sorted("sequence")
        self.assertEqual(line.hosny_outer_packaging_type_id, self.carton_type)
        self.assertEqual(levels[0].packaging_type_id, self.bag_type)
        self.assertEqual(levels[1].content_type, "base_uom")
        self.assertEqual(levels[1].final_uom_id, self.gram)

    def test_each_line_has_independent_content_uom(self):
        order = self._new_order()
        gram_line = self._create_packaging_line(
            order, outer_qty=10, content_qty=600, content_uom=self.gram
        )
        kg_line = self._create_packaging_line(
            order, outer_qty=2, content_qty=3, content_uom=self.kg
        )
        self.assertAlmostEqual(gram_line.product_qty, 6.0)
        self.assertAlmostEqual(kg_line.product_qty, 6.0)
        self.assertEqual(gram_line.hosny_line_content_uom_id, self.gram)
        self.assertEqual(kg_line.hosny_line_content_uom_id, self.kg)

    def test_standard_line_stays_standard(self):
        line = self.env["purchase.order.line"].create(
            {
                "order_id": self._new_order().id,
                "product_id": self.product.id,
                "product_qty": 3,
                "product_uom_id": self.kg.id,
                "price_unit": 15,
            }
        )
        self.assertFalse(line.hosny_line_packaging_enabled)
        self.assertFalse(line.hosny_line_packaging_summary)
        self.assertEqual(line.product_qty, 3)
        self.assertEqual(line.price_subtotal, 45)

    def test_validations_and_product_change_cleanup(self):
        order = self._new_order()
        with self.assertRaises(ValidationError):
            self._create_packaging_line(
                order, outer_qty=0, content_qty=600, content_uom=self.gram
            )
        with self.assertRaises(ValidationError):
            self._create_packaging_line(
                order, outer_qty=10, content_qty=0, content_uom=self.gram
            )
        with self.assertRaises(ValidationError):
            self._create_packaging_line(
                order, outer_qty=10, content_qty=1, content_uom=self.unit
            )
        line = self._create_packaging_line(
            order,
            outer_qty=4,
            inner_qty=6,
            content_qty=600,
            content_uom=self.gram,
        )
        with self.assertRaises(ValidationError):
            line.write({"hosny_inner_packaging_type_id": self.carton_type.id})

        other_product = self.env["product.product"].create(
            {
                "name": "Line Packaging Other Product",
                "purchase_ok": True,
                "uom_id": self.kg.id,
            }
        )
        line.write({"product_id": other_product.id})
        self.assertFalse(line.hosny_line_packaging_enabled)
        self.assertFalse(line.hosny_line_packaging_summary)

    def test_product_uom_change_is_protected(self):
        self._create_packaging_line(
            self._new_order(),
            outer_qty=10,
            content_qty=600,
            content_uom=self.gram,
        )
        with self.assertRaises(ValidationError):
            self.product.product_tmpl_id.write({"uom_id": self.unit.id})

    def test_confirmation_receipt_and_bill_snapshot_values(self):
        order = self._new_order()
        line = self._create_packaging_line(
            order,
            outer_qty=10,
            content_qty=600,
            content_uom=self.gram,
            price_method="package",
            input_price=20,
        )
        order.button_confirm()
        move = order.picking_ids.move_ids.filtered(lambda item: item.product_id == self.product)
        self.assertEqual(len(move), 1)
        self.assertAlmostEqual(move.product_uom_qty, 6.0)
        self.assertEqual(move.product_uom, self.kg)
        self.assertEqual(move.hosny_line_packaging_summary, line.hosny_line_packaging_summary)

        bill_line_values = line._prepare_account_move_line()
        self.assertTrue(bill_line_values["hosny_line_packaging_enabled"])
        self.assertAlmostEqual(bill_line_values["quantity"], 6.0)
        self.assertAlmostEqual(
            bill_line_values["hosny_packaging_unit_base_qty"], 0.6
        )
        self.assertEqual(
            bill_line_values["hosny_line_packaging_summary"],
            line.hosny_line_packaging_summary,
        )

        invoice_values = order._prepare_invoice()
        invoice_date = fields.Date.context_today(order)
        invoice_values.update(
            invoice_date=invoice_date,
            date=invoice_date,
            invoice_date_due=invoice_date,
            invoice_line_ids=[Command.create(bill_line_values)],
        )
        bill = self.env["account.move"].with_context(
            default_move_type="in_invoice"
        ).create(invoice_values)
        bill_line = bill.invoice_line_ids.filtered(
            lambda item: item.product_id == self.product
        )
        self.assertEqual(len(bill_line), 1)
        self.assertAlmostEqual(bill_line.quantity, 6.0)
        self.assertAlmostEqual(bill_line.hosny_invoice_packaging_qty, 10.0)
        bill.action_post()
        credit_note = bill._reverse_moves()
        credit_line = credit_note.invoice_line_ids.filtered(
            lambda item: item.product_id == self.product
        )
        self.assertTrue(credit_line.hosny_line_packaging_enabled)
        self.assertEqual(
            credit_line.hosny_line_packaging_summary,
            line.hosny_line_packaging_summary,
        )
        credit_note.invoice_date = invoice_date
        credit_note.action_post()
        self.assertEqual(credit_note.state, "posted")

    def test_duplicate_product_packagings_warn_and_stay_separate(self):
        order = self._new_order()
        first_line = self._create_packaging_line(
            order,
            outer_qty=10,
            content_qty=600,
            content_uom=self.gram,
            input_price=20,
        )
        second_line = self._create_packaging_line(
            order,
            outer_qty=4,
            content_qty=500,
            content_uom=self.gram,
            input_price=30,
            inner_qty=2,
        )

        self.assertEqual(len(order.order_line), 2)
        self.assertNotEqual(
            first_line.hosny_outer_packaging_type_id,
            second_line.hosny_outer_packaging_type_id,
        )
        self.assertAlmostEqual(first_line.product_qty, 6.0)
        self.assertAlmostEqual(second_line.product_qty, 4.0)

        onchange_warning = second_line._onchange_hosny_purchase_line_product_validation()
        self.assertEqual(onchange_warning["warning"]["type"], "dialog")
        self.assertEqual(
            onchange_warning["warning"]["message"],
            f"The product {self.product.display_name} already exists on another purchase line.",
        )

        warning_action = order.button_confirm()
        self.assertEqual(
            warning_action["res_model"],
            "hosny.duplicate.purchase.line.warning",
        )
        self.assertEqual(order.state, "draft")
        warning = self.env[warning_action["res_model"]].browse(
            warning_action["res_id"]
        )
        self.assertEqual(warning.duplicate_line_ids, second_line)
        self.assertIn(self.product.display_name, warning.warning_message)

        warning.action_continue()
        self.assertEqual(order.state, "purchase")
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(set(order.order_line.ids), {first_line.id, second_line.id})
        self.assertTrue(second_line.hosny_duplicate_warning_acknowledged)
        product_moves = order.picking_ids.move_ids.filtered(
            lambda move: move.product_id == self.product
        )
        self.assertEqual(len(product_moves), 2)
        self.assertEqual(
            set(product_moves.purchase_line_id.ids),
            {first_line.id, second_line.id},
        )

    def test_partial_receipt_creates_base_quantity_backorder(self):
        order = self._new_order()
        self._create_packaging_line(
            order,
            outer_qty=10,
            content_qty=600,
            content_uom=self.gram,
        )
        order.button_confirm()
        picking = order.picking_ids
        picking.move_ids.quantity = 2.0
        picking.with_context(skip_backorder=True).button_validate()
        self.assertEqual(picking.state, "done")
        backorder = picking.backorder_ids
        self.assertTrue(backorder)
        self.assertAlmostEqual(backorder.move_ids.product_uom_qty, 4.0)
        self.assertEqual(backorder.move_ids.product_uom, self.kg)
