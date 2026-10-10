# -*- coding: utf-8 -*-
from uuid import uuid4

from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestOrderTypeTable(TestPoSCommon):
    """السفري بلا طاولة والطاولة تعني محلي — على مسار sync_from_ui نفسه."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.config.module_pos_restaurant = True
        OrderType = cls.env["pos.order.type"]
        cls.local = OrderType._hosny_local_type()
        cls.takeaway = OrderType._hosny_takeaway_type()
        cls.floor = cls.env["restaurant.floor"].create({
            "name": "أرضي", "pos_config_ids": [(4, cls.config.id)]})
        cls.table = cls.env["restaurant.table"].create({
            "table_number": 5, "floor_id": cls.floor.id, "seats": 4})
        cls.table_2 = cls.env["restaurant.table"].create({
            "table_number": 6, "floor_id": cls.floor.id, "seats": 4})
        cls.takeaway_floor = cls.env["restaurant.floor"].create({
            "name": "سفري", "pos_config_ids": [(4, cls.config.id)]})
        cls.takeaway_table = cls.env["restaurant.table"].create({
            "table_number": 3, "floor_id": cls.takeaway_floor.id, "seats": 1})
        cls.product = cls.create_product("أرز بسمتى", cls.categ_basic, 9.0)

    def setUp(self):
        super().setUp()
        self.open_new_session()

    def _sync(self, payments=None, customer=False, **order_vals):
        data = self.create_ui_order_data(
            [(self.product, 2)], order_vals, customer=customer, payments=payments)
        data.setdefault("access_token", str(uuid4()))
        result = self.env["pos.order"].sync_from_ui([dict(data)])
        return self.env["pos.order"].browse(result["pos.order"][0]["id"]), data

    def _resync(self, data, **changes):
        """نفس الطلب يُرسل ثانية كما تفعل الشاشة (أودو يحذف مفاتيح من القاموس)."""
        self.env["pos.order"].sync_from_ui([dict(data, lines=[], **changes)])

    def _draft(self, **order_vals):
        return self._sync(payments=[], state="draft", amount_paid=0, **order_vals)

    # ── السفري ────────────────────────────────────────────────────────────

    def test_types_exist(self):
        self.assertEqual(self.local.code, "local")
        self.assertEqual(self.takeaway.code, "safari")
        self.assertTrue(self.local._hosny_requires_table())
        self.assertFalse(self.takeaway._hosny_requires_table())

    def test_takeaway_paid_cash_has_no_table(self):
        order, _ = self._sync(order_type_id=self.takeaway.id, table_id=False,
                              payments=[(self.cash_pm1, 18.0)])
        self.assertEqual(order.state, "paid")
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertFalse(order.table_id)
        self.assertEqual(order.payment_ids.payment_method_id, self.cash_pm1)

    def test_takeaway_paid_bank_has_no_table(self):
        order, _ = self._sync(order_type_id=self.takeaway.id, payments=[(self.bank_pm1, 18.0)])
        self.assertEqual(order.state, "paid")
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertFalse(order.table_id)
        self.assertEqual(order.payment_ids.payment_method_id, self.bank_pm1)

    def test_takeaway_paid_later_has_no_table(self):
        order, _ = self._sync(order_type_id=self.takeaway.id, customer=self.customer,
                              payments=[(self.pay_later_pm, 18.0)])
        self.assertEqual(order.state, "paid")
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertFalse(order.table_id)
        self.assertEqual(order.payment_ids.payment_method_id, self.pay_later_pm)

    def test_takeaway_sent_with_a_table_loses_the_table(self):
        """النوع هو المرجع: أي طاولة تصل مع سفري تُحذف، ولا يتحول لمحلي."""
        order, _ = self._sync(order_type_id=self.takeaway.id, table_id=self.table.id,
                              payments=[(self.cash_pm1, 18.0)])
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertFalse(order.table_id)

    def test_takeaway_draft_reloads_as_takeaway(self):
        """إعادة التحميل تقرأ الطلبات المفتوحة من الخادم: يبقى سفري بلا طاولة."""
        order, _ = self._draft(order_type_id=self.takeaway.id)
        loaded = self.env["pos.order"].search(
            self.env["pos.order"]._load_pos_data_domain({}, self.config))
        self.assertIn(order, loaded)
        row = next(r for r in order._load_pos_data_read(order, self.config) if r["id"] == order.id)
        self.assertEqual(row["order_type_id"], self.takeaway.id)
        self.assertFalse(row["table_id"])

    def test_takeaway_draft_edited_then_paid_stays_takeaway(self):
        order, data = self._draft(order_type_id=self.takeaway.id)
        # نفس الطلب يُرسل ثانية ثم يُدفع — كما تفعل الشاشة
        self._resync(data, state="paid", amount_paid=data["amount_total"],
                     payment_ids=[(0, 0, {"amount": data["amount_total"], "name": "p",
                                          "payment_method_id": self.cash_pm1.id})])
        self.assertEqual(order.state, "paid")
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertFalse(order.table_id)

    def test_takeaway_orders_are_not_merged_by_table(self):
        """سفري بلا طاولة: طلبان لا يُدمجان كما يدمج أودو طلبي نفس الطاولة."""
        first, _ = self._draft(order_type_id=self.takeaway.id)
        second, _ = self._draft(order_type_id=self.takeaway.id)
        self.assertNotEqual(first, second)

    # ── بدون نوع (نقطة بيع لم يُعَد تحميلها) ────────────────────────────

    def test_untyped_without_table_is_never_local(self):
        order, _ = self._sync(order_type_id=False, payments=[(self.cash_pm1, 18.0)])
        self.assertEqual(order.order_type_id, self.takeaway)

    def test_untyped_on_a_table_is_local(self):
        order, _ = self._draft(order_type_id=False, table_id=self.table.id)
        self.assertEqual(order.order_type_id, self.local)
        self.assertEqual(order.table_id, self.table)

    def test_stale_client_cannot_erase_or_reseat_takeaway(self):
        order, data = self._draft(order_type_id=self.takeaway.id)
        self._resync(data, order_type_id=False, table_id=self.table.id)
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertFalse(order.table_id)

    # ── التبديل ──────────────────────────────────────────────────────────

    def test_switch_local_to_takeaway_clears_table(self):
        order, data = self._draft(order_type_id=self.local.id, table_id=self.table.id)
        self.assertEqual(order.table_id, self.table)
        self._resync(data, order_type_id=self.takeaway.id)
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertFalse(order.table_id)

    def test_switch_takeaway_to_local_keeps_chosen_table(self):
        order, data = self._draft(order_type_id=self.takeaway.id)
        self._resync(data, order_type_id=self.local.id, table_id=self.table_2.id)
        self.assertEqual(order.order_type_id, self.local)
        self.assertEqual(order.table_id, self.table_2)

    def test_table_without_type_seats_takeaway_as_local(self):
        order, _ = self._draft(order_type_id=self.takeaway.id)
        order.write({"table_id": self.table_2.id})
        self.assertEqual(order.order_type_id, self.local)
        self.assertEqual(order.table_id, self.table_2)

    # ── المحلي كما هو ────────────────────────────────────────────────────

    def test_local_order_keeps_table_through_payment(self):
        order, _ = self._sync(order_type_id=self.local.id, table_id=self.table.id,
                              payments=[(self.cash_pm1, 18.0)])
        self.assertEqual(order.state, "paid")
        self.assertEqual(order.order_type_id, self.local)
        self.assertEqual(order.table_id, self.table)

    def test_local_draft_on_same_table_still_matched(self):
        """سلوك أودو للمحلي لم يتغير: مسودة ثانية على نفس الطاولة تُطابق الأولى."""
        first, _ = self._draft(order_type_id=self.local.id, table_id=self.table.id)
        second, _ = self._draft(order_type_id=self.local.id, table_id=self.table.id)
        self.assertEqual(first, second)

    def test_session_closes_with_takeaway_and_local(self):
        self._sync(order_type_id=self.takeaway.id, payments=[(self.cash_pm1, 18.0)])
        self._sync(order_type_id=self.takeaway.id, payments=[(self.bank_pm1, 18.0)])
        self._sync(order_type_id=self.local.id, table_id=self.table.id,
                   payments=[(self.cash_pm1, 18.0)])
        self.pos_session.action_pos_session_validate()
        self.assertEqual(self.pos_session.state, "closed")
        self.assertTrue(all(o.state == "done" for o in self.pos_session.order_ids))

    # ── المرتجع ──────────────────────────────────────────────────────────

    def test_refund_takes_the_refunded_order_type(self):
        order, _ = self._sync(order_type_id=self.local.id, table_id=self.table.id,
                              payments=[(self.cash_pm1, 18.0)])
        line = order.lines[0]
        refund_data = self.create_ui_order_data(
            [{"product": self.product, "quantity": -2, "refunded_orderline_id": line.id}],
            {"order_type_id": self.takeaway.id, "is_refund": True},
            payments=[(self.cash_pm1, -18.0)])
        result = self.env["pos.order"].sync_from_ui([refund_data])
        refund = self.env["pos.order"].browse(
            [r["id"] for r in result["pos.order"] if r["id"] != order.id])
        self.assertTrue(refund.is_refund)
        self.assertEqual(refund.order_type_id, self.local)

    # ── طاولات «سفري» (طلبات الهاتف) ─────────────────────────────────────

    def test_takeaway_on_takeaway_table_keeps_the_table(self):
        order, _ = self._sync(order_type_id=self.takeaway.id, table_id=self.takeaway_table.id,
                              payments=[(self.cash_pm1, 18.0)])
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertEqual(order.table_id, self.takeaway_table)

    def test_untyped_or_local_on_takeaway_table_is_takeaway(self):
        untyped, _ = self._draft(order_type_id=False, table_id=self.takeaway_table.id)
        self.assertEqual(untyped.order_type_id, self.takeaway)
        self.assertEqual(untyped.table_id, self.takeaway_table)
        local, _ = self._draft(order_type_id=self.local.id, table_id=self.takeaway_table.id)
        self.assertEqual(local.order_type_id, self.takeaway)
        self.assertEqual(local.table_id, self.takeaway_table)

    def test_takeaway_table_draft_resynced_then_paid_keeps_table(self):
        order, data = self._draft(order_type_id=self.takeaway.id, table_id=self.takeaway_table.id)
        self._resync(data, state="paid", amount_paid=data["amount_total"],
                     payment_ids=[(0, 0, {"amount": data["amount_total"], "name": "p",
                                          "payment_method_id": self.cash_pm1.id})])
        self.assertEqual(order.state, "paid")
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertEqual(order.table_id, self.takeaway_table)

    def test_type_only_write_keeps_takeaway_table(self):
        order, _ = self._draft(order_type_id=self.takeaway.id, table_id=self.takeaway_table.id)
        order.write({"order_type_id": self.takeaway.id})
        self.assertEqual(order.table_id, self.takeaway_table)

    def test_moving_to_takeaway_table_makes_it_takeaway(self):
        order, _ = self._draft(order_type_id=self.local.id, table_id=self.table.id)
        order.write({"table_id": self.takeaway_table.id})
        self.assertEqual(order.order_type_id, self.takeaway)
        self.assertEqual(order.table_id, self.takeaway_table)
