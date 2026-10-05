/** @odoo-module **/

/**
 * شاشة الدفع بتقسيمة FERP. القالب كله جديد ويُركَّب على الفئة نفسها
 * (PaymentScreen.template)، فيبقى منطق أودو — إضافة أسطر الدفع، مخزن الأرقام،
 * التصديق — وكل ما رقّعته الموديولات الأخرى على الفئة كما هو؛ وما كانت تضيفه
 * إلى القالب القديم (ملاحظات الفاتورة، الكوبون) يُستدعى هنا إن وُجد.
 */
import { Component } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";

const pad = (n) => String(n).padStart(2, "0");

/** «عرض الفاتورة»: الإيصال كما سيُطبع، قبل الدفع. */
export class HosnyReceiptPreview extends Component {
    static template = "hosny_pos_payment.ReceiptPreview";
    static components = { Dialog, OrderReceipt };
    static props = { order: Object, close: Function };
}

/** فئات النقد: تضع المبلغ الذي سلّمه العميل في سطر الدفع المحدد. */
const NOTES = [5, 10, 20, 50, 100, 200, 500];

patch(PaymentScreen, {
    template: "hosny_pos_payment.PaymentScreen",
});

patch(PaymentScreen.prototype, {
    /** 81.50 SR — الرمز بعد الرقم، معزول LTR داخل الشاشة العربية. */
    hpMoney(amount) {
        const symbol = this.pos.currency?.symbol ?? "";
        const number = this.env.utils.formatCurrency(amount || 0, false);
        return symbol ? `⁦${number} ${symbol}⁩` : number;
    },

    // ── ملخص الفاتورة ───────────────────────────────────────────────────
    get hpSummary() {
        const order = this.currentOrder;
        return {
            base: order.priceExcl,
            tax: order.amountTaxes,
            discount: order.getTotalDiscount?.() || 0,
            tip: order.getTip?.() || 0,
            total: order.totalDue,
        };
    },
    get hpInvoiceNumber() {
        const order = this.currentOrder;
        return String(order.hosny_session_number || order.tracking_number || order.getName?.() || "");
    },
    get hpDate() {
        const raw = this.currentOrder.date_order;
        const dt = raw ? (typeof raw === "string" ? deserializeDateTime(raw) : raw) : null;
        const d = dt?.isValid ? new Date(dt.toMillis()) : new Date();
        const h = d.getHours();
        return `${pad(d.getDate())}-${pad(d.getMonth() + 1)}-${d.getFullYear()}  ${h % 12 || 12}:${pad(d.getMinutes())} ${h < 12 ? "ص" : "م"}`;
    },
    get hpCashier() {
        return this.currentOrder.getCashierName?.() || this.pos.cashier?.name || "";
    },
    get hpPlace() {
        const order = this.currentOrder;
        if (order.table_id) {
            return `طاولة ${order.table_id.table_number}`;
        }
        return order.preset_id?.name || "";
    },
    get hpHasNotes() {
        return typeof this.openHosnyInvoiceNote === "function";
    },
    hpPreview() {
        this.dialog.add(HosnyReceiptPreview, { order: this.currentOrder });
    },
    /** «طباعة» قبل الدفع = الفاتورة المبدئية، بعدد النسخ إن كان متاحاً. */
    async hpPrint() {
        const order = this.currentOrder;
        if (!order.lines.length) {
            return;
        }
        this.pos.addPendingOrder?.([order.id]);
        await this.pos.syncAllOrders?.();
        if (this.pos.askReceiptCopies && this.pos.printReceiptCopies) {
            const copies = await this.pos.askReceiptCopies();
            if (copies) {
                await this.pos.printReceiptCopies({ copies, printBillActionTriggered: true });
            }
            return;
        }
        await this.pos.printReceipt({ printBillActionTriggered: true });
    },

    // ── الدفع ───────────────────────────────────────────────────────────
    get hpPaid() {
        return this.paymentLines
            .filter((line) => !line.is_change)
            .reduce((sum, line) => sum + line.getAmount(), 0);
    },
    get hpRemaining() {
        return Math.max(0, this.currentOrder.remainingDue);
    },
    get hpChange() {
        return Math.max(0, this.currentOrder.change);
    },
    get hpMethods() {
        const minimal = this.pos.cashier?._role === "minimal";
        return this.payment_methods_from_config.filter(
            (method) => !(minimal && method.type === "pay_later")
        );
    },
    hpMethodIcon(method) {
        return method.type === "cash"
            ? "fa-money"
            : method.type === "pay_later"
              ? "fa-clock-o"
              : "fa-credit-card";
    },
    hpIsActiveMethod(method) {
        return this.selectedPaymentLine?.payment_method_id?.id === method.id;
    },
    get hpLines() {
        return this.paymentLines.filter((line) => !line.is_change);
    },
    get hpCanValidate() {
        const order = this.currentOrder;
        return order.canBeValidated() && !order.isRefundInProcess();
    },
    get hpHideValidate() {
        return this.pos.config.set_tip_after_payment && !this.currentOrder.isPaid();
    },

    // ── الإجراءات والأرقام ──────────────────────────────────────────────
    get hpNotes() {
        return NOTES;
    },
    get hpShowTip() {
        return Boolean(this.pos.config.iface_tipproduct && this.pos.config.tip_product_id);
    },
    get hpShowPromo() {
        return typeof this.openPromoCode === "function";
    },
    get hpCanSplit() {
        const qty = this.currentOrder.lines
            .filter((line) => line.isGlobalDiscountApplicable?.() ?? true)
            .reduce((sum, line) => sum + line.qty, 0);
        return Boolean(this.pos.config.module_pos_restaurant) && qty >= 2;
    },
    hpSplit() {
        this.pos.navigate("SplitBillScreen", { orderUuid: this.currentOrder.uuid });
    },
    get hpDecimalPoint() {
        return this.env.services.localization?.decimalPoint || ".";
    },
    hpKey(key) {
        this.numberBuffer.sendKey(key);
    },
    /** سطر دفع محدد للأزرار التي تكتب مبلغاً؛ بلا سطر يُضاف النقدي (أو أول وسيلة). */
    async hpEnsureLine() {
        if (this.selectedPaymentLine) {
            return true;
        }
        const method =
            this.hpMethods.find((m) => m.type === "cash") || this.hpMethods[0];
        return method ? await this.addNewPaymentLine(method) : false;
    },
    async hpTender(value) {
        if (!(await this.hpEnsureLine())) {
            return;
        }
        this.numberBuffer.set(String(value));
        this.updateSelectedPaymentline(value);
    },
    /** المبلغ المتبقي كاملاً في السطر المحدد. */
    async hpExact() {
        if (!(await this.hpEnsureLine())) {
            return;
        }
        const line = this.selectedPaymentLine;
        const value = this.pos.currency.round(line.getAmount() + this.currentOrder.remainingDue);
        this.numberBuffer.set(String(value));
        this.updateSelectedPaymentline(value);
    },
});
