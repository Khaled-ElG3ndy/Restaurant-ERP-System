from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class HosnyPurchaseReturnWizard(models.TransientModel):
    _name = "hosny.purchase.return.wizard"
    _description = "Purchase Vendor Return / Credit Note Wizard"

    purchase_id = fields.Many2one("purchase.order", required=True, readonly=True)
    company_id = fields.Many2one(related="purchase_id.company_id", readonly=True)
    available_bill_ids = fields.Many2many("account.move", compute="_compute_available_documents")
    available_picking_ids = fields.Many2many("stock.picking", compute="_compute_available_documents")
    original_bill_id = fields.Many2one(
        "account.move",
        string="Original Vendor Bill",
        domain="[('id', 'in', available_bill_ids)]",
    )
    return_picking_id = fields.Many2one(
        "stock.picking",
        string="Receipt to Return",
        domain="[('id', 'in', available_picking_ids)]",
    )
    line_ids = fields.One2many(
        "hosny.purchase.return.wizard.line",
        "wizard_id",
        string="Products",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        purchase = self.env["purchase.order"].browse(
            res.get("purchase_id") or self.env.context.get("active_id")
        ).exists()
        if purchase:
            res["purchase_id"] = purchase.id
            bills = purchase.invoice_ids.filtered(lambda move: move.move_type == "in_invoice" and move.state == "posted")
            if bills:
                res["original_bill_id"] = bills.sorted(lambda move: (move.invoice_date or move.date, move.id), reverse=True)[:1].id
            pickings = purchase.picking_ids.filtered(
                lambda picking: picking.state == "done" and not picking.return_id and picking.location_dest_id.usage != "supplier"
            )
            if pickings:
                res["return_picking_id"] = pickings.sorted(lambda picking: (picking.date_done or picking.date, picking.id), reverse=True)[:1].id
            res["line_ids"] = [
                Command.create({"purchase_line_id": line.id})
                for line in purchase.order_line.filtered(lambda line: not line.display_type and line.product_id)
            ]
        return res

    @api.depends("purchase_id")
    def _compute_available_documents(self):
        for wizard in self:
            wizard.available_bill_ids = wizard.purchase_id.invoice_ids.filtered(
                lambda move: move.move_type == "in_invoice" and move.state == "posted"
            )
            wizard.available_picking_ids = wizard.purchase_id.picking_ids.filtered(
                lambda picking: picking.state == "done" and not picking.return_id and picking.location_dest_id.usage != "supplier"
            )

    @api.onchange("purchase_id")
    def _onchange_purchase_id(self):
        for wizard in self:
            wizard.line_ids = [Command.clear()] + [
                Command.create({"purchase_line_id": line.id})
                for line in wizard.purchase_id.order_line.filtered(lambda line: not line.display_type and line.product_id)
            ]

    def _check_permissions(self, needs_refund, needs_stock_return):
        if needs_refund and not self.env.user.has_group("account.group_account_invoice"):
            raise AccessError(_("You do not have the required accounting permission."))
        if needs_stock_return and not self.env.user.has_group("stock.group_stock_user"):
            raise AccessError(_("You do not have the required inventory permission."))

    @api.model
    def _returnable_move_quantity(self, move):
        quantity = move.quantity
        for returned_move in move.returned_move_ids.filtered(lambda item: item.state != "cancel"):
            quantity -= returned_move.product_uom._compute_quantity(
                returned_move.quantity,
                move.product_uom,
                round=False,
            )
        return max(move.product_uom.round(quantity), 0.0)

    def _validate_quantities(self):
        self.ensure_one()
        refund_lines = self.line_ids.filtered(lambda line: not float_is_zero(line.refund_quantity, precision_rounding=line.product_uom_id.rounding))
        return_lines = self.line_ids.filtered(lambda line: not float_is_zero(line.return_quantity, precision_rounding=line.product_uom_id.rounding))
        if not refund_lines and not return_lines:
            raise UserError(_("Please enter at least one refund or return quantity."))
        if refund_lines:
            if not self.original_bill_id:
                raise UserError(_("Please select the original posted vendor bill for the credit note."))
            if self.original_bill_id.state != "posted":
                raise UserError(_("The original vendor bill must be posted before creating a credit note."))
        if return_lines and not self.return_picking_id:
            raise UserError(_("Please select the received picking to return stock."))

        for line in self.line_ids:
            precision = line.product_uom_id.rounding
            if float_compare(line.refund_quantity, 0.0, precision_rounding=precision) < 0:
                raise ValidationError(_("Refund quantity cannot be negative for %s.") % line.product_id.display_name)
            if float_compare(line.return_quantity, 0.0, precision_rounding=precision) < 0:
                raise ValidationError(_("Return quantity cannot be negative for %s.") % line.product_id.display_name)
            if float_compare(line.refund_quantity, line.available_refund_quantity, precision_rounding=precision) > 0:
                raise ValidationError(_("You cannot refund more than the invoiced quantity for %s.") % line.product_id.display_name)
            if float_compare(line.return_quantity, line.available_return_quantity, precision_rounding=precision) > 0:
                raise ValidationError(_("You cannot return more than the received quantity for %s.") % line.product_id.display_name)
        return refund_lines, return_lines

    def action_create_return_documents(self):
        self.ensure_one()
        refund_lines, return_lines = self._validate_quantities()
        self._check_permissions(bool(refund_lines), bool(return_lines))

        refund = self.env["account.move"]
        return_picking = self.env["stock.picking"]
        if return_lines:
            return_picking = self._create_stock_return(return_lines)
        if refund_lines:
            refund = self._create_vendor_refund(refund_lines)
        if refund and return_picking:
            return_picking.write({"hosny_vendor_refund_id": refund.id})

        self.purchase_id._hosny_post_return_messages(
            refund=refund,
            return_picking=return_picking,
            source_bill=self.original_bill_id,
        )

        if refund:
            return {
                "type": "ir.actions.act_window",
                "name": _("Vendor Credit Note"),
                "res_model": "account.move",
                "res_id": refund.id,
                "view_mode": "form",
                "context": {"default_move_type": "in_refund"},
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("Stock Return"),
            "res_model": "stock.picking",
            "res_id": return_picking.id,
            "view_mode": "form",
        }

    def _create_vendor_refund(self, refund_lines):
        self.ensure_one()
        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move",
            active_ids=self.original_bill_id.ids,
        ).create({
            "move_ids": [Command.set(self.original_bill_id.ids)],
            "company_id": self.original_bill_id.company_id.id,
            "journal_id": self.original_bill_id.journal_id.id,
            "reason": _("Purchase return for %s") % self.purchase_id.name,
            "date": fields.Date.context_today(self),
        })
        reversal.refund_moves()
        refund = reversal.new_move_ids.ensure_one()

        quantity_by_purchase_line = {
            line.purchase_line_id.id: line.refund_quantity
            for line in refund_lines
        }
        refund.invoice_line_ids.filtered(lambda line: line.display_type in ("line_section", "line_subsection", "line_note")).unlink()
        for move_line in refund.invoice_line_ids.filtered(lambda line: line.display_type == "product"):
            purchase_line = move_line.purchase_line_id
            quantity = quantity_by_purchase_line.pop(purchase_line.id, 0.0)
            if float_is_zero(quantity, precision_rounding=purchase_line.product_uom_id.rounding):
                move_line.unlink()
                continue
            move_line.quantity = purchase_line.product_uom_id._compute_quantity(
                quantity,
                move_line.product_uom_id,
                round=False,
            )
        if quantity_by_purchase_line:
            raise UserError(_("Some selected products were not found on the original vendor bill."))

        values = {"invoice_origin": self.purchase_id.name}
        if "analytic_account_id" in refund._fields and self.purchase_id.analytic_account_id:
            values["analytic_account_id"] = self.purchase_id.analytic_account_id.id
        refund.write(values)
        return refund

    def _create_stock_return(self, return_lines):
        self.ensure_one()
        return_wizard = self.env["stock.return.picking"].with_context(
            active_model="stock.picking",
            active_id=self.return_picking_id.id,
            active_ids=self.return_picking_id.ids,
        ).create({})

        quantity_by_purchase_line = {
            line.purchase_line_id.id: line.return_quantity
            for line in return_lines
        }
        for return_move in return_wizard.product_return_moves:
            purchase_line = return_move.move_id.purchase_line_id
            remaining_qty = quantity_by_purchase_line.get(purchase_line.id, 0.0)
            if not purchase_line or float_is_zero(remaining_qty, precision_rounding=purchase_line.product_uom_id.rounding):
                return_move.quantity = 0.0
                continue
            move_available_qty = return_move.move_id.product_uom._compute_quantity(
                self._returnable_move_quantity(return_move.move_id),
                purchase_line.product_uom_id,
                round=False,
            )
            qty_for_move = min(remaining_qty, move_available_qty)
            return_move.quantity = purchase_line.product_uom_id._compute_quantity(
                qty_for_move,
                return_move.uom_id,
                round=False,
            )
            quantity_by_purchase_line[purchase_line.id] = remaining_qty - qty_for_move

        leftover = [
            qty
            for line_id, qty in quantity_by_purchase_line.items()
            if not float_is_zero(qty, precision_rounding=self.env["purchase.order.line"].browse(line_id).product_uom_id.rounding)
        ]
        if leftover:
            raise UserError(_("The selected receipt does not have enough returnable quantity."))

        action = return_wizard.action_create_returns()
        return self.env["stock.picking"].browse(action["res_id"]).exists()


