/**
 * نوع الطلب والطاولة: السفري لا طاولة له، والطاولة تعني «محلي» — إلا طاولات
 * طابق «سفري» (2026-10-07): طلب الهاتف السفري يُحجز على «سفري 1…15» ليُتابَع
 * حتى يصل العميل؛ الطلب عليها سفري ويبقى على طاولته، ويعود للخريطة كالمحلي.
 *
 * النوع (order_type_id) هو المرجع والطاولة تتبعه، ونفس القاعدة على الخادم في
 * models/pos_order.py. «سفري» (code = safari) هو نوع السفري المعتمد.
 *   • طلب جديد على طاولة ← محلي، وبدون طاولة ← سفري (قسمة الفاتورة تأخذ نوع أصلها).
 *   • تحويل السفري لطاولة يجعله محلياً، والتحويل من محلي لسفري يُفرغ الطاولة.
 *   • السفري لا يرجع لخريطة الطاولات: بعد «إرسال الطلب» يبقى على الشاشة، وبعد
 *     الدفع يفتح طلب سفري جديد.
 */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { patch } from "@web/core/utils/patch";

// نفس القائمة في models/pos_order_type.py
export const TABLELESS_ORDER_TYPE_CODES = new Set(["safari", "takeaway", "delivery"]);
export const TAKEAWAY_ORDER_TYPE_CODE = "safari";
export const LOCAL_ORDER_TYPE_CODE = "local";
// نفس النمط في models/pos_order.py و pos_entry_selector (isTakeawayFloor).
const TAKEAWAY_FLOOR = /سفري|takeaway|take away|تيك/i;

/** طاولة على طابق «سفري»: طلبها سفري ويحتفظ بها. */
export function isTakeawayTable(table) {
    const floor = table?.floor_id || table?.rootTable?.floor_id;
    return Boolean(floor && TAKEAWAY_FLOOR.test(String(floor.name || "")));
}

