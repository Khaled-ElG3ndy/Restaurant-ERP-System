/** @odoo-module **/

import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

const PAID_ORDER_STATES = new Set(["paid", "done", "invoiced"]);
const ORDER_EPSILON = 0.00001;

export class HosnyPaymentOrdersScreen extends Component {
    static template = "hosny_pos_controls.PaymentOrdersScreen";

    setup() {
        this.pos = usePos();
        this.state = useState({
            searchTerm: "",
            filter: "all",
            sortBy: "recent",
            refreshing: false,
            lastRefreshAt: Date.now(),
        });
    }

    get allPendingOrders() {
        const pendingOrders = new Map();
        const liveOrders = this.pos?.get_order_list?.() || this.pos?.orders || [];

        for (const order of liveOrders) {
            this.addPendingOrderEntry(pendingOrders, this.buildLiveOrderEntry(order));
        }

        const storedOrders = this.pos?.db?.get_unpaid_orders?.() || [];
        for (const json of storedOrders) {
            this.addPendingOrderEntry(pendingOrders, this.buildStoredOrderEntry(json));
        }

        return [...pendingOrders.values()].sort((left, right) => {
            if (right.sequenceNumber !== left.sequenceNumber) {
                return right.sequenceNumber - left.sequenceNumber;
            }
            if (right.dateOrderValue !== left.dateOrderValue) {
                return right.dateOrderValue - left.dateOrderValue;
            }
            return (left.name || "").localeCompare(right.name || "");
        });
    }

    get pendingOrders() {
        return this.sortOrders(
            this.allPendingOrders.filter(
                (order) => this.matchesSearch(order) && this.matchesFilter(order)
            )
        );
    }

    get quickFilters() {
        const orders = this.allPendingOrders;
        return [
            {
                key: "all",
                label: _t("الكل"),
                count: orders.length,
            },
            {
                key: "unpaid",
                label: _t("غير مسدد"),
                count: orders.filter((order) => order.statusKey === "unpaid").length,
            },
            {
                key: "partial",
                label: _t("مدفوع جزئياً"),
                count: orders.filter((order) => order.statusKey === "partial").length,
            },
            {
                key: "table",
                label: _t("طاولات"),
                count: orders.filter((order) => order.hasTable).length,
            },
            {
                key: "customer",
                label: _t("عملاء"),
                count: orders.filter((order) => order.hasCustomer).length,
            },
        ];
    }

    get summaryCards() {
        const orders = this.allPendingOrders;
        const totalDue = orders.reduce((sum, order) => sum + (order.dueAmount || 0), 0);
        return [
            {
                key: "orders",
                label: _t("طلبات مفتوحة"),
                value: orders.length,
            },
            {
                key: "due",
                label: _t("إجمالي المتبقي"),
                value: this.formatCurrency(totalDue),
            },
        ];
    }

    get lastRefreshLabel() {
        if (!this.state.lastRefreshAt) {
            return "";
        }
        return this.formatDateTime(this.state.lastRefreshAt);
    }

