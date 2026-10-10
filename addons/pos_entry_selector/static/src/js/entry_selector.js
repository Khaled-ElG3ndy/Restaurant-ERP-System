/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosStore } from "@point_of_sale/app/services/pos_store";

console.log("POS Entry Selector JS loaded");

function getOrders(pos) {
    return pos?.getOpenOrders?.() || pos?.orders?.models || pos?.orders || [];
}

function asArray(value) {
    if (!value) {
        return [];
    }
    if (Array.isArray(value)) {
        return Array.from(value);
    }
    if (typeof value.getAll === "function") {
        return value.getAll();
    }
    if (typeof value.values === "function") {
        return Array.from(value.values());
    }
    if (typeof value[Symbol.iterator] === "function") {
        return Array.from(value);
    }
    return Object.values(value);
}

function normalizeName(name) {
    return (name || "")
        .toString()
        .trim()
        .toLowerCase()
        .replace(/[أإآ]/g, "ا")
        .replace(/ة/g, "ه");
}

function getOrderTableId(order) {
    return (
        order?.table?.id ||
        order?.table_id?.id ||
        order?.table_id ||
        null
    );
}

function getOrderFloorId(order) {
    return (
        order?.floor?.id ||
        order?.floor_id?.id ||
        order?.floor_id ||
        null
    );
}

export function isTakeawayFloor(floor) {
    const floorName = normalizeName(floor?.name);
    return (
        /\btakeaway\b/.test(floorName) ||
        floorName.includes("سفري") ||
        floorName.includes("تيك اوي") ||
        floorName.includes("تيكاواي")
    );
}

/**
 * طوابق الجلوس في هذه النقطة — بلا طابق «سفري» — بالتسلسل ثم الأقدم، فيأتي
 * «أرضي» أولاً (ترتيب floor_ids في الإعدادات يضع VIP أولاً).
 */
export function dineInFloors(pos) {
    return pos.config.floor_ids
        .filter((floor) => floor.active !== false && !isTakeawayFloor(floor))
        .sort((a, b) => (a.sequence || 0) - (b.sequence || 0) || a.id - b.id);
}

function getTableLabel(table) {
    return table?.getName?.() || table?.table_number?.toString?.() || table?.name || "";
}

function getTablesById(pos) {
    return pos?.tables_by_id || pos?.models?.["restaurant.table"]?.getAllBy?.("id");
}

function getTableById(pos, tableId) {
    const tablesById = getTablesById(pos);
    if (!tablesById || !tableId) {
        return null;
    }
    return tablesById.get?.(tableId) || tablesById[tableId] || null;
}

function getTableList(pos) {
    const tablesById = getTablesById(pos);
    if (!tablesById) {
        return [];
    }
    return asArray(tablesById);
}

function isEmptyTableOrder(order) {
    if (!order) return false;

    const lines = order.getOrderlines ? order.getOrderlines() : [];
    const hasLines = lines.length > 0;
    const hasTable = !!(order.table || order.table_id);
    const isFinalized = !!order.finalized || !!order.validation_date;

    return hasTable && !hasLines && !isFinalized;
}

/** طلب سفري فُتح وتُرك فارغاً على هذا الجهاز ولم يصل للخادم. */
function isAbandonedTakeawayOrder(pos, order) {
    return (
        !!order &&
        !order.finalized &&
        !order.isSynced &&
        !order.table_id &&
        order.isEmpty() &&
        !order.payment_ids.length &&
        pos.isTakeawayOrder(order)
    );
}

function debugOrdersState(pos, label = "DEBUG") {
    const orders = getOrders(pos) || [];

    console.log(`========== ${label} ==========`);

    const mapped = orders.map((order) => {
        const lines = order.getOrderlines ? order.getOrderlines() : [];
        return {
            uid: order.uid,
            name: order.name,
            table_id: getOrderTableId(order),
            floor_id: getOrderFloorId(order),
            lines_count: lines.length,
            finalized: !!order.finalized,
            validation_date: !!order.validation_date,
            is_empty_table_order: isEmptyTableOrder(order),
        };
    });

    console.table(mapped);

    const tables = getTableList(pos);
    if (tables.length) {
        const tableRows = tables.map((table) => ({
            id: table.id,
            name: getTableLabel(table),
            order_count: table.order_count,
        }));
        console.table(tableRows);
    }

    console.log("selectedTable:", pos?.selectedTable);
    console.log("pos.table:", pos?.table);
    console.log("currentOrder:", pos?.getOrder?.());
    console.log(`========== END ${label} ==========`);
}

