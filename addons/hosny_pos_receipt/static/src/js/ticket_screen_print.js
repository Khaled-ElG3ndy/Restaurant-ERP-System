/** @odoo-module **/

/**
 * «الطلبات والفواتير» (TicketScreen), 2026-10-09: طباعة بدل الحذف.
 *
 * زر سلة المهملات في كل صف أُزيل؛ مكانه زر طباعة لفاتورة الطلب — مفتوحاً
 * كان (فاتورة العميل قبل الدفع) أو مدفوعاً (الإيصال). وزر «طباعة» كبير بجانب
 * «تحميل الطلب» للطلب المختار. الطباعة تمر من pos.printReceipt نفسه، فتخرج
 * بقالب FERP ورقم الوردية كبقية الطباعات (ferp_receipt.js).
 */
import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.hosnyPrinting = null;
    },

    async hosnyPrintOrder(order) {
        if (!order || !order.lines?.length || this.state.hosnyPrinting) {
            return;
        }
        this.state.hosnyPrinting = order.uuid;
        try {
            await this.pos.printReceipt({ order });
        } catch (error) {
            console.warn("[Hosny] ticket screen print failed", error);
            this.pos.notification.add("تعذّرت الطباعة — تأكد من الطابعة وحاول مرة أخرى.", { type: "danger" });
        } finally {
            this.state.hosnyPrinting = null;
        }
    },
});
