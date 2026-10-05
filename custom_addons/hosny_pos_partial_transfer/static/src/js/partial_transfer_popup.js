/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const EPSILON = 0.00001;

function getTableLabel(table) {
    return table?.getName?.() || table?.table_number?.toString?.() || table?.name || "";
}

function getFloors(pos) {
    return pos?.config?.floor_ids || pos?.floors || [];
}

function getTables(floor) {
    return floor?.table_ids || floor?.tables || [];
}

export class PartialTransferPopup extends Component {
    static template = "hosny_pos_partial_transfer.PartialTransferPopup";
    static components = { Dialog };
    static props = {
        order: Object,
        title: { type: String, optional: true },
        confirmText: { type: String, optional: true },
        cancelText: { type: String, optional: true },
        confirmKey: { type: Boolean, optional: true },
        getPayload: { type: Function, optional: true },
        close: Function,
    };
    static defaultProps = {
        title: _t("تحويل جزئي بين الطاولات"),
        confirmText: _t("تحويل"),
        cancelText: _t("إلغاء"),
        confirmKey: false,
    };

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");

        const destinationTables = this.availableTables;
        this.state = useState({
            destinationTableId: destinationTables.length ? destinationTables[0].id : null,
            selectedQtyByLineId: this._buildSelectionState(),
            collapsedFloorIds: this._buildCollapsedFloorsState(),
            isSubmitting: false,
        });
    }

    get currentOrder() {
        return this.props.order;
    }
    get sourceTable() {
        return (
            this.currentOrder?.getTable?.() ||
            this.currentOrder?.table_id ||
            this.pos?.selectedTable ||
            this.pos?.table ||
            null
        );
    }

    get sourceTableName() {
        return getTableLabel(this.sourceTable);
    }

    get sourceFloorName() {
        return this.sourceTable?.floor_id?.name || this.sourceTable?.floor?.name || "";
    }

    get availableTables() {
        const sourceTableId = this.sourceTable?.id;
        return getFloors(this.pos)
            .flatMap((floor) => getTables(floor))
            .filter((table) => table.id !== sourceTableId)
            .sort((a, b) => {
                const aFloor = a.floor_id?.name || a.floor?.name || "";
                const bFloor = b.floor_id?.name || b.floor?.name || "";
                if (aFloor === bFloor) {
                    return getTableLabel(a).localeCompare(getTableLabel(b), undefined, { numeric: true });
                }
                return aFloor.localeCompare(bFloor, undefined, { numeric: true });
            });
    }

    get tableSections() {
        return getFloors(this.pos)
            .map((floor) => ({
                id: floor.id,
                name: floor.name,
                isCollapsed: !!this.state.collapsedFloorIds[floor.id],
                tables: getTables(floor)
                    .filter((table) => table.id !== this.sourceTable?.id)
                    .map((table) => ({
                        table,
                        name: getTableLabel(table),
                        isSelected: table.id === this.state.destinationTableId,
                        orderCount: this.pos.getTableOrders(table.id).filter((order) => !order.finalized)
                            .length || table.order_count || 0,
                    })),
            }))
            .filter((section) => section.tables.length);
    }

    get lineEntries() {
        return this.currentOrder.get_orderlines().map((line) => {
            const displayData = {
                ...line.getDisplayData(),
                price: this.env.utils.formatCurrency(line.get_all_prices().priceWithTax),
                unitPrice: this.env.utils.formatCurrency(line.get_unit_price()),
                unit: line.get_unit?.()?.name || "" || "",
            };
            const rootLine = this._getComboRoot(line);
            return {
                id: line.id,
                line,
                displayData,
                availableQty: line.get_quantity(),
                selectedQty: this.state.selectedQtyByLineId[line.id] || 0,
                isComboChild: rootLine.id !== line.id,
                comboRootName: rootLine.get_full_product_name(),
                quantityStep: this._getQuantityStep(line),
                attributesText: this._formatAttributes(displayData.attributes || []),
            };
        });
    }

    get selectedTransfers() {
        return this.currentOrder
            .get_orderlines()
            .map((line) => ({
                line,
                quantity: this.state.selectedQtyByLineId[line.id] || 0,
            }))
            .filter(({ quantity }) => quantity > EPSILON);
    }

    get transferSummary() {
        const lines = this.selectedTransfers;
        const totalLines = lines.length;
        const totalQuantity = lines.reduce((sum, item) => sum + item.quantity, 0);
        const totalAmount = lines.reduce(
            (sum, item) => sum + item.line.get_all_prices(item.quantity).priceWithTax,
            0
        );
        return {
            totalLines,
            totalQuantity: Number(totalQuantity).toFixed(2),
            totalAmount: this.env.utils.formatCurrency(totalAmount),
        };
    }

    _buildSelectionState() {
        const state = {};
        for (const line of this.currentOrder.get_orderlines()) {
            state[line.id] = 0;
        }
        return state;
    }

    _buildCollapsedFloorsState() {
        const state = {};
        for (const floor of getFloors(this.pos)) {
            state[floor.id] = false;
        }
        return state;
    }

    _getComboRoot(line) {
        return line.getAllLinesInCombo?.()?.[0] || line;
    }

    _getLinkedLines(line) {
        return this._getComboRoot(line).getAllLinesInCombo?.() || [line];
    }

    /**
     * ضغطة «+» = قطعة واحدة. في أودو 19 صار unit.rounding دقة القاعدة
     * (0.0001)، فكانت كل ضغطة تنقل 0.0001 والشاشة تعرض «0.00» كأن الزر لا
     * يعمل. الحد الأعلى (المتاح) يقفل الكسور: 0.75 كيلو تُنقل 0.75.
     */
    _getQuantityStep(line) {
        return 1;
    }

    _roundQty(value, step) {
        if (!step) {
            return value;
        }
        return Math.round(value / step) * step;
    }

    _formatAttributes(attributes) {
        return attributes
            .map((attribute) => {
                const values = attribute.valuesForOrderLine.map((value) => value.name).join("، ");
                return `${attribute.name}: ${values}`;
            })
            .join(" • ");
    }

    setDestinationTable(tableId) {
        this.state.destinationTableId = tableId;
    }

    toggleFloorSection(floorId) {
        this.state.collapsedFloorIds[floorId] = !this.state.collapsedFloorIds[floorId];
    }

    getSelectedQty(line) {
        return this.state.selectedQtyByLineId[line.id] || 0;
    }

    updateLineQuantity(line, direction) {
        const targetLine = this._getComboRoot(line);
        const linkedLines = this._getLinkedLines(targetLine);
        const currentQty = this.getSelectedQty(targetLine);
        const step = this._getQuantityStep(targetLine);
        const maxQty = targetLine.get_quantity();

        let nextQty = currentQty + direction * step;
        nextQty = Math.max(0, Math.min(this._roundQty(nextQty, step), maxQty));
        if (Math.abs(maxQty - nextQty) < EPSILON) {
            nextQty = maxQty;
        }

        for (const linkedLine of linkedLines) {
            this.state.selectedQtyByLineId[linkedLine.id] = Math.min(
                nextQty,
                linkedLine.get_quantity()
            );
        }
    }

    setMaxQuantity(line) {
        const targetLine = this._getComboRoot(line);
        for (const linkedLine of this._getLinkedLines(targetLine)) {
            this.state.selectedQtyByLineId[linkedLine.id] = linkedLine.get_quantity();
        }
    }

    clearQuantity(line) {
        const targetLine = this._getComboRoot(line);
        for (const linkedLine of this._getLinkedLines(targetLine)) {
            this.state.selectedQtyByLineId[linkedLine.id] = 0;
        }
    }

    getPayload() {
        return {
            destinationTableId: this.state.destinationTableId,
            transfers: this.selectedTransfers.map(({ line, quantity }) => ({
                lineId: line.id,
                quantity,
            })),
        };
    }

    cancel() {
        this.props.close();
    }

    async confirm() {
        const payload = this.getPayload();

        if (!payload.destinationTableId) {
            await this.dialog.add(AlertDialog, {
                title: _t("اختر الطاولة"),
                body: _t("يرجى تحديد طاولة الوجهة قبل تأكيد التحويل."),
            });
            return;
        }

        if (!payload.transfers.length) {
            await this.dialog.add(AlertDialog, {
                title: _t("لا توجد عناصر محددة"),
                body: _t("يرجى اختيار كمية واحدة على الأقل لتحويلها."),
            });
            return;
        }

        this.state.isSubmitting = true;
        try {
            await this.pos.partialTransferOrderLines(
                this.currentOrder,
                payload.destinationTableId,
                payload.transfers
            );
            this.props.getPayload?.({ confirmed: true, payload });
            this.props.close();
        } catch (error) {
            await this.dialog.add(AlertDialog, {
                title: _t("تعذر إتمام التحويل"),
                body: error.message || _t("تعذر نقل العناصر المحددة إلى طاولة الوجهة."),
            });
        } finally {
            this.state.isSubmitting = false;
        }
    }
}
