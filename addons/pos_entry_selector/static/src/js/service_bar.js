/** @odoo-module **/

/**
 * شريط نوع الطلب أسفل الأصناف (على نسق شريط FERP): «سفري» / «محلي» والطاولة.
 *
 *   • سفري ← محلي، أو الضغط على خانة الطاولة: نافذة الطاولات. الطاولة الفارغة
 *     تُجلس الطلب عليها (فيصير محلياً). المشغولة تفتح طلبها لو كان الطلب الحالي
 *     فارغاً، وإلا تُضاف أصنافه لطلبها بعد التأكيد (نفس «تحويل» في أودو).
 *   • محلي ← سفري: يُفصل الطلب عن طاولته، بتأكيد لو كان فيه أصناف.
 *
 * قواعد النوع والطاولة نفسها في hosny_pos_printer_matrix/order_type_rules.js:
 * الطاولة تعني محلي، والسفري بلا طاولة.
 */
import { Component, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ask, makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { dineInFloors } from "@pos_entry_selector/js/entry_selector";

function tableTitle(table) {
    return table.floor_id?.name ? `${table.table_number} · ${table.floor_id.name}` : `${table.table_number}`;
}

export class HosnyTablePicker extends Component {
    static template = "pos_entry_selector.HosnyTablePicker";
    static components = { Dialog };
    static props = { order: Object, getPayload: Function, close: Function };

    setup() {
        this.pos = usePos();
        const floors = this.floors;
        const current = this.props.order.table_id?.rootTable;
        const floor = floors.find((f) => f.id === current?.floor_id?.id) || floors[0];
        this.state = useState({ floorId: floor?.id || null });
        // طلبات الأجهزة الأخرى على الطاولات، قبل أن يختار الكاشير
        this.pos.deviceSync?.readDataFromServer?.();
    }

    get floors() {
        return dineInFloors(this.pos);
    }

    get floor() {
        return this.floors.find((floor) => floor.id === this.state.floorId) || null;
    }

    get tables() {
        return [...(this.floor?.table_ids || [])]
            .filter((table) => table.active !== false)
            .sort((a, b) => a.table_number - b.table_number || a.id - b.id);
    }

    get title() {
        return this.props.order.table_id ? "تغيير الطاولة" : "اختر الطاولة";
    }

    /** الطلبات المفتوحة على الطاولة غير الطلب الحالي. */
    otherOrders(table) {
        return this.pos
            .getActiveOrdersOnTable(table.rootTable)
            .filter((order) => order.uuid !== this.props.order.uuid);
    }

    tableState(table) {
        const root = table.rootTable;
        const others = this.otherOrders(table);
        const total = others.reduce((sum, order) => sum + (order.totalDue || 0), 0);
        return {
            current: root.id === this.props.order.table_id?.rootTable?.id,
            busy: others.length > 0,
            amount: total ? this.env.utils.formatCurrency(total) : "",
            joinedTo: root.id !== table.id ? root.table_number : null,
        };
    }

    busyCount(floor) {
        return floor.table_ids.filter((table) => this.otherOrders(table).length).length;
    }

    selectFloor(floor) {
        this.state.floorId = floor.id;
    }

    pick(table) {
        this.props.getPayload(table.rootTable);
        this.props.close();
    }
}

export class HosnyServiceBar extends Component {
    static template = "pos_entry_selector.HosnyServiceBar";
    static props = {};

    setup() {
        this.pos = usePos();
    }

    get order() {
        const order = this.pos.getOrder();
        return order && !order.finalized && !order.isRefund ? order : null;
    }

    get isTakeaway() {
        return this.pos.isTakeawayOrder(this.order);
    }

    get table() {
        return this.order?.table_id?.rootTable || null;
    }

    chooseTakeaway() {
        return this.pos.hosnyChooseTakeaway(this.order);
    }

    chooseTable() {
        return this.pos.hosnyChooseTable(this.order);
    }
}

patch(ProductScreen, {
    components: { ...ProductScreen.components, HosnyServiceBar },
});

patch(PosStore.prototype, {
    async hosnyChooseTakeaway(order = this.getOrder()) {
        if (!order || order.finalized || this.isTakeawayOrder(order)) {
            return;
        }
        if (!order.isEmpty() && order.table_id) {
            const confirmed = await ask(this.dialog, {
                title: "تحويل الطلب إلى سفري",
                body: `سيُفصل الطلب عن الطاولة ${tableTitle(order.table_id)} ويصبح طلب سفري.`,
                confirmLabel: "نعم، سفري",
                cancelLabel: "إلغاء",
            });
            if (!confirmed) {
                return;
            }
        }
        this.setOrderType(order, this.takeawayOrderType);
    },

    async hosnyChooseTable(order = this.getOrder()) {
        if (!order || order.finalized) {
            return;
        }
        const table = await makeAwaitable(this.dialog, HosnyTablePicker, { order });
        if (table) {
            await this.hosnySeatOrder(order, table);
        }
    },

    async hosnySeatOrder(order, table) {
        if (order.table_id?.rootTable?.id === table.id) {
            return;
        }
        const tableOrders = this.getActiveOrdersOnTable(table).filter((o) => o.uuid !== order.uuid);
        if (tableOrders.length && order.isEmpty()) {
            // لا شيء ينتقل: الكاشير يريد طلب الطاولة نفسه
            await this.setTableFromUi(table);
            return;
        }
        if (tableOrders.length) {
            const confirmed = await ask(this.dialog, {
                title: `الطاولة ${tableTitle(table)} عليها طلب مفتوح`,
                body: "ستُضاف أصناف هذا الطلب إلى طلب الطاولة.",
                confirmLabel: "نعم، أضفها للطاولة",
                cancelLabel: "إلغاء",
            });
            if (!confirmed) {
                return;
            }
        }
        this.ui.block();
        try {
            await this.transferOrder(order.uuid, table);
        } finally {
            this.ui.unblock();
        }
        const current = this.getOrder();
        if (current) {
            this.navigate("ProductScreen", { orderUuid: current.uuid });
        }
    },
});
