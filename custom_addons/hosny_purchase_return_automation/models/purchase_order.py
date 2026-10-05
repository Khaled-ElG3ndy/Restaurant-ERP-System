from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools.float_utils import float_compare


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    hosny_vendor_bill_count = fields.Integer(
        string="Linked Vendor Bills",
        compute="_compute_hosny_purchase_links",
    )
    hosny_vendor_refund_count = fields.Integer(
        string="Linked Vendor Credit Notes",
        compute="_compute_hosny_purchase_links",
    )
    hosny_return_picking_count = fields.Integer(
        string="Linked Stock Returns",
        compute="_compute_hosny_purchase_links",
    )

    @api.depends("invoice_ids.move_type", "invoice_ids.state", "picking_ids.return_id", "picking_ids.state")
    def _compute_hosny_purchase_links(self):
        for order in self:
            bills = order.invoice_ids.filtered(lambda move: move.move_type == "in_invoice" and move.state != "cancel")
            refunds = order.invoice_ids.filtered(lambda move: move.move_type == "in_refund" and move.state != "cancel")
            returns = order.picking_ids.filtered(lambda picking: picking.return_id and picking.state != "cancel")
            order.hosny_vendor_bill_count = len(bills)
            order.hosny_vendor_refund_count = len(refunds)
            order.hosny_return_picking_count = len(returns)

    def _hosny_invoiceable_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda line: (
                not line.display_type
                and line.product_id
                and float_compare(
                    line.qty_to_invoice,
                    0.0,
                    precision_rounding=line.product_uom_id.rounding,
                )
                > 0
            )
        )

    def _hosny_check_account_invoice_group(self):
        if not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("You do not have the required accounting permission."))

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        if self.env.context.get("hosny_purchase_auto_bill") and not vals.get("invoice_date"):
            invoice_date = fields.Date.context_today(self)
            vals["invoice_date"] = invoice_date
            vals.setdefault("date", invoice_date)
            vals.setdefault("invoice_date_due", invoice_date)
        return vals

    def action_hosny_create_vendor_bill(self):
        self.ensure_one()
        self._hosny_check_account_invoice_group()
        if self.state != "purchase":
            raise UserError(_("Only confirmed purchase orders can create vendor bills."))

        existing_bills = self.invoice_ids.filtered(
            lambda move: move.move_type == "in_invoice" and move.state != "cancel"
        )
        if existing_bills and not self.env.context.get("hosny_allow_additional_vendor_bill"):
            return {
                "type": "ir.actions.act_window",
                "name": _("Confirm Additional Vendor Bill"),
                "res_model": "hosny.purchase.vendor.bill.confirm",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_purchase_id": self.id,
                    "default_existing_bill_ids": [(6, 0, existing_bills.ids)],
                },
            }
        if not self._hosny_invoiceable_lines():
            raise UserError(_("There are no remaining quantities to bill for this purchase order."))

        previous_invoices = self.invoice_ids
        action = self.with_context(hosny_purchase_auto_bill=True).action_create_invoice()
        self.invalidate_recordset(["invoice_ids", "invoice_count"])
        created_bills = (self.invoice_ids - previous_invoices).filtered(lambda move: move.move_type == "in_invoice")
        if not created_bills and action.get("res_id"):
            created_bills = self.env["account.move"].browse(action["res_id"]).filtered(lambda move: move.move_type == "in_invoice")
        for bill in created_bills:
            body = _(
                "Vendor bill %(bill)s was created from purchase order %(order)s.",
                bill=bill._get_html_link(),
                order=self._get_html_link(),
            )
            self.message_post(body=body)
            bill.message_post(body=_("Created automatically from purchase order %s.") % self._get_html_link())
        return action

    def action_hosny_open_purchase_return_wizard(self):
        self.ensure_one()
        if self.state != "purchase":
            raise UserError(_("Only confirmed purchase orders can be returned."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Create Vendor Return / Credit Note"),
            "res_model": "hosny.purchase.return.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_purchase_id": self.id,
                "active_id": self.id,
                "active_ids": self.ids,
                "active_model": "purchase.order",
            },
        }

    def _hosny_action_for_records(self, records, xmlid, name):
        self.ensure_one()
        if not records:
            return {"type": "ir.actions.act_window_close"}
        action = self.env["ir.actions.act_window"]._for_xml_id(xmlid)
        action["name"] = name
        if len(records) == 1:
            action.update({
                "views": [(False, "form")],
                "res_id": records.id,
                "domain": [],
            })
        else:
            action["domain"] = [("id", "in", records.ids)]
        return action

    def action_hosny_view_vendor_bills(self):
        self.ensure_one()
        bills = self.invoice_ids.filtered(lambda move: move.move_type == "in_invoice" and move.state != "cancel")
        return self._hosny_action_for_records(bills, "account.action_move_in_invoice_type", _("Linked Vendor Bills"))

    def action_hosny_view_vendor_refunds(self):
        self.ensure_one()
        refunds = self.invoice_ids.filtered(lambda move: move.move_type == "in_refund" and move.state != "cancel")
        return self._hosny_action_for_records(refunds, "account.action_move_in_refund_type", _("Linked Vendor Credit Notes"))

    def action_hosny_view_stock_returns(self):
        self.ensure_one()
        returns = self.picking_ids.filtered(lambda picking: picking.return_id and picking.state != "cancel")
        return self._hosny_action_for_records(returns, "stock.action_picking_tree_all", _("Linked Stock Returns"))

    def _hosny_post_return_messages(self, refund=False, return_picking=False, source_bill=False):
        self.ensure_one()
        parts = []
        if refund:
            parts.append(_("vendor credit note %(refund)s", refund=refund._get_html_link()))
        if return_picking:
            parts.append(_("stock return %(picking)s", picking=return_picking._get_html_link()))
        if not parts:
            return
        body = _(
            "Created %(documents)s from purchase order %(order)s.",
            documents=Markup(", ").join(parts),
            order=self._get_html_link(),
        )
        self.message_post(body=body)
        if refund:
            refund.message_post(body=_("Created from purchase order %s.") % self._get_html_link())
            if source_bill:
                refund.message_post(body=_("This credit note reverses vendor bill %s.") % source_bill._get_html_link())
        if return_picking:
            return_picking.message_post(body=_("Created from purchase order %s.") % self._get_html_link())
            if refund:
                return_picking.message_post(body=_("Linked to vendor credit note %s.") % refund._get_html_link())
