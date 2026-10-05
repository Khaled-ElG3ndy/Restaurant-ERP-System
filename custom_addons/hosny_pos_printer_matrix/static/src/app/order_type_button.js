/** زر اختيار نوع الفاتورة داخل شاشة نقاط البيع */
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { patch } from "@web/core/utils/patch";

/**
 * شارة نوع الفاتورة في الشريط العلوي (شاشة الأصناف): «سفري» أو «محلي · رقم
 * الطاولة». الضغط عليها يبدّل بين محلي وسفري. زر «نوع الفاتورة» الكامل في
 * أزرار التحكم مخفي في تصميم الفروع (شبكة الـ 8 أزرار)، فهذه هي الواجهة.
 */
patch(Navbar.prototype, {
    get hosnyOrderTypeChip() {
        const pos = this.pos;
        if (!pos.config.module_pos_restaurant || pos.router.state.current !== "ProductScreen") {
            return null;
        }
        const order = pos.getOrder();
        if (!order || order.finalized || order.isRefund) {
            return null;
        }
        const takeaway = pos.isTakeawayOrder(order);
        const type = pos.getEffectiveOrderType(order);
        const table = order.table_id?.rootTable || order.table_id || null;
        return {
            takeaway,
            label: type?.name || "",
            tableNumber: !takeaway && table ? table.table_number : null,
            floorName: !takeaway && table ? table.floor_id?.name || "" : "",
        };
    },

    clickHosnyOrderTypeChip() {
        return this.pos.chooseServiceType(this.pos.getOrder());
    },
});

patch(ControlButtons.prototype, {
    get orderTypes() {
        return this.pos.models["pos.order.type"]?.getAll?.() || [];
    },

    get currentOrderTypeName() {
        const type = this.pos.getEffectiveOrderType(this.pos.getOrder());
        return type?.name || "نوع الفاتورة";
    },

    async clickOrderType() {
        const order = this.pos.getOrder();
        if (!order) {
            return;
        }
        const types = [...this.orderTypes].sort(
            (a, b) => (a.sequence || 0) - (b.sequence || 0)
        );
        const selected = await makeAwaitable(this.dialog, SelectionPopup, {
            title: "نوع الفاتورة",
            list: types.map((t) => ({
                id: t.id,
                label: t.name,
                isSelected: this.pos.getEffectiveOrderType(order)?.id === t.id,
                item: t,
            })),
        });
        if (selected) {
            // نفس قواعد التبديل: السفري يُفرغ الطاولة، والمحلي يحتاج طاولة.
            this.pos.switchOrderType(order, selected);
        }
    },
});
