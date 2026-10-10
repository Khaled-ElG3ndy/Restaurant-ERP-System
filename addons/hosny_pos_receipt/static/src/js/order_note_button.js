/** @odoo-module **/

import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { formatCurrency } from "@web/core/currency";
import { nbsp } from "@web/core/utils/strings";
import { patch } from "@web/core/utils/patch";

/*
 * ملاحظات الفاتورة (عملاء الأجل وشركات التوصيل).
 *
 * تُحفظ في pos.order.hosny_invoice_note — لا في general_customer_note، فذاك
 * ملاحظة للمطبخ: أودو يعدّه تغييراً يُرسل للتحضير وتطبعه تذاكر المطبخ.
 * الحقل يُرسل للخادم مع الطلب تلقائياً، ويُطبع في صف «ملاحظة» بفاتورة العميل،
 * ويُنسخ إلى ملاحظات فاتورة المحاسبة.
 */
export const HOSNY_INVOICE_NOTE_HINTS = [
    "رقم طلب التطبيق: ",
    "اسم المستلم: ",
    "جوال المستلم: ",
    "العنوان: ",
    "المندوب: ",
];
const HOSNY_INVOICE_NOTE_MAX = 1000;

patch(PosOrder.prototype, {
    get hosnyInvoiceNote() {
        return (this.hosny_invoice_note || "").trim();
    },
    setHosnyInvoiceNote(note) {
        const clean = (note || "").trim().slice(0, HOSNY_INVOICE_NOTE_MAX);
        if (clean !== this.hosnyInvoiceNote) {
            this.hosny_invoice_note = clean;
        }
    },
    get hosnyIsPayLater() {
        return (this.payment_ids || []).some((p) => p.payment_method_id?.type === "pay_later");
    },
});

export class HosnyInvoiceNoteDialog extends Component {
    static template = "hosny_pos_receipt.InvoiceNoteDialog";
    static components = { Dialog };
    static props = {
        startingValue: { type: String, optional: true },
        customerName: { type: String, optional: true },
        atValidation: { type: Boolean, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = { startingValue: "", customerName: "", atValidation: false };

    setup() {
        this.hints = HOSNY_INVOICE_NOTE_HINTS;
        this.maxLength = HOSNY_INVOICE_NOTE_MAX;
        this.state = useState({ note: this.props.startingValue || "" });
        this.input = useRef("noteInput");
        onMounted(() => this.focusEnd());
    }

    focusEnd() {
        const el = this.input.el;
        if (el) {
            el.focus();
            el.setSelectionRange(el.value.length, el.value.length);
        }
    }

    addHint(hint) {
        const current = this.state.note.replace(/\s+$/, "");
        const note = (current ? current + "\n" : "") + hint;
        // Written to the textarea now, not at the next render: a cashier who
        // types right after the tap would otherwise overwrite the chip's text
        // (t-model reads the stale DOM value on the first keystroke).
        if (this.input.el) {
            this.input.el.value = note;
        }
        this.state.note = note;
        this.focusEnd();
    }

    clear() {
        this.state.note = "";
        this.focusEnd();
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.confirm();
        }
    }

    confirm() {
        this.props.getPayload({ note: this.state.note.trim() });
        this.props.close();
    }

    skip() {
        this.props.getPayload({ skip: true });
        this.props.close();
    }
}

/**
 * يفتح نافذة الملاحظات للطلب ويحفظها عليه.
 * يرجع undefined إن أُغلقت النافذة، وإلا { note } أو { skip: true }.
 */
export async function editHosnyInvoiceNote(dialog, order, { atValidation = false } = {}) {
    if (!order) {
        return undefined;
    }
    const result = await makeAwaitable(dialog, HosnyInvoiceNoteDialog, {
        startingValue: order.hosny_invoice_note || "",
        customerName: order.partner_id?.name || "",
        atValidation,
    });
    if (result && !result.skip) {
        order.setHosnyInvoiceNote(result.note);
    }
    return result;
}

patch(PaymentScreen.prototype, {
    async openHosnyInvoiceNote() {
        await editHosnyInvoiceNote(this.dialog, this.currentOrder);
    },

    /* فاتورة أجل (عميل أجل أو شركة توصيل) بلا ملاحظة: نسأل مرة واحدة قبل
     * الإغلاق. بلا عميل لا نسأل — أودو نفسه سيطلب اختيار العميل أولاً. */
    async validateOrder(isForceValidate) {
        const order = this.currentOrder;
        if (
            order &&
            !order.hosnyInvoiceNote &&
            !order.uiState?.hosnyInvoiceNoteAsked &&
            order.partner_id &&
            order.hosnyIsPayLater &&
            !order.isRefund
        ) {
            const result = await editHosnyInvoiceNote(this.dialog, order, { atValidation: true });
            if (result === undefined) {
                return;
            }
            if (order.uiState) {
                order.uiState.hosnyInvoiceNoteAsked = true;
            }
        }
        return super.validateOrder(...arguments);
    },
});

/*
 * آخر ملاحظة طُبعت مع الفاتورة. فاتورة السفري صارت تُطبع بعد الدفع فقط
 * (takeaway_checkout)، فتخرج بالملاحظة النهائية ولا حاجة لإعادة طباعتها.
 */
patch(PosStore.prototype, {
    async printReceipt(options = {}) {
        const order = options.order || this.getOrder();
        const result = await super.printReceipt(...arguments);
        if (result && order?.uiState && !options.basic) {
            order.uiState.hosnyNotePrinted = order.hosnyInvoiceNote;
        }
        return result;
    },
});

const originalLineScreenValuesGetter = Object.getOwnPropertyDescriptor(Orderline.prototype, "lineScreenValues")?.get;

patch(Orderline.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
    },

