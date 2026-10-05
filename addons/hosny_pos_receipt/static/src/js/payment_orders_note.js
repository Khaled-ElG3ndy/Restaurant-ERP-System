/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { HosnyPaymentOrdersScreen } from "@hosny_pos_controls/js/payment_orders_screen";

/* «تسديد الفواتير»: ملاحظات الفاتورة تظهر على بطاقة الطلب ويُبحث بها
 * (رقم طلب التطبيق، اسم المستلم…). */
patch(HosnyPaymentOrdersScreen.prototype, {
    buildLiveOrderEntry(order) {
        const entry = super.buildLiveOrderEntry(...arguments);
        return entry && this.hosnyWithInvoiceNote(entry, order.hosny_invoice_note);
    },
    buildStoredOrderEntry(json) {
        const entry = super.buildStoredOrderEntry(...arguments);
        return entry && this.hosnyWithInvoiceNote(entry, json.hosny_invoice_note);
    },
    hosnyWithInvoiceNote(entry, note) {
        const invoiceNote = (note || "").trim();
        if (invoiceNote) {
            entry.invoiceNote = invoiceNote;
            entry.searchableText = `${entry.searchableText || ""} ${invoiceNote.toLowerCase()}`;
        }
        return entry;
    },
});
