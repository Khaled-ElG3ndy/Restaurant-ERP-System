/**
 * عدد نسخ فاتورة العميل في طلب واحد للطابعة (2026-10-09): فاتورة السفري تخرج
 * نسختين ورا بعض. الفاتورة تُرسم مرة واحدة (الرسم هو الجزء البطيء) وتُرسل
 * نفس الصورة للطابعة بعدد النسخ، فلا يزيد زمن النسخة الثانية إلا زمن الورق.
 *
 *   pos.printReceipt({ order, copies: 2 })
 *     → PosPrinterService.print يعرف النسخ من الطلب نفسه
 *     → printHtml يربطها بعنصر الفاتورة المرسوم
 *     → BasePrinter.printReceipt (render_lock.js) يرسل الصورة مرتين
 *
 * لو فشلت نسخة يبقى على العنصر عدد ما لم يُطبع، فـ«إعادة المحاولة» (تستدعي
 * printHtml بنفس العنصر) تطبع الناقص فقط ولا تكرر ما خرج.
 *
 * وما إن تخرج نسخة واحدة على الأقل — من أول مرة أو من «إعادة المحاولة» —
 * يُعلَّم الطلب hosnyReceiptPrinted (طُبعت فاتورته).
 */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosPrinterService } from "@point_of_sale/app/services/pos_printer_service";
import { patch } from "@web/core/utils/patch";

/** نسخ فاتورة العميل التي تخرج تلقائياً للسفري بعد الدفع. */
export const TAKEAWAY_RECEIPT_COPIES = 2;

const copiesByOrder = new WeakMap();
const copiesByReceipt = new WeakMap();
const printedByReceipt = new WeakMap();

const toCopies = (value) => Math.max(1, Math.floor(Number(value) || 1));

/** النسخ الباقية لعنصر فاتورة مرسوم (1 لو لم يُطلب غير ذلك). */
export function remainingCopies(receipt) {
    return (receipt && copiesByReceipt.get(receipt)) || 1;
}

/** ما بقي بعد فشل نسخة، أو 0 حين خرجت كلها. */
export function setRemainingCopies(receipt, count) {
    if (!receipt || typeof receipt !== "object") {
        return;
    }
    if (count > 0) {
        copiesByReceipt.set(receipt, count);
    } else {
        copiesByReceipt.delete(receipt);
    }
}

/** نسخة خرجت فعلاً من الطابعة. */
export function notePrintedCopy(receipt) {
    if (receipt && typeof receipt === "object") {
        printedByReceipt.set(receipt, (printedByReceipt.get(receipt) || 0) + 1);
    }
}

patch(PosStore.prototype, {
    get hosnyTakeawayReceiptCopies() {
        return TAKEAWAY_RECEIPT_COPIES;
    },

    /** copies اختياري؛ بدونه (أو 1) المسار كما هو حرفياً. */
    async printReceipt(options = {}) {
        const copies = toCopies(options?.copies);
        const order = options?.order || this.getOrder();
        if (copies <= 1 || !order) {
            return await super.printReceipt(...arguments);
        }
        copiesByOrder.set(order, copies);
        try {
            return await super.printReceipt(...arguments);
        } finally {
            copiesByOrder.delete(order);
        }
    },
});

patch(PosPrinterService.prototype, {
    async print(component, props, options = {}) {
        const copies = props?.order && !props.basic_receipt ? copiesByOrder.get(props.order) : 0;
        if (copies > 1) {
            options = { ...options, copies, hosnyOrder: props.order };
        }
        return await super.print(component, props, options);
    },

    async printHtml(el, options = {}) {
        // «إعادة المحاولة» تمر من هنا بنفس العنصر: نُبقي الباقي ولا نعيد العدد كاملاً.
        if (options?.copies > 1 && el && !copiesByReceipt.has(el)) {
            copiesByReceipt.set(el, options.copies);
        }
        try {
            return await super.printHtml(...arguments);
        } finally {
            const order = options?.hosnyOrder;
            if (order?.uiState && printedByReceipt.get(el) > 0) {
                order.uiState.hosnyReceiptPrinted = true;
            }
        }
    },
});
