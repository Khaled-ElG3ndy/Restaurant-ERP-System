/** @odoo-module **/

/**
 * فتح وإغلاق الوردية (طلب 2026-10-10):
 *
 *   • كل وردية تبدأ من صفر: الافتتاح صفر دائماً، لأن الإغلاق يسلّم النقدية
 *     المعدودة كلها لخزنة الفرع (pos.session._hosny_handover على الخادم).
 *   • «الأجل» في نافذة الإغلاق: الكاشير يكتب إجمالي فواتير الأجل الورقية
 *     ويظهر الفرق — للمراجعة فقط، لا قيد (الأجل مسجل على حساب كل عميل).
 *   • ملخص الوردية: الخصومات والضيافة وبطاقات الهدايا والمرتجعات والإلغاءات.
 *   • ما كُتب في النافذة يُحفظ على الوردية قبل الإغلاق، ويُحفظ تقرير كامل بعده.
 *
 * كل ذلك يعمل فقط حين يكون لنقطة البيع «خزنة الفرع» (hosny_shift_zero_start)،
 * إلا كتابة الأجل والملخص فهما دائماً.
 */
import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ClosePosPopup } from "@point_of_sale/app/components/popups/closing_popup/closing_popup";
import { OpeningControlPopup } from "@point_of_sale/app/components/popups/opening_control_popup/opening_control_popup";

function hosnyZeroStart(pos) {
    return Boolean(pos.config.hosny_shift_zero_start);
}

patch(ClosePosPopup.prototype, {
    setup() {
        super.setup(...arguments);
        this.hosnySummary = useState({ data: null });
        onWillStart(async () => {
            try {
                this.hosnySummary.data = await this.pos.data.call("pos.session", "hosny_shift_close_summary", [
                    this.pos.session.id,
                ]);
            } catch {
                this.hosnySummary.data = null; // بلا اتصال: النافذة تعمل بدون الملخص
            }
        });
    },

    get hosnyZeroStart() {
        return hosnyZeroStart(this.pos);
    },

    /** الأجل: خانة يكتب فيها الكاشير إجمالي فواتيره (فارغة حتى يكتب). */
    getInitialState() {
        const state = super.getInitialState(...arguments);
        for (const pm of this.props.non_cash_payment_methods) {
            if (pm.type === "pay_later" && pm.number) {
                state.payments[pm.id] = { counted: "" };
            }
        }
        return state;
    },

    /** خانة الأجل الفارغة تعتبرها أودو «رقماً صالحاً»: لا إغلاق قبل كتابتها. */
    canConfirm() {
        const laterFilled = this.props.non_cash_payment_methods
            .filter((pm) => pm.type === "pay_later" && pm.number && this.state.payments[pm.id])
            .every((pm) => String(this.state.payments[pm.id].counted ?? "").trim() !== "");
        return laterFilled && super.canConfirm(...arguments);
    },

    async closeSession() {
        const counts = { cash: null, methods: {} };
        const cashId = this.props.default_cash_details?.id;
        for (const [id, payment] of Object.entries(this.state.payments)) {
            // parseValidFloat يقرأ «6,819.33» صحيحاً (parseFloat العادي يرجع 6)
            const value = this.env.utils.isValidFloat(payment.counted)
                ? this.env.utils.parseValidFloat(payment.counted)
                : null;
            if (Number(id) === cashId) {
                counts.cash = value;
            } else if (value !== null) {
                counts.methods[id] = value;
            }
        }
        try {
            await this.pos.data.call("pos.session", "hosny_save_close_counts", [this.pos.session.id, counts]);
        } catch {
            // الإغلاق لا يتوقف على حفظ الأرقام المكتوبة
        }
        return await super.closeSession(...arguments);
    },
});

patch(OpeningControlPopup.prototype, {
    setup() {
        super.setup(...arguments);
        if (hosnyZeroStart(this.pos)) {
            this.state.openingCash = "0";
        }
    },

    get hosnyZeroStart() {
        return hosnyZeroStart(this.pos);
    },
});
