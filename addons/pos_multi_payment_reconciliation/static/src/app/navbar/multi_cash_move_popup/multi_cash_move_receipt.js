/** @odoo-module */

import { Component } from "@odoo/owl";
import { ReceiptHeader } from "@point_of_sale/app/screens/receipt_screen/receipt/receipt_header/receipt_header";

export class MultiCashMoveReceipt extends Component {
    static template = "pos_multi_payment_reconciliation.MultiCashMoveReceipt";
    static components = { ReceiptHeader };
    static props = {
        headerData: Object,
        date: String,
        lines: Array,
    };
}