patch(PosStore.prototype, {
    getOrderTypeByCode(code) {
        return this.models["pos.order.type"]?.find((type) => type.code === code) || null;
    },

    get localOrderType() {
        return this.getOrderTypeByCode(LOCAL_ORDER_TYPE_CODE) || this.defaultOrderType;
    },

    get takeawayOrderType() {
        return this.getOrderTypeByCode(TAKEAWAY_ORDER_TYPE_CODE);
    },

    orderTypeRequiresTable(type) {
        return !type || !TABLELESS_ORDER_TYPE_CODES.has(type.code);
    },

    isTakeawayOrder(order) {
        return Boolean(order) && !this.orderTypeRequiresTable(this.getEffectiveOrderType(order));
    },

    resolveTable(table) {
        return table && typeof table !== "object" ? this.models["restaurant.table"]?.get(table) : table || null;
    },

    /** طلب سفري على طاولة من طابق «سفري» (طلبات الهاتف). */
    isTakeawayTableOrder(order) {
        return Boolean(order?.table_id) && isTakeawayTable(this.resolveTable(order.table_id));
    },

    /** نوع الطلب الجديد لو لم يُحدَّد. */
    newOrderType(data) {
        if (data.table_id) {
            return isTakeawayTable(this.resolveTable(data.table_id))
                ? this.takeawayOrderType || this.localOrderType
                : this.localOrderType;
        }
        // قسمة الفاتورة تنشئ الجزء الجديد بلا طاولة: يبقى من نوع الطلب الأصلي.
        const current = this.getOrder();
        if (this.router?.state?.current === "SplitBillScreen" && current?.order_type_id) {
            return current.order_type_id;
        }
        return this.takeawayOrderType || this.localOrderType;
    },

    createNewOrder(data = {}) {
        if (this.config.module_pos_restaurant && !data.order_type_id) {
            const type = this.newOrderType(data);
            if (type) {
                data = { ...data, order_type_id: type };
            }
        }
        const order = super.createNewOrder(data);
        this.applyOrderTypeRules(order);
        return order;
    },

    /** السفري بلا طاولة، إلا على طاولات «سفري» فالطلب عليها سفري دائماً. */
    applyOrderTypeRules(order) {
        if (!order || order.finalized || !order.table_id) {
            return;
        }
        if (this.isTakeawayTableOrder(order)) {
            if (!this.isTakeawayOrder(order) && this.takeawayOrderType) {
                order.order_type_id = this.takeawayOrderType;
            }
            return;
        }
        if (this.isTakeawayOrder(order)) {
            order.table_id = false;
        }
    },

    /**
     * اسم عائم من البداية (رقم التتبّع، كما يسمّي أودو أي طلب بلا طاولة عند أول
     * مزامنة) حتى لا يعامله أودو كـ«بيع مباشر» ينتظر طاولة: الضغط على طاولة
     * في الخريطة كان سيحوّل السفري إليها.
     */
    nameTakeawayOrder(order) {
        if (order && !order.finalized && !order.table_id && !order.floating_order_name && this.isTakeawayOrder(order)) {
            order.floating_order_name = order.floatingOrderName || order.pos_reference || "";
        }
    },

    setOrderType(order, type) {
        if (!order || !type) {
            return;
        }
        order.order_type_id = type;
        this.applyOrderTypeRules(order);
        this.nameTakeawayOrder(order);
        this.addPendingOrder([order.id]);
    },

    /**
     * التبديل بين محلي وسفري. السفري يُفرغ الطاولة فوراً؛ المحلي بدون طاولة
     * يفتح اختيار الطاولة (نفس «تحويل»)، ولا يصير محلياً إلا عند اختيارها —
     * لو رجع الكاشير بدون طاولة يبقى الطلب سفري.
     */
    switchOrderType(order, type) {
        if (!order || !type || order.finalized) {
            return;
        }
        if (this.orderTypeRequiresTable(type) && !order.table_id) {
            order.uiState.hosnyTypeOnTable = type;
            this.startTransferOrder();
            return;
        }
        this.setOrderType(order, type);
    },

    async chooseServiceType(order = this.getOrder()) {
        const local = this.localOrderType;
        const takeaway = this.takeawayOrderType;
        if (!order || !local || !takeaway) {
            return;
        }
        const current = this.isTakeawayOrder(order) ? takeaway : local;
        const selected = await makeAwaitable(this.dialog, SelectionPopup, {
            title: "نوع الفاتورة",
            list: [local, takeaway].map((type) => ({
                id: type.id,
                label: type.name,
                isSelected: type.id === current.id,
                item: type,
            })),
        });
        if (selected && selected.id !== current.id) {
            this.switchOrderType(order, selected);
        }
    },

    /** طلب سفري فارغ نبدأ به: نعيد استخدام الفارغ غير المُرسَل بدل تكديس طلبات فارغة. */
    startTakeawayOrder() {
        let order = this.models["pos.order"].find(
            (o) =>
                !o.finalized &&
                !o.isSynced &&
                !o.isRefund &&
                o.isEmpty() &&
                !o.payment_ids.length &&
                this.isTakeawayOrder(o)
        );
        if (!order) {
            order = this.createNewOrder({ order_type_id: this.takeawayOrderType });
        }
        this.applyOrderTypeRules(order);
        this.nameTakeawayOrder(order);
        this.setOrder(order);
        return order;
    },

    // ── الطاولة تجعل الطلب محلياً ─────────────────────────────────────────

    /** التحويل لطاولة فارغة يضع الطاولة على الطلب نفسه. */
    prepareOrderTransfer(order, destinationTable) {
        const result = super.prepareOrderTransfer(...arguments);
        this.seatOrder(order);
        return result;
    },

    /** أودو يعيد استخدام أي طلب فارغ بلا طاولة لطاولة جديدة. */
    async setTable(table, orderUuid = null) {
        const result = await super.setTable(...arguments);
        this.seatOrder(this.getOrder());
        return result;
    },

    seatOrder(order) {
        if (order?.table_id && !order.finalized && this.isTakeawayTableOrder(order)) {
            if (!this.isTakeawayOrder(order) && this.takeawayOrderType) {
                order.order_type_id = this.takeawayOrderType;
                this.addPendingOrder([order.id]);
            }
        } else if (order?.table_id && !order.finalized && this.isTakeawayOrder(order)) {
            const type = order.uiState?.hosnyTypeOnTable || this.localOrderType;
            order.order_type_id = type;
            this.addPendingOrder([order.id]);
        }
        if (order?.uiState) {
            delete order.uiState.hosnyTypeOnTable;
        }
    },

    async preSyncAllOrders(orders) {
        if (this.config.module_pos_restaurant) {
            for (const order of orders) {
                if (!order.order_type_id && !order.finalized) {
                    order.order_type_id = this.newOrderType({ table_id: order.table_id });
                }
                this.applyOrderTypeRules(order);
            }
        }
        return super.preSyncAllOrders(...arguments);
    },

    // ── السفري لا يرجع لخريطة الطاولات ───────────────────────────────────

    /** بعد «إرسال الطلب»: السفري يبقى على الشاشة حتى الدفع. */
    showDefault() {
        const order = this.getOrder();
        if (this.config.module_pos_restaurant && order && !order.finalized && this.isTakeawayOrder(order) && !order.table_id) {
            this.navigate("ProductScreen", { orderUuid: order.uuid });
            return;
        }
        return super.showDefault(...arguments);
    },

    /** بعد الدفع: طلب سفري جديد مباشرة بدل خريطة الطاولات. */
    orderDone(order) {
        if (this.config.module_pos_restaurant && order && this.isTakeawayOrder(order) && !order.table_id) {
            order.setScreenData({ name: "" });
            this.searchProductWord = "";
            const next = this.startTakeawayOrder();
            this.navigate("ProductScreen", { orderUuid: next.uuid });
            return;
        }
        return super.orderDone(...arguments);
    },
});
