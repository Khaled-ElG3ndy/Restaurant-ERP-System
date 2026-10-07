/** @odoo-module **/

/**
 * الكاشير أولاً: نقطة البيع تفتح على شاشة الأصناف بطلب سفري، بلا شاشة «اختر
 * مكان العمل». نوع الطلب (سفري / محلي) والطاولة يُختاران من الشريط أسفل
 * الأصناف (service_bar.js)، وخريطة الطاولات من زر «الطاولات» في الشريط العلوي.
 *
 * كل ما كان يرجع لخريطة الطاولات يمر بـ defaultPage: فتح نقطة البيع وفك
 * القفل، «إرسال الطلب» لطلب محلي، والطلب غير الموجود في الرابط. وبعد الدفع
 * (orderDone) طلب سفري جديد، محلياً كان المدفوع أو سفري.
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { dineInFloors } from "@pos_entry_selector/js/entry_selector";

patch(PosStore.prototype, {
    hosnyCashierFirst() {
        return Boolean(this.config.module_pos_restaurant && this.takeawayOrderType);
    },

    /** السفري المباشر (بلا طاولة). طلب الهاتف على طاولة «سفري» يُعامل كالمحلي. */
    hosnyIsOpenTakeaway(order) {
        return (
            Boolean(order) && !order.finalized && !order.isRefund && !order.table_id && this.isTakeawayOrder(order)
        );
    },

    /**
     * الطلب الذي يفتح عليه الكاشير: السفري المفتوح على الشاشة، ثم السفري الذي
     * تركه الكاشير ليفتح خريطة الطاولات (حتى لا تختفي أصنافه من أمامه)، وإلا
     * سفري فارغ.
     */
    hosnyCashierOrder() {
        const current = this.getOrder();
        if (this.hosnyIsOpenTakeaway(current)) {
            return current;
        }
        const resume = this.hosnyResumeOrderUuid
            ? this.models["pos.order"].getBy("uuid", this.hosnyResumeOrderUuid)
            : null;
        this.hosnyResumeOrderUuid = null;
        if (this.hosnyIsOpenTakeaway(resume)) {
            this.setOrder(resume);
            return resume;
        }
        return this.startTakeawayOrder();
    },

    get defaultPage() {
        if (this.hosnyCashierFirst()) {
            return {
                page: "ProductScreen",
                params: { orderUuid: this.hosnyCashierOrder().uuid },
            };
        }
        return super.defaultPage;
    },

    orderDone(order) {
        if (this.hosnyCashierFirst()) {
            order.setScreenData({ name: "" });
            this.searchProductWord = "";
            const next = this.startTakeawayOrder();
            this.navigate("ProductScreen", { orderUuid: next.uuid });
            return;
        }
        return super.orderDone(...arguments);
    },

    /**
     * خريطة الطاولات تبدأ على «أرضي» (أودو يبدأ بأول طابق في الإعدادات، وهو
     * VIP)، و F5 على رابطها (‎/pos/ui/<id>/floor‎) يفتح الكاشير أيضاً.
     */
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        if (this.hosnyCashierFirst()) {
            this.currentFloor = dineInFloors(this)[0] || this.currentFloor;
            if (this.router.state.current === "FloorScreen") {
                const next = this.defaultPage;
                this.router.navigate(next.page, next.params);
            }
        }
        return result;
    },

    /** زر الشريط العلوي: من الأصناف إلى خريطة الطاولات، ومن غيرها رجوع للكاشير. */
    hosnyTogglePlace() {
        if (this.router.state.current === "ProductScreen") {
            const order = this.getOrder();
            this.hosnyResumeOrderUuid =
                this.hosnyIsOpenTakeaway(order) && !order.isEmpty() ? order.uuid : null;
            // الخريطة تفتح على طابق طاولة الطلب، وإلا على آخر طابق فتحه الكاشير
            this.currentFloor = order?.table_id?.rootTable?.floor_id || this.currentFloor;
            this.navigate("FloorScreen");
            return;
        }
        const order = this.getOrder();
        if (order && !order.finalized) {
            this.navigate("ProductScreen", { orderUuid: order.uuid });
            return;
        }
        const next = this.defaultPage;
        this.navigate(next.page, next.params);
    },
});

patch(Navbar.prototype, {
    /**
     * شارة الـ navbar تلخّص نوع الطلب والطاولة الحالية. يبقى الشريط السفلي
     * مخصصاً للاختيار السريع فقط، فلا تتكرر تفاصيل الطاولة في المكانين.
     */
    get hosnyOrderTypeChip() {
        return super.hosnyOrderTypeChip;
    },
});
