/** @odoo-module **/
/**
 * عدد نسخ الفاتورة يُختار عند كل طباعة (طلب 2026-09-28): «فاتورة» في شاشة
 * الأصناف و«طباعة الإيصال» بعد الدفع يفتحان خانة لعدد النسخ — أي عدد، وليس
 * إعداداً ثابتاً للفرع — وزر «طباعة». الفاتورة تُطبع على طابعة الكاشير كما
 * كانت، نسخة بعد نسخة، وتتوقف عند أول فشل مع ذكر ما خرج منها.
 */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { ReceiptScreen } from "@point_of_sale/app/screens/receipt_screen/receipt_screen";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { BACKSPACE, EMPTY, ZERO, getButtons } from "@point_of_sale/app/components/numpad/numpad";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { useTrackedAsync } from "@point_of_sale/app/hooks/hooks";
import { patch } from "@web/core/utils/patch";

// أكثر من هذا يطلب تأكيداً فقط (لا حدّ أعلى): رقم زائد بالخطأ، 22 بدل 2،
// يُفرغ رول الورق ويشغل الطابعة دقائق.
const CONFIRM_COPIES_ABOVE = 20;

const toCopies = (buffer) => (/^\d+$/.test(String(buffer)) ? parseInt(buffer, 10) : 0);

export function copiesLabel(count) {
    if (count === 1) {
        return "نسخة واحدة";
    }
    if (count === 2) {
        return "نسختان";
    }
    if (count >= 3 && count <= 10) {
        return `${count} نسخ`;
    }
    return `${count} نسخة`;
}

patch(PosStore.prototype, {
    /** عدد النسخ الذي كتبه الكاشير، أو 0 لو ألغى. */
    async askReceiptCopies() {
        const value = await makeAwaitable(this.dialog, NumberPopup, {
            title: "عدد نسخ الفاتورة",
            startingValue: "1",
            buttons: getButtons([{ ...EMPTY, disabled: true }, ZERO, BACKSPACE]),
            isValid: (buffer) => toCopies(buffer) >= 1,
            feedback: (buffer) => (toCopies(buffer) >= 1 ? copiesLabel(toCopies(buffer)) : ""),
            confirmButtonLabel: "طباعة",
        });
        const copies = toCopies(value);
        if (copies > CONFIRM_COPIES_ABOVE) {
            const confirmed = await ask(this.dialog, {
                title: "تأكيد عدد النسخ",
                body: `ستُطبع ${copiesLabel(copies)} من الفاتورة. هل الرقم صحيح؟`,
                confirmLabel: "طباعة",
                cancelLabel: "رجوع",
            });
            if (!confirmed) {
                return 0;
            }
        }
        return copies;
    },

    /**
     * نسخة واحدة: نفس مسار أودو حرفياً. أكثر: نفس المسار مكرراً، لأن أي تعديل
     * آخر على printReceipt يجب أن يسري على كل نسخة.
     *
     * خدمة الطابعة لا ترمي عند الفشل: تعرض نافذة «إعادة المحاولة» بنفسها وترجع
     * undefined. لذلك نتوقف عند أول نتيجة فارغة ونقول كم نسخة خرجت، في إشعار
     * لا في نافذة، حتى لا نغطي نافذتها.
     *
     * بدون طابعة كاشير يفتح أودو نافذة طباعة المتصفح، ولها خانة نسخ خاصة بها،
     * فلا نفتحها أكثر من مرة. الطابعة تُقرأ من hardwareProxy كما تفعل خدمة
     * الطباعة نفسها لحظة الطباعة؛ printer.device يبقى فارغاً حتى أول طباعة.
     */
    async printReceiptCopies({ copies = 1, ...options } = {}) {
        if (copies <= 1 || !this.hardwareProxy?.printer) {
            return await this.printReceipt(options);
        }
        let printed = 0;
        let result;
        for (; printed < copies; printed++) {
            result = await this.printReceipt(options);
            if (!result) {
                break;
            }
        }
        if (printed < copies) {
            this.notification.add(
                `توقفت الطباعة: خرج ${printed ? copiesLabel(printed) : "لا شيء"} من ${copiesLabel(copies)}.`,
                { type: "danger", sticky: true }
            );
            return false;
        }
        this.notification.add(`تمت طباعة ${copiesLabel(copies)} من الفاتورة`, { type: "success" });
        return result;
    },
});

patch(ControlButtons.prototype, {
    /** «فاتورة»: فاتورة العميل قبل الدفع، بالعدد الذي يكتبه الكاشير. */
    async clickPrintBill() {
        if (!this.pos.getOrder()?.getOrderlines?.().length) {
            return;
        }
        const copies = await this.pos.askReceiptCopies();
        if (copies) {
            await this.pos.printReceiptCopies({ copies, printBillActionTriggered: true });
        }
    },
});

patch(ReceiptScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.doFullPrint = useTrackedAsync(() => this.printHosnyReceiptCopies(false));
        this.doBasicPrint = useTrackedAsync(() => this.printHosnyReceiptCopies(true));
    },

    /** «طباعة الإيصال» بعد الدفع يسأل عن عدد النسخ أيضاً. */
    async printHosnyReceiptCopies(basic) {
        const copies = await this.pos.askReceiptCopies();
        if (copies) {
            await this.pos.printReceiptCopies({ order: this.currentOrder, basic, copies });
        }
    },
});