class HosnyPurchaseReturnWizardLine(models.TransientModel):
    _name = "hosny.purchase.return.wizard.line"
    _description = "Purchase Vendor Return / Credit Note Wizard Line"

    wizard_id = fields.Many2one("hosny.purchase.return.wizard", required=True, ondelete="cascade")
    purchase_line_id = fields.Many2one("purchase.order.line", required=True, readonly=True)
    product_id = fields.Many2one(related="purchase_line_id.product_id", readonly=True)
    product_uom_id = fields.Many2one(related="purchase_line_id.product_uom_id", readonly=True)
    ordered_quantity = fields.Float(related="purchase_line_id.product_qty", readonly=True)
    available_refund_quantity = fields.Float(
        string="Available to Refund",
        compute="_compute_available_quantities",
        digits="Product Unit",
    )
    available_return_quantity = fields.Float(
        string="Available to Return",
        compute="_compute_available_quantities",
        digits="Product Unit",
    )
    refund_quantity = fields.Float(string="Refund Quantity", digits="Product Unit")
    return_quantity = fields.Float(string="Stock Return Quantity", digits="Product Unit")

    @api.depends(
        "purchase_line_id",
        "wizard_id.original_bill_id",
        "wizard_id.return_picking_id",
        "purchase_line_id.qty_invoiced",
        "purchase_line_id.move_ids.quantity",
        "purchase_line_id.move_ids.returned_move_ids.quantity",
    )
    def _compute_available_quantities(self):
        for line in self:
            line.available_refund_quantity = line._get_available_refund_quantity()
            line.available_return_quantity = line._get_available_return_quantity()

    def _get_available_refund_quantity(self):
        self.ensure_one()
        purchase_line = self.purchase_line_id
        bill = self.wizard_id.original_bill_id
        if not purchase_line:
            return 0.0
        if not bill:
            return max(purchase_line.qty_invoiced, 0.0)

        bill_qty = sum(
            invoice_line.product_uom_id._compute_quantity(
                invoice_line.quantity,
                purchase_line.product_uom_id,
                round=False,
            )
            for invoice_line in bill.invoice_line_ids.filtered(
                lambda item: item.purchase_line_id == purchase_line and item.display_type == "product"
            )
        )
        refunded_qty = sum(
            refund_line.product_uom_id._compute_quantity(
                refund_line.quantity,
                purchase_line.product_uom_id,
                round=False,
            )
            for refund_line in bill.reversal_move_ids.filtered(lambda move: move.state != "cancel" and move.move_type == "in_refund").invoice_line_ids.filtered(
                lambda item: item.purchase_line_id == purchase_line and item.display_type == "product"
            )
        )
        return max(purchase_line.product_uom_id.round(bill_qty - refunded_qty), 0.0)

    def _get_available_return_quantity(self):
        self.ensure_one()
        purchase_line = self.purchase_line_id
        picking = self.wizard_id.return_picking_id
        if not purchase_line or not picking:
            return 0.0
        quantity = 0.0
        for move in picking.move_ids.filtered(lambda item: item.purchase_line_id == purchase_line and item.state != "cancel"):
            quantity += move.product_uom._compute_quantity(
                self.wizard_id._returnable_move_quantity(move),
                purchase_line.product_uom_id,
                round=False,
            )
        return max(purchase_line.product_uom_id.round(quantity), 0.0)
