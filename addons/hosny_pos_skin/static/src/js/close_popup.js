/** @odoo-module **/

/**
 * «إغلاق الوردية»: كل المبالغ «395.82 SR» — الرقم ثم الرمز (2026-10-07).
 *
 * قالب ClosePosPopup ومكوّن الإيرادات/النفقات داخله يستعملان
 * env.utils.formatCurrency مباشرة، فيخرج الرمز قبل الرقم. نستبدله لهذه
 * النافذة وأبنائها فقط (useSubEnv) بنفس صيغة شاشة الدفع: الرقم ثم الرمز،
 * معزولين LTR حتى لا تقلبهما الواجهة العربية. بدون رمز (hasSymbol=false)
 * يبقى كما هو.
 */
import { useSubEnv } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup(...arguments);
        const utils = this.env.utils;
        const symbol = this.pos?.currency?.symbol ?? "";
        useSubEnv({
            utils: {
                ...utils,
                formatCurrency: (amount, hasSymbol = true, ...rest) => {
                    if (!hasSymbol || !symbol) {
                        return utils.formatCurrency(amount, hasSymbol, ...rest);
                    }
                    const number = utils.formatCurrency(amount, false, ...rest);
                    return `⁦${number} ${symbol}⁩`;
                },
            },
        });
    },
});
