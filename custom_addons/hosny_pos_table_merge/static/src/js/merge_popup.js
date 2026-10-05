/** @odoo-module */
import { Dialog } from "@web/core/dialog/dialog";
import { AbstractAwaitablePopup } from "@point_of_sale/app/popup/abstract_awaitable_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUnmount, useState } from "@odoo/owl";

// The sync is a chain of eight round-trips and Odoo's RPC has no client-side
// timeout, so a branch that loses its line mid-call leaves the promise pending
// for ever. Time-box it: the table list is built from local POS data anyway, so
// a refresh that never answers costs freshness, not the whole panel.
const REFRESH_TIMEOUT_MS = 12000;
const AUTO_REFRESH_MS = 15000;

function withTimeout(promise, ms, message) {
    let timer;
    return Promise.race([
        promise,
        new Promise((_resolve, reject) => {
            timer = setTimeout(() => reject(new Error(message)), ms);
        }),
    ]).finally(() => clearTimeout(timer));
}

function getTableLabel(table) {
    return table?.getName?.() || table?.table_number?.toString?.() || table?.name || "";
}

function getFloors(pos) {
    return pos?.config?.floor_ids || pos?.floors || [];
}

export class MergeTablesPopup extends AbstractAwaitablePopup {
    static template = "hosny_pos_table_merge.MergeTablesPopup";
    static components = { Dialog };
    static props = {
        order: Object,
        title: { type: String, optional: true },
        confirmText: { type: String, optional: true },
        cancelText: { type: String, optional: true },
        confirmKey: { type: Boolean, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("دمج الطاولات"),
        confirmText: _t("تأكيد الدمج"),
        cancelText: _t("إلغاء"),
        confirmKey: false,
    };

    setup() {
        super.setup?.();
        this.pos = usePos();
        this.popup = useService("popup");
        this.state = useState({
            selectedTableIds: [],
            collapsedFloorIds: this._buildCollapsedFloorsState(),
            // The list renders from local POS data, so it is never "loading" in
            // the blocking sense — only refreshing on top of what is shown.
            isRefreshing: false,
            hasRefreshedOnce: false,
            isSubmitting: false,
            loadError: null,
            lastRefreshLabel: "",
        });

        onMounted(() => {
            this.refreshTables();
            this._autoRefresh = setInterval(() => {
                // never stack refreshes, and never fight a merge in progress
                if (!this.state.isRefreshing && !this.state.isSubmitting) {
                    this.refreshTables({ silent: true });
                }
            }, AUTO_REFRESH_MS);
        });

        onWillUnmount(() => clearInterval(this._autoRefresh));
    }

    /**
     * Pull fresh order data for the mergeable tables. Failure is not fatal:
     * `getMergeableTables()` reads the POS's own in-memory orders, so the panel
     * keeps showing the last known figures and offers a retry instead of
     * hanging on a spinner.
     */
    async refreshTables({ silent = false } = {}) {
        if (this.state.isRefreshing) {
            return;
        }
        this.state.isRefreshing = true;
        if (!silent) {
            this.state.loadError = null;
        }
        try {
            await withTimeout(
                this.pos.syncMergePreviewTables(this.destinationTable?.id),
                REFRESH_TIMEOUT_MS,
                _t("انتهت مهلة الاتصال بالخادم.")
            );
            this.state.loadError = null;
            this.state.lastRefreshLabel = this._nowLabel();
        } catch (error) {
            this.state.loadError =
                error?.message || _t("تعذر تحديث بيانات الطاولات من الخادم.");
        } finally {
            this.state.isRefreshing = false;
            this.state.hasRefreshedOnce = true;
        }
    }

    _nowLabel() {
        return new Date().toLocaleTimeString("ar-EG", {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    get currentOrder() {
        return this.props.order;
    }

    get destinationTable() {
        return this.currentOrder?.getTable();
    }

    get destinationTableName() {
        return getTableLabel(this.destinationTable);
    }

    get destinationFloorName() {
        return this.destinationTable?.floor_id?.name || this.destinationTable?.floor?.name || "";
    }

    get destinationOrders() {
        if (!this.destinationTable) {
            return [];
        }
        return this.pos.getTableOrders(this.destinationTable.id).filter((order) => !order.finalized);
    }

    get availableTables() {
        return this.destinationTable ? this.pos.getMergeableTables(this.destinationTable.id) : [];
    }

    get tableSections() {
        return getFloors(this.pos)
            .map((floor) => ({
                id: floor.id,
                name: floor.name,
                isCollapsed: !!this.state.collapsedFloorIds[floor.id],
                tables: this.availableTables.filter((table) => table.floorId === floor.id),
            }))
            .filter((section) => section.tables.length);
    }

    get selectedTables() {
        const selectedIds = new Set(this.state.selectedTableIds);
        return this.availableTables.filter((table) => selectedIds.has(table.id));
    }

    get destinationSummary() {
        const activeOrders = this.destinationOrders;
        const totalAmount = activeOrders.reduce((sum, order) => sum + order.get_total_with_tax(), 0);
        const itemsCount = activeOrders.reduce(
            (sum, order) => sum + order.get_orderlines().length,
            0
        );
        const guestsCount = activeOrders.reduce(
            (sum, order) => sum + (order.getCustomerCount?.() || 0),
            0
        );

        return {
            ordersCount: activeOrders.length,
            itemsCount,
            guestsCount,
            totalAmount,
        };
    }

    get mergeSummary() {
        const selectedTables = this.selectedTables;
        const tablesCount = selectedTables.length;
        const ordersCount = selectedTables.reduce((sum, table) => sum + table.ordersCount, 0);
        const itemsCount = selectedTables.reduce((sum, table) => sum + table.itemsCount, 0);
        const guestsCount = selectedTables.reduce((sum, table) => sum + table.guestsCount, 0);
        const totalAmount = selectedTables.reduce((sum, table) => sum + table.totalAmount, 0);

        return {
            tablesCount,
            ordersCount,
            itemsCount,
            guestsCount,
            totalAmount,
            projectedAmount: this.destinationSummary.totalAmount + totalAmount,
        };
    }

    get destinationContextHint() {
        const destinationHasContent =
            this.destinationSummary.ordersCount > 0 && this.destinationSummary.itemsCount > 0;
        if (destinationHasContent) {
            return _t(
                "سيتم الاحتفاظ ببيانات الطاولة الحالية عند اختلاف العميل أو قائمة الأسعار أو الوضع الضريبي."
            );
        }
        return _t("إذا كانت الطاولة الحالية فارغة فسيتم اعتماد بيانات أول طلب منقول تلقائياً.");
    }

    _buildCollapsedFloorsState() {
        const state = {};
        for (const floor of getFloors(this.pos)) {
            state[floor.id] = false;
        }
        return state;
    }

    toggleFloorSection(floorId) {
        this.state.collapsedFloorIds[floorId] = !this.state.collapsedFloorIds[floorId];
    }

    isSelected(tableId) {
        return this.state.selectedTableIds.includes(tableId);
    }

    toggleTable(tableId) {
        if (this.isSelected(tableId)) {
            this.state.selectedTableIds = this.state.selectedTableIds.filter((id) => id !== tableId);
            return;
        }
        this.state.selectedTableIds = [...this.state.selectedTableIds, tableId];
    }

    formatCurrency(value) {
        return this.env.utils.formatCurrency(value || 0);
    }

    async confirm() {
        if (!this.state.selectedTableIds.length) {
            await this.popup.add(ErrorPopup, {
                title: _t("اختر طاولة واحدة على الأقل"),
                body: _t("حدد الطاولات التي تريد دمجها داخل الطاولة الحالية قبل المتابعة."),
            });
            return;
        }

        this.state.isSubmitting = true;
        try {
            await this.pos.mergeSelectedTables(this.currentOrder, this.state.selectedTableIds);
            this.props.getPayload({
                confirmed: true,
                payload: { sourceTableIds: [...this.state.selectedTableIds] },
            });
            this.props.close();
        } catch (error) {
            await this.popup.add(ErrorPopup, {
                title: _t("تعذر إتمام الدمج"),
                body: error?.message || _t("حدث خطأ غير متوقع أثناء دمج الطاولات."),
            });
        } finally {
            this.state.isSubmitting = false;
        }
    }
}
