/** رسم التذاكر واحدة واحدة، والإرسال للطابعات بالتوازي */
import { ConnectionLostError } from "@web/core/network/rpc";
import { htmlToCanvas } from "@point_of_sale/app/services/render_service";
import { BasePrinter } from "@point_of_sale/app/utils/printer/base_printer";
import { patch } from "@web/core/utils/patch";

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
    /** نفس منطق الأصل حرفياً، عدا أن الرسم يمر عبر renderExclusive. */
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
            try {
                printResult = await this.sendPrintingJob(image);
            } catch (error) {
                this.receiptQueue.length = 0;
                if (error instanceof ConnectionLostError) {
                    return this.getOfflineError();
                }
                return this.getActionError();
            }
            if (!printResult || printResult.result === false) {
                this.receiptQueue.length = 0;
                return this.getResultsError(printResult);
            }
        }
        return {
            successful: true,
            warningCode: this.getResultWarningCode(printResult),
        };
    },
});
