/** @odoo-module **/

/**
 * إقفال دورة «سفري» بعد إرسال الطلب (إجباري):
 *
 *  1. «إرسال الطلب» يرسل تذكرة التحضير و**ينتظر** نجاحها (submitOrder في
 *     أودو لا ينتظرها) — لو انقطع الاتصال أو عُدِّل الطلب من جهاز آخر أو بقي
 *     شيء لم يُرسل، يبقى الطلب على شاشة الأصناف مع رسالة، ولا يُفتح الدفع.
 *  2. بعد النجاح تُفتح شاشة الدفع مباشرة لاختيار نقدي / آجل / شبكة. سفري كل
 *     أصنافه خارج طابعات التحضير (لا شيء يُرسل) يذهب للدفع مباشرة أيضاً.
 *  3. الطلب مقفول على الدفع: لا رجوع لشاشة الأصناف ولا خروج لأي شاشة أخرى
 *     (الرئيسية، الطلبات، الطاولات…) حتى يُدفع. المخرج الوحيد «إلغاء الطلب»
 *     — باعتماد الإلغاء لأن أصنافه وصلت المطبخ.
 *  4. بعد اعتماد الدفع ينشئ orderDone طلب سفرياً جديداً فوراً.
 *  5. نفس الإقفال حين يبدأ الكاشير بـ«الدفع» مباشرة: لو أرسل الطلب من سؤال
 *     «لم يتم إرسال الطلب» يُقفل، وفي كل الأحوال يُفتح سفري جديد بعد الدفع
 *     بدل شاشة الإيصال.
 *
 * لا نغيّر مسار المحلي إطلاقاً، ولا نعتمد على اسم وسيلة الدفع: شاشة الدفع
 * تقرأ الوسائل المعرّفة للفرع نفسه، فتظل مطابقة لإعدادات كل فرع.
 */
import { useEffect } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { FeedbackScreen } from "@point_of_sale/app/screens/feedback_screen/feedback_screen";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