function recomputeTableCounts(pos) {
    const tables = getTableList(pos);
    if (!tables.length) return;

    console.log("recomputeTableCounts -> START");

    for (const table of tables) {
        table.order_count = 0;
    }

    const orders = getOrders(pos);
    for (const order of orders) {
        const lines = order.getOrderlines ? order.getOrderlines() : [];
        const tableId = getOrderTableId(order);
        const isFinalized = !!order.finalized || !!order.validation_date;

        console.log("Checking order for count:", {
            uid: order.uid,
            tableId,
            lines: lines.length,
            isFinalized,
        });

        const table = getTableById(pos, tableId);
        if (tableId && lines.length > 0 && !isFinalized && table) {
            table.order_count += 1;
        }
    }

    console.table(
        tables.map((table) => ({
            id: table.id,
            name: getTableLabel(table),
            order_count: table.order_count,
        }))
    );

    console.log("recomputeTableCounts -> END");
}

function cleanupEmptyTableOrders(pos) {
    if (!pos || !pos.orders) return;

    const orders = getOrders(pos);
    if (!orders.length) {
        console.log("cleanupEmptyTableOrders -> no orders found");
        return;
    }

    debugOrdersState(pos, "BEFORE CLEANUP");

    const currentOrder = pos.getOrder ? pos.getOrder() : null;
    const toRemove = orders.filter((order) => isEmptyTableOrder(order));

    console.log(
        "Orders marked for removal:",
        toRemove.map((o) => ({
            uid: o.uid,
            name: o.name,
            table_id: getOrderTableId(o),
        }))
    );

    let removedCurrentOrder = false;

    for (const order of toRemove) {
        console.log("Removing empty table order:", {
            uid: order.uid,
            table_id: getOrderTableId(order),
            name: order.name,
        });

        if (currentOrder && order === currentOrder) {
            removedCurrentOrder = true;
        }

        if (typeof pos.removeOrder === "function") {
            pos.removeOrder(order, false);
        } else if (typeof pos.remove_order === "function") {
            pos.remove_order(order);
        }
    }

    if (removedCurrentOrder && !pos.getOrder?.()) {
        console.log("Current order was removed, creating a new one");
        pos.addNewOrder?.();
    }

    if (!pos.isOrderTransferMode) {
        const current = pos.getOrder?.();
        for (const order of orders.filter((o) => o !== current && isAbandonedTakeawayOrder(pos, o))) {
            pos.removeOrder(order, false);
        }
    }

    debugOrdersState(pos, "AFTER CLEANUP");
}

function getTableStatus(pos, table) {
    const orders = getOrders(pos);

    const relatedOrders = orders.filter((o) => {
        const tableId = getOrderTableId(o);
        const lines = o.getOrderlines ? o.getOrderlines() : [];
        const isFinalized = !!o.finalized || !!o.validation_date;

        return tableId === table.id && lines.length > 0 && !isFinalized;
    });

    console.log("getTableStatus:", {
        table: getTableLabel(table),
        tableId: table.id,
        relatedOrders: relatedOrders.map((o) => ({
            uid: o.uid,
            name: o.name,
            lines: o.getOrderlines ? o.getOrderlines().length : 0,
            table_id: getOrderTableId(o),
        })),
        result: relatedOrders.length ? "occupied" : "free",
    });

    return relatedOrders.length ? "occupied" : "free";
}

patch(PosOrder.prototype, {
    removeOrderline(line) {
        super.removeOrderline(...arguments);

        const lines = this.getOrderlines ? this.getOrderlines() : [];
        const hasTable = !!(this.table || this.table_id);
        const isFinalized = !!this.finalized || !!this.validation_date;

        if (!lines.length && hasTable && !isFinalized) {
            const pos = this.pos;

            setTimeout(() => {
                const freshLines = this.getOrderlines ? this.getOrderlines() : [];
                if (freshLines.length) return;

                console.log("Auto removing empty table order after last line deleted:", this.uid);

                if (typeof pos?.removeOrder === "function") {
                    pos.removeOrder(this, false);
                } else if (typeof pos?.remove_order === "function") {
                    pos.remove_order(this);
                }

                recomputeTableCounts(pos);
            }, 0);
        }
    },

    async setTable(table) {
        const pos = this.pos;
        const oldTableId = getOrderTableId(this);

        console.log("setTable -> BEFORE super", {
            order_uid: this.uid,
            oldTableId,
            targetTable: table?.id || table || null,
            lines: this.getOrderlines ? this.getOrderlines().length : 0,
        });

        debugOrdersState(pos, "BEFORE TRANSFER");

        if (super.setTable) {
            await super.setTable(...arguments);
        }

        this.table = table || null;
        this.table_id = table || null;

        const newTableId = getOrderTableId(this);

        console.log("setTable -> AFTER super", {
            order_uid: this.uid,
            oldTableId,
            newTableId,
            lines: this.getOrderlines ? this.getOrderlines().length : 0,
        });

        debugOrdersState(pos, "AFTER TRANSFER BEFORE CLEANUP");

        setTimeout(() => {
            console.log("setTable -> timeout 0 start");

            cleanupEmptyTableOrders(pos);
            recomputeTableCounts(pos);

            const floorScreen = pos.mainScreen?.component;
            console.log("floorScreen in timeout 0:", floorScreen);
            floorScreen?.render?.();

            debugOrdersState(pos, "AFTER TRANSFER TIMEOUT 0");

            this.trigger?.("change");
        }, 0);

        setTimeout(() => {
            console.log("setTable -> timeout 100 start");

            cleanupEmptyTableOrders(pos);
            recomputeTableCounts(pos);

            const floorScreen = pos.mainScreen?.component;
            console.log("floorScreen in timeout 100:", floorScreen);
            floorScreen?.render?.();

            debugOrdersState(pos, "AFTER TRANSFER TIMEOUT 100");

            this.trigger?.("change");
        }, 100);
    },
});

