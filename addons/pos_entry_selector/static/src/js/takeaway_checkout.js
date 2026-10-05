/** @odoo-module **/

/**
 * إقفال دورة «سفري» بعد إرسال الطلب:
 *
 *  1. تُرسل تذكرة التحضير أولاً عبر submitOrder المعتاد.
 *  2. عند نجاح الإرسال فقط نفتح شاشة الدفع لاختيار نقدي / آجل / شبكة.
 *  3. لا نسمح بالرجوع لشاشة الأصناف لهذا الطلب، حتى لا يُعدَّل بعد وصوله
 *     للمطبخ.
 *  4. بعد اعتماد الدفع ينشئ orderDone طلب سفرياً جديداً فوراً.
 *  5. نفس الإقفال حين يبدأ الكاشير بـ«الدفع» مباشرة: لو أرسل الطلب من سؤال
 *     «لم يتم إرسال الطلب» يُقفل الرجوع، وفي كل الأحوال يُفتح سفري جديد بعد
 *     الدفع بدل شاشة الإيصال.
 *
 * لا نغيّر مسار المحلي إطلاقاً، ولا نعتمد على اسم وسيلة الدفع: شاشة الدفع
 * تقرأ الوسائل المعرّفة للفرع نفسه، فتظل مطابقة لإعدادات كل فرع.
 */
import { useEffect } from "@odoo/owl";
import { FeedbackScreen } from "@point_of_sale/app/screens/feedback_screen/feedback_screen";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

const hasUnsentPreparationChanges = (pos, order) => {
    if (typeof pos.hasPreparationChanges === "function") {
        return pos.hasPreparationChanges(order);
    }
    const changes = pos.getOrderChanges(order);
    return Boolean(
        changes?.nbrOfChanges ||
            Object.keys(changes?.noteUpdate || {}).length ||
            changes?.general_customer_note !== undefined ||
            changes?.internal_note !== undefined
    );
};

patch(PosStore.prototype, {
    /** الطلب الذي انتقل للدفع بعد إرساله ولا يجوز تعديله من شاشة الأصناف. */
    hosnyIsTakeawayCheckoutLocked(order) {
        return Boolean(order?.uiState?.hosnyTakeawayCheckoutRequired);
    },

    hosnyNeedsTakeawayCheckout(order) {
        return Boolean(
            this.hosnyCashierFirst?.() &&
                order &&
                !order.finalized &&
                !order.isRefund &&
                !order.isEmpty?.() &&
                this.isTakeawayOrder?.(order)
        );
    },

    /** كل سفري يُدفع من الكاشير ينتهي بسفري جديد، أياً كان الزر الذي بدأ منه. */
    hosnyTakeawayAutoNext(order) {
        return Boolean(
            this.hosnyIsTakeawayCheckoutLocked(order) ||
                (this.hosnyCashierFirst?.() &&
                    order &&
                    !order.isRefund &&
                    this.isTakeawayOrder?.(order))
        );
    },

    /** نضع القفل بعد نجاح الإرسال، ثم ننتقل إلى طرق الدفع المعرفة في الفرع. */
    hosnyStartTakeawayCheckout(order) {
        if (!this.hosnyNeedsTakeawayCheckout(order)) {
            return;
        }
        order.uiState ??= {};
        order.uiState.hosnyTakeawayCheckoutRequired = true;
        this.mobile_pane = "right";
        this.navigate("PaymentScreen", { orderUuid: order.uuid });
    },

    /**
     * submitOrder يتأكد من العميل/الضيوف، يرسل التحضير ويزامن الطلب. لا نفتح
     * الدفع إلا بعد أن ينجح هذا المسار؛ فلو فشل الاتصال يبقى الطلب على الشاشة
     * ولا تُسجل له وسيلة دفع بالخطأ.
     */
    async submitOrder() {
        const order = this.getOrder();
        const mustCheckout =
            this.hosnyNeedsTakeawayCheckout(order) && hasUnsentPreparationChanges(this, order);
        const result = await super.submitOrder(...arguments);
        if (mustCheckout && !order.finalized) {
            this.hosnyStartTakeawayCheckout(order);
        }
        return result;
    },

    /**
     * «الدفع» مباشرة: pos_restaurant يسأل «لم يتم إرسال الطلب» ثم يرسل. لو
     * وصل المطبخ فعلاً نُقفل الرجوع كما في «إرسال الطلب»؛ لو اختار «إهمال»
     * يبقى الرجوع متاحاً.
     */
    async pay() {
        const order = this.getOrder();
        const mustLock =
            this.hosnyNeedsTakeawayCheckout(order) && hasUnsentPreparationChanges(this, order);
        const result = await super.pay(...arguments);
        if (
            mustLock &&
            this.getOrder() === order &&
            !order.finalized &&
            this.router.state.current === "PaymentScreen" &&
            !hasUnsentPreparationChanges(this, order)
        ) {
            order.uiState ??= {};
            order.uiState.hosnyTakeawayCheckoutRequired = true;
        }
        return result;
    },

    /** لا نعيد سفري المُرسل للمطبخ إلى شاشة تعديل الأصناف. */
    async onClickBackButton() {
        if (
            this.router.state.current === "PaymentScreen" &&
            this.hosnyIsTakeawayCheckoutLocked(this.getOrder())
        ) {
            this.notification.add(
                _t("تم إرسال الأوردر للمطبخ. اختر وسيلة الدفع لإتمامه."),
                { type: "warning" }
            );
            return;
        }
        return await super.onClickBackButton(...arguments);
    },
});

patch(OrderPaymentValidation.prototype, {
    /**
     * بعد نجاح الدفع نستخدم FeedbackScreen كجسر قصير ينتظر مزامنة الاعتماد؛
     * امتداده أدناه ينتقل فور اكتمالها إلى orderDone، الذي يفتح سفرياً جديداً.
     */
    get nextPage() {
        if (this.pos.hosnyTakeawayAutoNext?.(this.order)) {
            this.order.uiState ??= {};
            this.order.uiState.hosnyTakeawayAutoNext = true;
            return {
                page: "FeedbackScreen",
                params: { orderUuid: this.order.uuid },
            };
        }
        return super.nextPage;
    },

    /**
     * لا شاشة إيصال للسفري. فاتورته تخرج عادة مع أول إرسال؛ لو دُفع دون أن
     * يُرسل («الدفع» ثم «إهمال») نطبعها هنا مرة واحدة قبل فتح السفري الجديد.
     */
    async afterOrderValidation() {
        const result = await super.afterOrderValidation(...arguments);
        if (
            this.order?.uiState?.hosnyTakeawayAutoNext &&
            !this.order.uiState.hosnyReceiptPrinted &&
            !this.order.nb_print &&
            !this.pos.config.iface_print_auto
        ) {
            try {
                await this.pos.printReceipt({ order: this.order });
            } catch (error) {
                console.warn("[Hosny] takeaway receipt after payment failed", error);
            }
        }
        return result;
    },
});

patch(FeedbackScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.hosnyTakeawayNextOrderOpened = false;
        useEffect(
            () => {
                if (
                    !this.state.loading &&
                    !this.hosnyTakeawayNextOrderOpened &&
                    this.currentOrder?.uiState?.hosnyTakeawayAutoNext
                ) {
                    this.hosnyTakeawayNextOrderOpened = true;
                    // orderDone في cashier_first/order_type_rules ينشئ سفرياً
                    // فارغاً وينقله إلى شاشة الأصناف.
                    this.goNext();
                }
            },
            () => [this.state.loading]
        );
    },
});