/** الشاشات المسموحة لسفري مقفول على الدفع. */
const CHECKOUT_PAGES = new Set(["PaymentScreen", "FeedbackScreen", "ReceiptScreen"]);

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
                this.isTakeawayOrder?.(order) &&
                // طلب الهاتف على طاولة «سفري» يُرسل ويعود للخريطة حتى يصل العميل
                !order.table_id
        );
    },

    /**
     * بعد «إغلاق الفاتورة» من الكاشير: لا شاشة إيصال — تُطبع الفاتورة تلقائياً
     * ويُفتح طلب جديد (2026-10-09: المحلي أيضاً، كان يقف على شاشة الإيصال
     * والطباعة اليدوية). المرتجع يبقى على مساره.
     */
    hosnyTakeawayAutoNext(order) {
        return Boolean(
            this.hosnyIsTakeawayCheckoutLocked(order) ||
                (this.hosnyCashierFirst?.() && order && !order.isRefund)
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
     * «إرسال الطلب» لسفري الكاشير. أودو (pos_restaurant) يطلق الإرسال ولا
     * ينتظره ثم يعرض الشاشة الافتراضية؛ هنا ننتظره حتى لا يُفتح الدفع لطلب لم
     * يصل المطبخ. باقي الطلبات (المحلي، طاولات «سفري») تمر كما هي.
     */
    async submitOrder() {
        const order = this.getOrder();
        if (!this.hosnyNeedsTakeawayCheckout(order)) {
            return await super.submitOrder(...arguments);
        }
        await this.ensureGuestCustomerCount?.(order);
        if (hasUnsentPreparationChanges(this, order)) {
            const ui = this.env.services.ui;
            ui?.block();
            try {
                await this.sendOrderInPreparationUpdateLastChange(order);
            } catch (error) {
                console.warn("[Hosny] takeaway send failed", error);
                this.notification.add(
                    this.data?.network?.offline
                        ? _t("لا يوجد اتصال — لم يُرسل الطلب للمطبخ. حاول مرة أخرى عند عودة الاتصال.")
                        : _t("تعذّر إرسال الطلب للمطبخ — حاول مرة أخرى."),
                    { type: "danger" }
                );
                return false;
            } finally {
                ui?.unblock();
            }
            if (hasUnsentPreparationChanges(this, order)) {
                // مثلاً «الطلب عُدِّل من جهاز آخر»: أودو يحدّث الطلب ولا يرسل
                this.notification.add(_t("لم يُرسل الطلب كاملاً للمطبخ — راجع الأصناف واضغط «إرسال الطلب» مرة أخرى."), {
                    type: "warning",
                });
                return false;
            }
        }
        if (order.finalized || this.getOrder() !== order) {
            return true;
        }
        this.hosnyStartTakeawayCheckout(order);
        return true;
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

    /** سفري مقفول على الدفع ولم يُدفع بعد — الطلب الحالي فقط. */
    hosnyCheckoutHoldsScreen() {
        const order = this.getOrder();
        return Boolean(
            order &&
                !order.finalized &&
                this.hosnyIsTakeawayCheckoutLocked(order) &&
                this.router?.state?.current === "PaymentScreen"
        );
    },

    /**
     * لا خروج من الدفع لسفري مُرسل: الرجوع، الرئيسية، الطلبات، الطاولات…
     * كلها تمر من navigate. ما بعد الدفع (Feedback / Receipt / orderDone) مسموح
     * لأن الطلب يصبح finalized.
     */
    navigate(routeName, routeParams = {}) {
        if (!CHECKOUT_PAGES.has(routeName) && this.hosnyCheckoutHoldsScreen()) {
            this.hosnyWarnCheckoutLocked();
            return false;
        }
        return super.navigate(...arguments);
    },

    /** لا نعيد سفري المُرسل للمطبخ إلى شاشة تعديل الأصناف. */
    async onClickBackButton() {
        if (this.hosnyCheckoutHoldsScreen()) {
            this.hosnyWarnCheckoutLocked();
            return;
        }
        return await super.onClickBackButton(...arguments);
    },

    /**
     * «أكمل الدفع» أو «إلغاء الطلب». الإلغاء يمر من onDeleteOrder، فيطلب
     * اعتماد إلغاء الأصناف المرسلة (void_approval في hosny_pos_controls)،
     * ثم يفتح سفرياً جديداً.
     */
    hosnyWarnCheckoutLocked() {
        if (this._hosnyCheckoutPrompt) {
            return;
        }
        const order = this.getOrder();
        this._hosnyCheckoutPrompt = true;
        this.dialog.add(
            ConfirmationDialog,
            {
                title: _t("الطلب السفري لم يُدفع"),
                body: _t("تم إرسال الطلب للمطبخ. اختر وسيلة الدفع لإتمامه، أو ألغِ الطلب (يحتاج اعتماد الإلغاء)."),
                confirmLabel: _t("أكمل الدفع"),
                confirm: () => {},
                cancelLabel: _t("إلغاء الطلب"),
                // إغلاق النافذة بـ× أو Esc لا يلغي الطلب
                dismiss: () => {},
                cancel: async () => {
                    const deleted = await this.onDeleteOrder(order);
                    if (deleted) {
                        const next = this.defaultPage;
                        this.navigate(next.page, next.params);
                    }
                },
            },
            { onClose: () => (this._hosnyCheckoutPrompt = false) }
        );
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
     * لا شاشة إيصال، فالفاتورة تُطبع هنا مرة واحدة قبل فتح الطلب الجديد:
     *   • المحلي (على طاولة): دائماً — فاتورة «تم التسديد»، حتى لو طُبعت فاتورة
     *     الحساب قبل الدفع.
     *   • السفري: فاتورته تخرج عادة مع أول إرسال؛ لو دُفع دون أن يُرسل
     *     («الدفع» ثم «إهمال») تُطبع هنا.
     * طباعة أودو التلقائية (iface_print_auto) لو مفعّلة تكفي عن هذه.
     */
    async afterOrderValidation() {
        const result = await super.afterOrderValidation(...arguments);
        const order = this.order;
        const alreadyPrinted = order?.table_id
            ? false
            : order?.uiState?.hosnyReceiptPrinted || order?.nb_print;
        if (
            order?.uiState?.hosnyTakeawayAutoNext &&
            !alreadyPrinted &&
            !this.pos.config.iface_print_auto
        ) {
            try {
                await this.pos.printReceipt({ order });
            } catch (error) {
                console.warn("[Hosny] receipt after payment failed", error);
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
