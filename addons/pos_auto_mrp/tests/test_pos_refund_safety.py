# -*- coding: utf-8 -*-

import json

import odoo

from odoo import Command
from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install", "pos_auto_mrp_return")
class TestPosRefundSafety(TestPoSCommon):

    @classmethod
    def _create_basic_config(cls):
        """Honor the deployment's required POS analytic account in core POS fixtures."""
        plan = cls.env["account.analytic.plan"].search([], limit=1)
        if not plan:
            plan = cls.env["account.analytic.plan"].create({"name": "POS Test Plan"})
        analytic = cls.env["account.analytic.account"].create({
            "name": "POS Refund Safety",
            "plan_id": plan.id,
            "company_id": cls.env.company.id,
        })
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                default_analytic_account_id=analytic.id,
            )
        )
        return super()._create_basic_config()

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.open_new_session()
        self.product = self.create_product("Refund Safety Product", self.categ_basic, 10.0, 5.0)

    def test_sync_from_ui_drops_missing_refunded_orderline_id(self):
        order_data = self.create_ui_order_data(
            [{
                "product": self.product,
                "quantity": -1,
                "discount": 0.0,
                "refunded_orderline_id": 999999999,
            }],
            payments=[(self.cash_pm1, -10.0)],
            uuid="refund-safety-invalid-link",
        )

        result = self.env["pos.order"].sync_from_ui([order_data])

        order = self.env["pos.order"].browse(result["pos.order"][0]["id"])
        self.assertTrue(order.exists())
        self.assertEqual(len(order.lines), 1)
        self.assertFalse(order.lines.refunded_orderline_id)

    def test_write_drops_missing_refunded_orderline_id(self):
        order_data = self.create_ui_order_data(
            [(self.product, 1)],
            payments=[(self.cash_pm1, 10.0)],
            uuid="refund-safety-write-check",
        )
        result = self.env["pos.order"].sync_from_ui([order_data])
        order = self.env["pos.order"].browse(result["pos.order"][0]["id"])
        line = order.lines

        line.write({"refunded_orderline_id": 999999999})

        self.assertFalse(line.refunded_orderline_id)

    def test_pos_ui_refund_skips_unbuild_when_original_mo_never_completed(self):
        self._check_uncompleted_mo_sale_and_refund(self.env)

    def test_pos_only_cashier_pays_when_components_are_missing(self):
        self._check_uncompleted_mo_sale_and_refund(self.env(user=self._pos_cashier()))

    def _check_uncompleted_mo_sale_and_refund(self, env):
        self.config.write({
            "auto_create_mrp_from_pos": True,
            "auto_done_mrp_from_pos": True,
        })
        component = self.env["product.product"].create({
            "name": "Unavailable POS UI Component",
            "is_storable": True,
        })
        self.env["mrp.bom"].create({
            "product_tmpl_id": self.product.product_tmpl_id.id,
            "product_id": self.product.id,
            "product_qty": 1,
            "product_uom_id": self.product.uom_id.id,
            "type": "normal",
            "bom_line_ids": [Command.create({
                "product_id": component.id,
                "product_qty": 2,
                "product_uom_id": component.uom_id.id,
            })],
        })

        sale_data = self.create_ui_order_data(
            [{
                "product": self.product,
                "quantity": 1,
                "discount": 0.0,
                "uuid": "pos-ui-uncompleted-mo-sale-line",
            }],
            payments=[(self.cash_pm1, 10.0)],
            uuid="pos-ui-uncompleted-mo-sale",
        )
        sale_result = self._send_then_pay(env, sale_data)
        sale = self.env["pos.order"].browse(sale_result["pos.order"][0]["id"])
        production = sale.lines.mrp_production_ids
        self.assertEqual(production.state, "draft")
        self.assertEqual(production.qty_produced, 0)

        refund_data = self.create_ui_order_data(
            [{
                "product": self.product,
                "quantity": -1,
                "discount": 0.0,
                "refunded_orderline_id": sale.lines.id,
            }],
            pos_order_ui_args={"is_refund": True},
            payments=[(self.cash_pm1, -10.0)],
            uuid="pos-ui-uncompleted-mo-refund",
        )
        refund_result = env["pos.order"].sync_from_ui([refund_data])
        refund = self.env["pos.order"].browse(refund_result["pos.order"][0]["id"])

        self.assertEqual(refund.state, "paid")
        self.assertEqual(refund.picking_ids.state, "done")
        self.assertFalse(refund.lines.pos_auto_mrp_refund_allocation_ids)
        self.assertFalse(refund.lines.mrp_unbuild_id)

    def _setup_routed_bom_product(self):
        """Give self.product a BoM whose components sit in a routed POS section."""
        self.config.write({
            "auto_create_mrp_from_pos": True,
            "auto_done_mrp_from_pos": True,
        })
        self.pos_session.update_stock_at_closing = False
        pos_stock = self.config.picking_type_id.default_location_src_id
        component_source = self.env["stock.location"].create({
            "name": "POS UI Routed Components",
            "location_id": pos_stock.id,
            "usage": "internal",
        })
        routes = []
        configs = self.env["pos.mrp.source.profile"]._get_routed_pos_configs()
        for config in configs:
            location = component_source
            if config != self.config:
                location = self.env["stock.location"].create({
                    "name": "POS UI Routed Components %s" % config.id,
                    "location_id": config.picking_type_id.default_location_src_id.id,
                    "usage": "internal",
                })
            routes.append(Command.create({
                "pos_config_id": config.id,
                "location_id": location.id,
            }))
        profile = self.env["pos.mrp.source.profile"].create({
            "name": "POS UI Routed Source",
            "route_ids": routes,
        })
        component = self.env["product.product"].create({
            "name": "POS UI Routed Component",
            "type": "consu",
            "is_storable": True,
        })
        self.product.product_tmpl_id.pos_mrp_source_profile_id = profile.id
        self.env["mrp.bom"].create({
            "product_tmpl_id": self.product.product_tmpl_id.id,
            "product_id": self.product.id,
            "product_qty": 1,
            "product_uom_id": self.product.uom_id.id,
            "type": "normal",
            "bom_line_ids": [Command.create({
                "product_id": component.id,
                "product_qty": 2,
                "product_uom_id": component.uom_id.id,
            })],
        })
        self.env["stock.quant"]._update_available_quantity(
            component, component_source, 10
        )
        return component_source

    def _send_then_pay(self, env, order_data):
        """Sync like a branch till: sent to the kitchen as a draft, paid later.

        Each sync is its own request, so the cache is dropped in between; the
        payment then reads the already-stored lines from the database.  The
        data goes through JSON like the RPC does (commands become lists).
        """
        order_data = json.loads(json.dumps(order_data, default=str))
        draft = json.loads(json.dumps(order_data))
        draft.update(state="draft", payment_ids=[], amount_paid=0.0)
        sent = env["pos.order"].sync_from_ui([draft])["pos.order"][0]
        order_data["access_token"] = sent["access_token"]
        env.invalidate_all()
        result = env["pos.order"].sync_from_ui([order_data])
        env.invalidate_all()
        return result

    def _pos_cashier(self):
        """A cashier like the branch ones: POS rights, no Inventory/Manufacturing."""
        return self.env["res.users"].create({
            "name": "POS Only Cashier",
            "login": "pos_auto_mrp_cashier",
            "group_ids": [Command.set([
                self.env.ref("base.group_user").id,
                self.env.ref("point_of_sale.group_pos_user").id,
            ])],
            "company_id": self.company.id,
            "company_ids": [Command.set([self.company.id])],
        })

    def test_pos_ui_refund_unbuilds_completed_routed_mo(self):
        self._check_routed_sale_and_refund(self.env)

    def test_pos_only_cashier_sells_and_refunds_manufactured_product(self):
        cashier = self._pos_cashier()
        self.assertFalse(cashier.has_group("mrp.group_mrp_user"))
        self.assertFalse(cashier.has_group("stock.group_stock_user"))
        self._check_routed_sale_and_refund(self.env(user=cashier))

    def _check_routed_sale_and_refund(self, env):
        component_source = self._setup_routed_bom_product()

        sale_data = self.create_ui_order_data(
            [{
                "product": self.product,
                "quantity": 1,
                "discount": 0.0,
                "uuid": "pos-ui-completed-routed-mo-sale-line",
            }],
            payments=[(self.cash_pm1, 10.0)],
            uuid="pos-ui-completed-routed-mo-sale",
        )
        sale_result = self._send_then_pay(env, sale_data)
        sale = self.env["pos.order"].browse(sale_result["pos.order"][0]["id"])
        production = sale.lines.mrp_production_ids
        self.assertEqual(production.state, "done")
        self.assertEqual(production.location_dest_id, component_source)
        self.assertEqual(production.move_raw_ids.location_id, component_source)

        refund_data = self.create_ui_order_data(
            [{
                "product": self.product,
                "quantity": -1,
                "discount": 0.0,
                "refunded_orderline_id": sale.lines.id,
            }],
            pos_order_ui_args={"is_refund": True},
            payments=[(self.cash_pm1, -10.0)],
            uuid="pos-ui-completed-routed-mo-refund",
        )
        refund_result = env["pos.order"].sync_from_ui([refund_data])
        refund = self.env["pos.order"].browse(refund_result["pos.order"][0]["id"])

        self.assertEqual(refund.state, "paid")
        self.assertEqual(refund.picking_ids.state, "done")
        allocation = self.env["pos.auto.mrp.return.allocation"].search([
            ("production_id", "=", production.id),
        ])
        self.assertEqual(allocation.state, "done")
        self.assertEqual(allocation.unbuild_id.state, "done")
        self.assertEqual(allocation.unbuild_id.location_id, component_source)
        self.assertEqual(allocation.unbuild_id.location_dest_id, component_source)