    get lineScreenValues() {
        const vals = originalLineScreenValuesGetter ? originalLineScreenValuesGetter.call(this) : {};
        if (this.props.mode !== "receipt" || !this.line?.currency) {
            return vals;
        }

        const format = (amount) =>
            `${formatCurrency(amount, this.line.currency.id, { noSymbol: true })}${nbsp}${this.line.currency.symbol}`;

        if (vals.price) {
            vals.price = format(this.line.displayPrice);
        }
        if (vals.displayPriceUnit) {
            vals.displayPriceUnit = `${format(this.line.displayPriceUnit)} / ${this.line.product_id?.uom_id?.name || ""}`;
        }
        if (vals.noDiscountPrice) {
            vals.noDiscountPrice = format(this.line.displayPriceNoDiscount);
        }
        return vals;
    },

    async openHosnyLineNote(ev) {
        ev.stopPropagation();
        ev.preventDefault();

        const currentNote =
            this.line.getCustomerNote?.() ||
            this.line.get_customer_note?.() ||
            this.line.customer_note ||
            "";
        const note = await makeAwaitable(this.dialog, TextInputPopup, {
            title: _t("ملاحظات الصنف"),
            placeholder: _t("اكتب ملاحظات هذا الصنف..."),
            rows: 4,
            startingValue: currentNote,
        });
        if (note === undefined) {
            return;
        }

        if (typeof this.line.setCustomerNote === "function") {
            this.line.setCustomerNote(note);
        } else if (typeof this.line.set_customer_note === "function") {
            this.line.set_customer_note(note);
        } else {
            this.line.customer_note = note || "";
        }
    },
});

patch(OrderReceipt.prototype, {
    formatCurrency(amount) {
        const order = this.order;
        if (!order) {
            return formatCurrency(amount, this.pos.currency?.id);
        }
        return `${formatCurrency(amount, order.currency.id, { noSymbol: true })}${nbsp}${order.currency.symbol}`;
    },
});

patch(ReceiptScreen.prototype, {
    /* بعد الدفع الطلب مُرسل للخادم، فالتعديل يُكتب هناك مباشرة (والفاتورة
     * المحاسبية إن وُجدت)، ثم يُعاد طبع الإيصال بالملاحظة الجديدة. */
    async openReceiptNotePopup() {
        const order = this.currentOrder;
        if (!order) {
            return;
        }
        const before = order.hosny_invoice_note || "";
        const result = await editHosnyInvoiceNote(this.dialog, order);
        if (!result || result.skip || (order.hosny_invoice_note || "") === before) {
            return;
        }
        if (typeof order.id === "number") {
            try {
                await this.pos.data.call("pos.order", "hosny_set_invoice_note", [
                    [order.id],
                    order.hosny_invoice_note || "",
                ]);
            } catch (error) {
                order.hosny_invoice_note = before;
                this.notification.add(_t("تعذّر حفظ ملاحظات الفاتورة — تحقق من الاتصال وحاول مرة أخرى."), {
                    type: "danger",
                });
                return;
            }
        }
        this.notification.add(_t("تم حفظ ملاحظات الفاتورة. اطبع الإيصال مرة أخرى لتظهر عليه."), {
            type: "success",
        });
    },
});