/**
 * هذه الواجهة تخفي أزرار أودو للطلب بلا طاولة («Set Table» وتسمية الطلب)، فكل
 * طلب سفري جديد (ومنه «فاتورة جديدة» من سفري) يُسمّى من البداية.
 */
patch(PosStore.prototype, {
    createNewOrder() {
        const order = super.createNewOrder(...arguments);
        this.nameTakeawayOrder(order);
        return order;
    },
});

patch(FloorScreen.prototype, {
    getFloorTone() {
        const floor = this.activeFloor || this.pos?.currentFloor;
        const floorName = (floor?.name || "").toString().trim().toLowerCase();
        if (!floorName) return "";

        // Support English and Arabic naming patterns.
        const isGround =
            /\bground\b/.test(floorName) ||
            floorName.includes("أرض") ||
            floorName.includes("ارضي") ||
            floorName.includes("الدور الارضي") ||
            floorName.includes("الدور الأرضي");
        const isUpper =
            /\bupper\b/.test(floorName) ||
            floorName.includes("علو") ||
            floorName.includes("علوي") ||
            floorName.includes("الدور العلوي");
        const isTakeaway =
            /\btakeaway\b/.test(floorName) ||
            floorName.includes("سفري") ||
            floorName.includes("تيك اوي") ||
            floorName.includes("تيك_اواي") ||
            floorName.includes("تيكأواي");
        const isVip =
            /\bvip\b/.test(floorName) ||
            floorName.includes("vip") ||
            floorName.includes("في اي بي") ||
            floorName.includes("في آي بي");

        if (isGround) return "ground";
        if (isUpper) return "upper";
        if (isTakeaway) return "takeaway";
        if (isVip) return "vip";
        return "";
    },

    refreshFloorState() {
        cleanupEmptyTableOrders(this.pos);
        recomputeTableCounts(this.pos);

        this.render();

        setTimeout(() => {
            cleanupEmptyTableOrders(this.pos);
            recomputeTableCounts(this.pos);

            this.render();
        }, 50);
    },

    /**
     * السفري لم يعد يجلس على طاولات، فطابق «سفري» لا يظهر في أزرار الطوابق —
     * وإلا اختار الكاشير «طاولة سفري» لطلب محلي. يظهر فقط لو بقي عليه طلب
     * مفتوح (من نقطة بيع لم يُعَد تحميلها بعد التحديث) حتى لا يضيع.
     */
    /**
     * طابق «سفري» يظهر متى كانت عليه طاولات (2026-10-07): «سفري 1…15» لطلبات
     * الهاتف تُتابَع حتى يصل العميل. السفري المباشر يبقى بلا طاولة.
     */
    get hosnyFloorTabs() {
        return this.pos.config.floor_ids.filter(
            (floor) =>
                floor.active &&
                (!isTakeawayFloor(floor) || floor.table_ids.some((table) => table.active !== false))
        );
    },

    setup() {
        super.setup(...arguments);

        const tabs = this.hosnyFloorTabs;
        if (tabs.length && !tabs.some((floor) => floor.id === this.state.selectedFloorId)) {
            this.pos.currentFloor = tabs[0];
            this.state.selectedFloorId = tabs[0].id;
        }

        console.log("FloorScreen patched successfully");

        Promise.resolve().then(() => this.refreshFloorState());
    },

    async onMounted() {
        await super.onMounted?.(...arguments);
        this.refreshFloorState();
    },

    getStatusClass(table) {
        const status = getTableStatus(this.pos, table);

        if (status === "occupied") return "table-occupied";
        if (status === "reserved") return "table-reserved";

        return "table-free";
    },
});
