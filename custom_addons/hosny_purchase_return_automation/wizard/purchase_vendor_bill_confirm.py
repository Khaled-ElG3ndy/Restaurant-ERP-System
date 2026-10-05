from odoo import fields, models


class HosnyPurchaseVendorBillConfirm(models.TransientModel):
    _name = "hosny.purchase.vendor.bill.confirm"
    _description = "Confirm Additional Vendor Bill"

    purchase_id = fields.Many2one("purchase.order", required=True, readonly=True)
    existing_bill_ids = fields.Many2many("account.move", readonly=True)

    def action_confirm_create_bill(self):
        self.ensure_one()
        return self.purchase_id.with_context(hosny_allow_additional_vendor_bill=True).action_hosny_create_vendor_bill()
