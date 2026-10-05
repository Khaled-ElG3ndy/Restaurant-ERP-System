from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHierarchicalPurchasePackaging(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.unit = cls.env.ref("uom.product_uom_unit")
        cls.product = cls.env["product.product"].create(
            {
                "name": "Hierarchical Packaging Test Water",
                "purchase_ok": True,
                "sale_ok": False,
                "is_storable": True,
                "uom_id": cls.unit.id,
                "purchase_method": "receive",
            }
        )
        Type = cls.env["hosny.packaging.type"]
        cls.shrink_type = Type.create(
            {"name": "Shrink", "company_id": cls.company.id}
        )
        cls.carton_type = cls.env.ref(
            "hosny_purchase_packaging.packaging_type_carton"
        )
        cls.pallet_type = cls.env.ref(
            "hosny_purchase_packaging.packaging_type_pallet"
        )
        Packaging = cls.env["hosny.purchase.packaging"]
        cls.shrink = Packaging.create(
            {
                "packaging_type_id": cls.shrink_type.id,
                "product_id": cls.product.id,
                "company_id": cls.company.id,
                "content_type": "base_uom",
                "content_qty": 6,
            }
        )
        cls.carton = Packaging.create(
            {
                "packaging_type_id": cls.carton_type.id,
                "product_id": cls.product.id,
                "company_id": cls.company.id,
                "content_type": "packaging",
                "content_qty": 4,
                "inner_packaging_id": cls.shrink.id,
            }
        )
        cls.pallet = Packaging.create(
            {
                "packaging_type_id": cls.pallet_type.id,
                "product_id": cls.product.id,
                "company_id": cls.company.id,
                "content_type": "packaging",
                "content_qty": 50,
                "inner_packaging_id": cls.carton.id,
            }
        )

    def test_hierarchy_recalculation_and_guards(self):
        self.assertEqual(self.shrink.final_content_qty, 6)
        self.assertEqual(self.carton.final_content_qty, 24)
        self.assertEqual(self.pallet.final_content_qty, 1200)
        self.assertEqual(
            self.carton.uom_id._compute_quantity(1, self.unit, round=False), 24
        )
        self.assertEqual(
            self.pallet.uom_id._compute_quantity(1, self.unit, round=False), 1200
        )

        vendor = self.env["res.partner"].create(
            {"name": "Hierarchical Packaging Test Vendor", "supplier_rank": 1}
        )
        order = self.env["purchase.order"].create(
            {"partner_id": vendor.id, "company_id": self.company.id}
        )
        carton_line = self.env["purchase.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "hosny_purchase_packaging_id": self.carton.id,
                "product_qty": 3,
                "price_unit": 10,
            }
        )
        pallet_line = self.env["purchase.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "hosny_purchase_packaging_id": self.pallet.id,
                "product_qty": 2,
                "price_unit": 10,
            }
        )
        self.assertEqual(carton_line.product_uom_qty, 72)
        self.assertEqual(pallet_line.product_uom_qty, 2400)

        self.shrink.content_qty = 8
        self.assertEqual(self.shrink.final_content_qty, 8)
        self.assertEqual(self.carton.final_content_qty, 32)
        self.assertEqual(self.pallet.final_content_qty, 1600)
        self.assertEqual(carton_line.product_uom_qty, 96)
        self.assertEqual(pallet_line.product_uom_qty, 3200)

        with self.assertRaises(ValidationError):
            self.carton.write(
                {
                    "content_type": "packaging",
                    "inner_packaging_id": self.carton.id,
                }
            )
        with self.assertRaises(ValidationError):
            self.shrink.write(
                {
                    "content_type": "packaging",
                    "inner_packaging_id": self.carton.id,
                }
            )
        with self.assertRaises(ValidationError):
            self.shrink.unlink()

    def test_direct_packaging_compatibility(self):
        sack_type = self.env.ref("hosny_purchase_packaging.packaging_type_sack")
        direct = self.env["hosny.purchase.packaging"].create(
            {
                "packaging_type_id": sack_type.id,
                "product_id": self.product.id,
                "company_id": self.company.id,
                "content_type": "base_uom",
                "content_qty": 25,
            }
        )
        self.assertEqual(direct.final_content_qty, 25)
        self.assertEqual(
            direct.uom_id._compute_quantity(1, self.unit, round=False), 25
        )

    def test_delete_complete_hierarchy_in_one_save(self):
        with self.assertRaises(ValidationError):
            (self.shrink | self.carton).unlink()

        hierarchy = self.shrink | self.carton | self.pallet
        managed_uoms = hierarchy.uom_id
        hierarchy.unlink()
        self.assertFalse(hierarchy.exists())
        self.assertFalse(any(managed_uoms.with_context(active_test=False).mapped("active")))
        self.assertFalse(managed_uoms & self.product.product_tmpl_id.uom_ids)

    def test_product_is_detected_from_open_template(self):
        packaging_type = self.env.ref(
            "hosny_purchase_packaging.packaging_type_package"
        )
        Packaging = self.env["hosny.purchase.packaging"].with_context(
            default_product_id=False,
            default_product_tmpl_id=self.product.product_tmpl_id.id,
            default_company_id=self.company.id,
        )
        defaults = Packaging.default_get(["product_id", "company_id"])
        self.assertEqual(defaults["product_id"], self.product.id)

        packaging = Packaging.create(
            {
                "packaging_type_id": packaging_type.id,
                "company_id": self.company.id,
                "content_type": "base_uom",
                "content_qty": 5,
            }
        )
        self.assertEqual(packaging.product_id, self.product)
        self.assertEqual(packaging.final_content_qty, 5)