    formatCurrency(amount) {
        const value = Number(amount || 0).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });

        return `${value} SR`;
    }

    formatDateTime(dateValue) {
        if (!dateValue) {
            return "";
        }
        try {
            return new Intl.DateTimeFormat("ar-SA-u-ca-gregory", {
                year: "numeric",
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
            }).format(new Date(dateValue));
        } catch {
            return "";
        }
    }

    addPendingOrderEntry(entries, entry) {
        if (!entry) {
            return;
        }
        const existingEntry = entries.get(entry.key);
        if (!existingEntry) {
            entries.set(entry.key, entry);
            return;
        }
        entries.set(entry.key, {
            ...existingEntry,
            ...entry,
            order: entry.order || existingEntry.order,
            json: entry.json || existingEntry.json,
        });
    }

    buildLiveOrderEntry(order) {
        if (!order || this.isLiveOrderPaidOrFinalized(order) || this.isLiveOrderEmpty(order)) {
            return null;
        }
        const total = order.get_total_with_tax?.() || 0;
        const paidAmount = order.get_total_paid?.() || 0;
        const rawDueAmount = order.get_due?.();
        const dueAmount = Math.max(0, rawDueAmount ?? total);
        const statusKey = paidAmount > ORDER_EPSILON ? "partial" : "unpaid";
        const displayName = this.getLiveOrderDisplayName(order);
        const posReference = this.getUsableReference(order.pos_reference);
        return {
            key: this.getOrderKey(order),
            uuid: order.uuid || null,
            uid: order.uid || null,
            serverId: order.server_id || order.id || null,
            name: displayName,
            posReference,
            total,
            paidAmount,
            dueAmount,
            lineCount: order.get_orderlines?.().length || 0,
            tableName: order.getTable?.()?.name || "",
            partnerName: order.get_partner?.()?.name || "",
            sequenceNumber: this.getSequenceNumber(order.sequence_number),
            dateOrderValue: this.normalizeDateValue(order.date_order),
            statusKey,
            statusLabel: this.getStatusLabel(statusKey),
            statusClass: this.getStatusClass(statusKey),
            hasTable: !!order.getTable?.()?.name,
            hasCustomer: !!order.get_partner?.()?.name,
            dateLabel: this.formatDateTime(this.normalizeDateValue(order.date_order)),
            searchableText: this.buildSearchableText({
                name: displayName,
                posReference,
                tableName: order.getTable?.()?.name || "",
                partnerName: order.get_partner?.()?.name || "",
            }),
            order,
        };
    }

    buildStoredOrderEntry(json) {
        if (!json || this.isStoredOrderPaidOrFinalized(json) || this.isStoredOrderEmpty(json)) {
            return null;
        }
        const total = Number(json.amount_total || 0);
        const paidAmount = Number(json.amount_paid || 0);
        const dueAmount = Math.max(0, total - paidAmount);
        const statusKey = paidAmount > ORDER_EPSILON ? "partial" : "unpaid";
        const tableName = this.pos?.tables_by_id?.[json.table_id]?.name || json.table || "";
        const partnerName = this.pos?.db?.get_partner_by_id?.(json.partner_id)?.name || "";
        const dateOrderValue = this.parseDateValue(json.date_order);
        const displayName = this.getStoredOrderDisplayName(json);
        const posReference = this.getUsableReference(json.pos_reference);
        return {
            key: this.getOrderKey(json),
            uuid: json.uuid || null,
            uid: json.uid || null,
            serverId: json.server_id || json.id || null,
            name: displayName,
            posReference,
            total,
            paidAmount,
            dueAmount,
            lineCount: json.lines?.length || 0,
            tableName,
            partnerName,
            sequenceNumber: this.getSequenceNumber(json.sequence_number),
            dateOrderValue,
            statusKey,
            statusLabel: this.getStatusLabel(statusKey),
            statusClass: this.getStatusClass(statusKey),
            hasTable: !!tableName,
            hasCustomer: !!partnerName,
            dateLabel: this.formatDateTime(dateOrderValue),
            searchableText: this.buildSearchableText({
                name: displayName,
                posReference,
                tableName,
                partnerName,
            }),
            json,
        };
    }

    getOrderKey(orderLike) {
        if (orderLike?.server_id) {
            return `server-${orderLike.server_id}`;
        }
        if (orderLike?.id) {
            return `id-${orderLike.id}`;
        }
        if (orderLike?.uuid) {
            return `uuid-${orderLike.uuid}`;
        }
        if (orderLike?.uid) {
            return `uid-${orderLike.uid}`;
        }
        return `fallback-${orderLike?.name || "order"}-${orderLike?.sequence_number || 0}-${orderLike?.date_order || "0"}`;
    }

    getLiveOrderDisplayName(order) {
        return (
            this.getUsableReference(order.getName?.()) ||
            this.getUsableReference(order.get_name?.()) ||
            this.getUsableReference(order.tracking_number) ||
            this.getUsableReference(order.pos_reference) ||
            this.getUsableReference(order.sequence_number) ||
            this.getUsableReference(order.name) ||
            this.getUsableReference(order.uid) ||
            _t("Unnamed order")
        );
    }

    getStoredOrderDisplayName(json) {
        return (
            this.getUsableReference(json.floating_order_name) ||
            this.getUsableReference(json.tracking_number) ||
            this.getUsableReference(json.pos_reference) ||
            this.getUsableReference(json.sequence_number) ||
            this.getUsableReference(json.name) ||
            this.getUsableReference(json.uid) ||
            _t("Unnamed order")
        );
    }

    getUsableReference(value) {
        const reference = `${value ?? ""}`.trim();
        return reference && reference !== "/" ? reference : "";
    }

    getSequenceNumber(value) {
        const sequenceNumber = Number.parseInt(value, 10);
        return Number.isFinite(sequenceNumber) ? sequenceNumber : 0;
    }

    parseDateValue(dateOrder) {
        if (!dateOrder) {
            return 0;
        }
        const normalizedDate = typeof dateOrder === "string" ? dateOrder.replace(" ", "T") : dateOrder;
        const dateValue = Date.parse(normalizedDate);
        return Number.isFinite(dateValue) ? dateValue : 0;
    }

    normalizeDateValue(dateOrder) {
        if (!dateOrder) {
            return 0;
        }
        if (typeof dateOrder?.toMillis === "function") {
            return dateOrder.toMillis();
        }
        if (dateOrder instanceof Date) {
            return dateOrder.getTime();
        }
        return this.parseDateValue(dateOrder);
    }

    buildSearchableText(orderDetails) {
        return [
            orderDetails.name,
            orderDetails.posReference,
            orderDetails.tableName,
            orderDetails.partnerName,
        ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
    }

    getStatusLabel(statusKey) {
        if (statusKey === "partial") {
            return _t("مدفوع جزئياً");
        }
        return _t("غير مسدد");
    }

    getStatusClass(statusKey) {
        return statusKey === "partial" ? "is-partial" : "is-unpaid";
    }

    isLiveOrderPaidOrFinalized(order) {
        const isPaid = typeof order.is_paid === "function" ? order.is_paid() : false;
        return isPaid || !!order.finalized || !!order.validation_date;
    }

    isStoredOrderPaidOrFinalized(json) {
        const state = json.state || "";
        return (
            PAID_ORDER_STATES.has(state) ||
            Number(json.amount_total || 0) - Number(json.amount_paid || 0) <= ORDER_EPSILON
        );
    }

    isLiveOrderEmpty(order) {
        const lineCount = order.get_orderlines?.().length || 0;
        const paymentLineCount = order.paymentlines?.length || 0;
        return lineCount === 0 && paymentLineCount === 0;
    }

    isStoredOrderEmpty(json) {
        return (json.lines?.length || 0) === 0 && (json.statement_ids?.length || 0) === 0;
    }

    matchesSearch(order) {
        const term = (this.state.searchTerm || "").trim().toLowerCase();
        if (!term) {
            return true;
        }
        return (order.searchableText || "").includes(term);
    }

    matchesFilter(order) {
        switch (this.state.filter) {
            case "unpaid":
                return order.statusKey === "unpaid";
            case "partial":
                return order.statusKey === "partial";
            case "table":
                return order.hasTable;
            case "customer":
                return order.hasCustomer;
            default:
                return true;
        }
    }

    sortOrders(orders) {
        const sortedOrders = [...orders];
        switch (this.state.sortBy) {
            case "due_desc":
                sortedOrders.sort((left, right) => {
                    if (right.dueAmount !== left.dueAmount) {
                        return right.dueAmount - left.dueAmount;
                    }
                    return right.dateOrderValue - left.dateOrderValue;
                });
                break;
            case "amount_desc":
                sortedOrders.sort((left, right) => {
                    if (right.total !== left.total) {
                        return right.total - left.total;
                    }
                    return right.dateOrderValue - left.dateOrderValue;
                });
                break;
            case "name":
                sortedOrders.sort((left, right) => (left.name || "").localeCompare(right.name || ""));
                break;
            default:
                sortedOrders.sort((left, right) => {
                    if (right.sequenceNumber !== left.sequenceNumber) {
                        return right.sequenceNumber - left.sequenceNumber;
                    }
                    if (right.dateOrderValue !== left.dateOrderValue) {
                        return right.dateOrderValue - left.dateOrderValue;
                    }
                    return (left.name || "").localeCompare(right.name || "");
                });
                break;
        }
        return sortedOrders;
    }

    setFilter(filterKey) {
        this.state.filter = filterKey;
    }

    clearSearch() {
        this.state.searchTerm = "";
    }

    async refreshOrders() {
        const syncOrders = this.pos?._syncAllOrdersFromServer || this.pos?.syncAllOrders;
        if (this.state.refreshing || typeof syncOrders !== "function") {
            this.state.lastRefreshAt = Date.now();
            return;
        }
        this.state.refreshing = true;
        try {
            await syncOrders.call(this.pos);
            this.state.lastRefreshAt = Date.now();
        } catch (error) {
            console.warn("Failed to refresh unpaid POS orders.", error);
            this.pos.notification?.add(_t("تعذر تحديث قائمة الفواتير حالياً."), {
                type: "warning",
            });
        } finally {
            this.state.refreshing = false;
        }
    }

    resolveOrder(entry) {
        if (entry?.order) {
            return entry.order;
        }
        const existingOrder = this.findOrder(entry);
        if (existingOrder) {
            return existingOrder;
        }
        if (!entry?.json || typeof this.pos?.createReactiveOrder !== "function") {
            return null;
        }
        try {
            const restoredOrder = this.pos.createReactiveOrder(entry.json);
            this.pos.orders.add(restoredOrder);
            return restoredOrder;
        } catch (error) {
            console.error("Failed to restore unpaid POS order for payment.", entry?.json, error);
            this.pos.notification?.add(_t("تعذر تحميل الطلب المحدد للدفع."), {
                type: "danger",
            });
            return null;
        }
    }

    findOrder(entry) {
        const orders = this.pos?.get_order_list?.() || this.pos?.orders || [];
        return (
            orders.find(
                (order) =>
                    (entry?.serverId && order.server_id === entry.serverId) ||
                    (entry?.serverId && order.id === entry.serverId) ||
                    (entry?.uuid && order.uuid === entry.uuid) ||
                    (entry?.uid && order.uid === entry.uid)
            ) || null
        );
    }

    payOrder(entry) {
        const order = this.resolveOrder(entry);
        if (!order) {
            return;
        }
        if (typeof this.pos.setOrder === "function") {
            this.pos.setOrder(order);
        } else if (typeof this.pos.set_order === "function") {
            this.pos.set_order(order);
        } else {
            this.pos.selectedOrderUuid = order.uuid;
        }
        if (typeof order.set_screen_data === "function") {
            order.set_screen_data({ name: "PaymentScreen" });
        }
        this.pos.navigate("PaymentScreen", { orderUuid: order.uuid });
    }

    back() {
        const order =
            this.pos.getOrder?.() ||
            this.pos.get_order?.() ||
            this.pos.openOrder ||
            this.pos.getEmptyOrder?.() ||
            this.pos.addNewOrder?.() ||
            this.pos.add_new_order?.();
        if (!order?.uuid) {
            this.pos.navigateToFirstPage?.();
            return;
        }
        if (typeof this.pos.setOrder === "function") {
            this.pos.setOrder(order);
        } else if (typeof this.pos.set_order === "function") {
            this.pos.set_order(order);
        }
        this.pos.mobile_pane = "right";
        this.pos.navigate("ProductScreen", { orderUuid: order.uuid });
    }
}

registry.category("pos_pages").add("HosnyPaymentOrdersScreen", {
    name: "HosnyPaymentOrdersScreen",
    component: HosnyPaymentOrdersScreen,
    route: `/pos/ui/${odoo.pos_config_id}/payment-orders`,
});
