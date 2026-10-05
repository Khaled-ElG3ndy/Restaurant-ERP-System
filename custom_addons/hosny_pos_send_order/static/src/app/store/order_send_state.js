/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosStore } from "@point_of_sale/app/services/pos_store";

const { DateTime } = luxon;

// =========================
// Order
// =========================
// `preparation_state` و `preparation_sent_at` حقلان حقيقيان على pos.order،
// فالنموذج العلائقي في أودو 19 يحمّلهما ويزامنهما تلقائياً. لا حاجة إلى
// init_from_JSON/export_as_JSON (غير موجودتين أصلاً في 19)، ولا إلى نسخة
// camelCase موازية في الذاكرة.
patch(PosOrder.prototype, {
    /** أول إرسال فقط هو ما يبدأ العدّاد؛ الإرسالات التالية لا تصفّره. */
    markPreparationSent() {
        if (!this.preparation_sent_at) {
            this.preparation_sent_at = DateTime.utc();
        }
        this.preparation_state = "sent";
    },

    /** حقل datetime يرجع كائن luxon من النموذج العلائقي، أو undefined. */
    getPreparationSentDate() {
        const value = this.preparation_sent_at;
        return value && value.isValid ? value : null;
    },
});

// =========================
// POS Store
// =========================
patch(PosStore.prototype, {
    /**
     * نفس ما يعتبره أودو «تغييراً يستحق الإرسال»: كمية، أو ملاحظة سطر، أو
     * ملاحظة عامة/داخلية. nbrOfChanges وحده لا يحسب تغيير الملاحظات.
     */
    hasPreparationChanges(order) {
        const changes = this.getOrderChanges(order);
        return Boolean(
            changes.nbrOfChanges ||
                Object.keys(changes.noteUpdate || {}).length ||
                changes.general_customer_note !== undefined ||
                changes.internal_note !== undefined
        );
    },

    /**
     * زر «إرسال الطلب».
     *
     * الاستدعاء الأصلي هو خط الإرسال كله: كشف انقطاع الشبكة، التحقق من أن
     * الطلب لم يُعدَّل على جهاز آخر، إطلاق الطبق الأول، ثم الطباعة عبر
     * printChanges — وهي نقطة دخول hosny_pos_printer_matrix (أنواع الفواتير،
     * عدد النسخ، القوالب، التذكرة المجمّعة، توجيه الأصناف). لذلك نستدعي super
     * ولا نبني مساراً موازياً؛ دورنا هنا هو ختم وقت الإرسال فقط.
     *
     * الأخطاء تُترك تصعد كما هي: لو فشل الإرسال يجب أن يرى الكاشير ذلك بدل
     * أن يظهر الطلب مُرسَلاً وهو لم يصل المطبخ.
     */
    async sendOrderInPreparationUpdateLastChange(order, opts = {}) {
        const hadChanges = !opts.cancelled && this.hasPreparationChanges(order);

        const result = await super.sendOrderInPreparationUpdateLastChange(order, opts);

        if (hadChanges) {
            order.markPreparationSent();
            // مسار الدفع (_askForPreparation) لا يستدعي addPendingOrder،
            // فنضيفه هنا حتى يصل الختم إلى الخادم في الحالتين.
            this.addPendingOrder([order.id]);
        }

        return result;
    },
});
