/** رسم التذاكر واحدة واحدة، والإرسال للطابعات بالتوازي */
import { ConnectionLostError } from "@web/core/network/rpc";
import { htmlToCanvas } from "@point_of_sale/app/services/render_service";
import { BasePrinter } from "@point_of_sale/app/utils/printer/base_printer";
import { patch } from "@web/core/utils/patch";
import { notePrintedCopy, remainingCopies, setRemainingCopies } from "./receipt_copies";

/**
 * أودو يرسم كل تذكرة داخل `.render-container` بعد أن يحذف منه كل عنصر يحمل
 * نفس الكلاس (`pos-receipt-print`). لو رُسمت تذكرتان في نفس اللحظة (فاتورة
 * العميل مع تذكرة المطبخ، أو محطتان معاً) تمسح الثانية الأولى من الصفحة قبل
 * أن تتحول لصورة، فتخرج فارغة. نجعل مرحلة الرسم بالدور، والانتظار على شبكة
 * الطابعة — وهو الجزء البطيء — يبقى متوازياً.
 */
let renderChain = Promise.resolve();

function renderExclusive(job) {
    const run = renderChain.then(job, job);
    renderChain = run.catch(() => {});
    return run;
}

patch(BasePrinter.prototype, {
    /**
     * نفس منطق الأصل حرفياً، عدا أن الرسم يمر عبر renderExclusive، وأن
     * الفاتورة المطلوبة بأكثر من نسخة (receipt_copies.js) تُرسم مرة واحدة
     * وتُرسل صورتها بعدد النسخ، ورا بعض على نفس الطابعة.
     */
    async printReceipt(receipt) {
        if (receipt) {
            this.receiptQueue.push(receipt);
        }
        let image, printResult;
        while (this.receiptQueue.length > 0) {
            receipt = this.receiptQueue.shift();
            image = await renderExclusive(async () =>
                this.processCanvas(await htmlToCanvas(receipt, { addClass: "pos-receipt-print" }))
            );
            for (let left = remainingCopies(receipt); left > 0; left--) {
                try {
                    printResult = await this.sendPrintingJob(image);
                } catch (error) {
                    setRemainingCopies(receipt, left);
                    this.receiptQueue.length = 0;
                    if (error instanceof ConnectionLostError) {
                        return this.getOfflineError();
                    }
                    return this.getActionError();
                }
                if (!printResult || printResult.result === false) {
                    setRemainingCopies(receipt, left);
                    this.receiptQueue.length = 0;
                    return this.getResultsError(printResult);
                }
                notePrintedCopy(receipt);
            }
            setRemainingCopies(receipt, 0);
        }
        return {
            successful: true,
            warningCode: this.getResultWarningCode(printResult),
        };
    },
});
