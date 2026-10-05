/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ConnectionLostError } from "@web/core/network/rpc";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { Orderline, Packlotline } from "@point_of_sale/app/store/models";
import { ProductCustomAttribute } from "@point_of_sale/app/store/models/product_custom_attribute";

const EPSILON = 0.00001;

function getTableLabel(table) {
    return table?.getName?.() || table?.table_number?.toString?.() || table?.name || "";
}

function getAllTables(pos) {
    const modelTables = pos?.models?.["restaurant.table"]?.getAll?.();
    if (modelTables?.length) {
        return modelTables;
    }
    const floors = pos?.config?.floor_ids || pos?.floors || [];
    return floors.flatMap((floor) => floor?.table_ids || floor?.tables || []);
}

patch(PosStore.prototype, {
    getMergeableTables(destinationTableId) {
        return getAllTables(this)
            .filter((table) => table.id !== destinationTableId)
            .map((table) => this._buildMergeTableSummary(table))
            .filter((table) => table.ordersCount > 0)
            .sort((a, b) => {
                if (a.floorName === b.floorName) {
                    return a.name.localeCompare(b.name, undefined, { numeric: true });
                }
                return a.floorName.localeCompare(b.floorName, undefined, { numeric: true });
            });
    },

    async syncMergePreviewTables(destinationTableId) {
        const tables = this.getMergeableTables(destinationTableId);
        if (!tables.length) {
            return tables;
        }

        const tableIds = tables.map((table) => table.id);
        await this._syncMergeTablesFromServer(tableIds);
        return this.getMergeableTables(destinationTableId);
    },

    async mergeSelectedTables(destinationOrder, sourceTableIds) {
        const destinationTable = destinationOrder?.getTable() || this.table;
        if (!destinationOrder || !destinationTable) {
            throw new Error(_t("لا توجد طاولة حالية صالحة لإتمام الدمج."));
        }

        const distinctTableIds = [...new Set(sourceTableIds || [])].filter(
            (tableId) => tableId && tableId !== destinationTable.id
        );
        if (!distinctTableIds.length) {
            throw new Error(_t("يرجى اختيار طاولة واحدة على الأقل للدمج."));
        }

        await this._syncMergeTablesFromServer(distinctTableIds);

        const sourceOrders = distinctTableIds.flatMap((tableId) =>
            this.getTableOrders(tableId).filter((order) => !order.finalized)
        );
        if (!sourceOrders.length) {
            throw new Error(_t("الطاولات المحددة لم تعد تحتوي على طلبات قابلة للدمج."));
        }

        const activeDestinationOrder =
            (!destinationOrder.finalized && destinationOrder.tableId === destinationTable.id
                ? destinationOrder
                : null) ||
            this.getTableOrders(destinationTable.id).find((order) => !order.finalized) ||
            this._createMergeDestinationOrder(destinationTable, sourceOrders[0]);

        const destinationWasEmpty = !activeDestinationOrder.get_orderlines().length;
        if (destinationWasEmpty) {
            this._seedMergeDestinationOrder(activeDestinationOrder, sourceOrders[0]);
        }

        const destinationBaseGuests = destinationWasEmpty
            ? 0
            : activeDestinationOrder.getCustomerCount?.() || 0;
        let mergedGuests = destinationBaseGuests;

        for (const sourceOrder of sourceOrders) {
            const createdLinesMap = new Map();
            const transfers = sourceOrder
                .get_orderlines()
                .map((line) => ({
                    line,
                    quantity: Math.abs(line.get_quantity()),
                }))
                .filter(({ quantity }) => quantity > EPSILON);

            for (const transfer of transfers) {
                const newLine = this._cloneLineForTableMerge(
                    transfer.line,
                    activeDestinationOrder,
                    transfer.quantity
                );
                const insertedLine = this._mergeOrAddMergedLine(activeDestinationOrder, newLine);
                createdLinesMap.set(transfer.line, insertedLine);
            }

            for (const transfer of transfers) {
                const sourceLine = transfer.line;
                const destinationLine = createdLinesMap.get(sourceLine);
                if (!destinationLine) {
                    continue;
                }

                destinationLine.comboLine = sourceLine.comboLine;
                if (!sourceLine.comboParent) {
                    destinationLine.comboLines = destinationLine.comboLines || [];
                }
                if (sourceLine.comboParent) {
                    const newParent = createdLinesMap.get(sourceLine.comboParent);
                    if (newParent) {
                        destinationLine.comboParent = newParent;
                        newParent.comboLines = newParent.comboLines || [];
                        if (!newParent.comboLines.includes(destinationLine)) {
                            newParent.comboLines.push(destinationLine);
                        }
                    }
                } else if (sourceLine.comboLines?.length) {
                    destinationLine.comboLines = sourceLine.comboLines
                        .map((childLine) => createdLinesMap.get(childLine))
                        .filter(Boolean);
                }
            }

            mergedGuests += sourceOrder.getCustomerCount?.() || 0;
            this._removeMergedSourceOrder(sourceOrder, transfers);
        }

        activeDestinationOrder.setCustomerCount(Math.max(mergedGuests, 1));

        if (this.orderPreparationCategories?.size) {
            activeDestinationOrder.updateLastOrderChange();
        }

        activeDestinationOrder.setBooked(true);
        activeDestinationOrder.save_to_db();
        this.ordersToUpdateSet.add(activeDestinationOrder);
        this.set_order(activeDestinationOrder);

        distinctTableIds.forEach((tableId) => this._recomputeRestaurantTableState(tableId));
        this._recomputeRestaurantTableState(destinationTable.id);

        try {
            await this.sendDraftToServer();
        } catch (error) {
            if (!(error instanceof ConnectionLostError)) {
                throw error;
            }
            Promise.reject(error);
        }

        return activeDestinationOrder;
    },

    async _syncMergeTablesFromServer(tableIds) {
        const distinctTableIds = [...new Set(tableIds || [])].filter(Boolean);
        if (!distinctTableIds.length) {
            return;
        }

        await this.sendDraftToServer();
        await this._removeOrdersFromServer();

        const ordersJsons = await this._getTableOrdersFromServer(distinctTableIds);
        await this._loadMissingProducts(ordersJsons);
        await this._loadMissingPartners(ordersJsons);
        await this._addPricelists(ordersJsons);
        await this._addFiscalPositions(ordersJsons);

        const ordersToReplace = this.get_order_list().filter(
            (order) => distinctTableIds.includes(order.tableId) && !order.finalized
        );
        this._replaceOrders(ordersToReplace, ordersJsons);

        distinctTableIds.forEach((tableId) => this._recomputeRestaurantTableState(tableId));
    },

    _buildMergeTableSummary(table) {
        const activeOrders = this.getTableOrders(table.id).filter((order) => !order.finalized);
        const itemsCount = activeOrders.reduce(
            (sum, order) => sum + order.get_orderlines().length,
            0
        );
        const guestsCount = activeOrders.reduce(
            (sum, order) => sum + (order.getCustomerCount?.() || 0),
            0
        );
        const totalAmount = activeOrders.reduce((sum, order) => sum + order.get_total_with_tax(), 0);

        return {
            id: table.id,
            name: getTableLabel(table),
            floorId: table.floor_id?.id || table.floor?.id,
            floorName: table.floor_id?.name || table.floor?.name || "",
            seats: table.seats || 0,
            ordersCount: activeOrders.length || table.order_count || 0,
            itemsCount,
            guestsCount,
            totalAmount,
        };
    },

    _createMergeDestinationOrder(destinationTable, sourceOrder) {
        const destinationOrder = this.createReactiveOrder();
        destinationOrder.tableId = destinationTable.id;
        destinationOrder.setBooked(true);
        destinationOrder.set_screen_data({ name: "ProductScreen" });
        if (sourceOrder) {
            this._seedMergeDestinationOrder(destinationOrder, sourceOrder);
        }
        this.orders.add(destinationOrder);
        return destinationOrder;
    },

    _seedMergeDestinationOrder(destinationOrder, sourceOrder) {
        if (!sourceOrder) {
            return;
        }
        if (!destinationOrder.get_partner() && sourceOrder.get_partner()) {
            destinationOrder.set_partner(sourceOrder.get_partner());
        }
        const sourcePricelist = sourceOrder.pricelist || sourceOrder.pricelist_id;
        if (!destinationOrder.pricelist && !destinationOrder.pricelist_id && sourcePricelist) {
            destinationOrder.set_pricelist(sourcePricelist);
        }
        const sourceFiscalPosition = sourceOrder.fiscal_position || sourceOrder.fiscal_position_id;
        if (
            !destinationOrder.fiscal_position &&
            !destinationOrder.fiscal_position_id &&
            sourceFiscalPosition
        ) {
            destinationOrder.set_fiscal_position(sourceFiscalPosition);
        }
        destinationOrder.to_invoice = destinationOrder.to_invoice || sourceOrder.to_invoice;
        destinationOrder.shippingDate =
            destinationOrder.shippingDate || sourceOrder.shippingDate || sourceOrder.shipping_date;
    },

    _cloneCustomAttributesForMerge(line) {
        return (line.custom_attribute_value_ids || []).map(
            (attribute) =>
                new ProductCustomAttribute({
                    id: attribute.id,
                    name: attribute.name,
                    custom_value: attribute.custom_value,
                    custom_product_template_attribute_value_id:
                        attribute.custom_product_template_attribute_value_id,
                })
        );
    },

    _extractPackLotNamesForMerge(sourceLine, quantity) {
        const lots = sourceLine.get_lot_lines() ? [...sourceLine.get_lot_lines()] : [];
        if (!lots.length) {
            return [];
        }

        const lineQty = Math.abs(sourceLine.get_quantity());
        const moveAllLots = Math.abs(lineQty - quantity) < EPSILON;
        if (moveAllLots || !Number.isInteger(quantity) || lots.length < quantity) {
            return lots.map((lot) => lot.get_lot_name());
        }

        return lots.slice(0, Math.max(0, Math.trunc(quantity))).map((lot) => lot.get_lot_name());
    },

    _applyPackLotsForMerge(destinationLine, lotNames) {
        if (!destinationLine.has_product_lot || !lotNames.length) {
            return;
        }

        for (const lotName of lotNames) {
            const lotLine = new Packlotline(
                { env: this.env },
                {
                    order_line: destinationLine,
                }
            );
            lotLine.set_lot_name(lotName);
            destinationLine.pack_lot_lines.add(lotLine);
        }
    },

    _cloneLineForTableMerge(sourceLine, destinationOrder, quantity) {
        if (this.models?.["pos.order.line"]?.create && sourceLine.raw) {
            const data = { ...sourceLine.raw };
            delete data.id;
            delete data.uuid;
            delete data.combo_line_ids;
            delete data.combo_parent_id;
            delete data.pack_lot_ids;
            delete data.course_id;
            const destinationLine = this.models["pos.order.line"].create(
                {
                    ...data,
                    order_id: destinationOrder.id,
                    qty: quantity,
                },
                false,
                true
            );
            destinationLine.setQuantity(quantity, true);
            destinationLine.setUnitPrice(sourceLine.get_unit_price());
            destinationLine.setDiscount(sourceLine.get_discount());
            destinationLine.setCustomerNote(sourceLine.get_customer_note());
            destinationLine.setNote(sourceLine.getNote());
            destinationLine.setFullProductName?.();
            this._applyPackLotsForMerge(
                destinationLine,
                this._extractPackLotNamesForMerge(sourceLine, quantity)
            );
            return destinationLine;
        }

        const destinationLine = new Orderline(
            { env: this.env },
            {
                pos: this,
                order: destinationOrder,
                product: sourceLine.get_product(),
                price: sourceLine.get_unit_price(),
                quantity,
                price_type: sourceLine.price_type,
                tax_ids: sourceLine.tax_ids,
            }
        );

        destinationLine.set_quantity(quantity, "do not recompute unit price");
        destinationLine.set_unit_price(sourceLine.get_unit_price());
        destinationLine.set_discount(sourceLine.get_discount());
        destinationLine.set_price_extra(sourceLine.get_price_extra());
        destinationLine.set_customer_note(sourceLine.get_customer_note());
        destinationLine.setNote(sourceLine.getNote());
        destinationLine.tax_ids = sourceLine.tax_ids ? [...sourceLine.tax_ids] : sourceLine.tax_ids;
        destinationLine.attribute_value_ids = sourceLine.attribute_value_ids
            ? [...sourceLine.attribute_value_ids]
            : [];
        destinationLine.custom_attribute_value_ids =
            this._cloneCustomAttributesForMerge(sourceLine);
        destinationLine.full_product_name = sourceLine.full_product_name;
        destinationLine.price_type = sourceLine.price_type;
        destinationLine.skipChange = sourceLine.skipChange;
        destinationLine.refunded_orderline_id = sourceLine.refunded_orderline_id;
        destinationLine.refunded_qty = sourceLine.refunded_qty;
        destinationLine.saved_quantity = quantity;
        destinationLine.set_full_product_name();
        this._applyPackLotsForMerge(
            destinationLine,
            this._extractPackLotNamesForMerge(sourceLine, quantity)
        );

        return destinationLine;
    },

    _mergeOrAddMergedLine(destinationOrder, candidateLine) {
        const existingLine = destinationOrder.get_orderlines().find((line) =>
            line.can_be_merged_with(candidateLine)
        );
        if (existingLine) {
            existingLine.merge(candidateLine);
            candidateLine.delete?.();
            return existingLine;
        }
        if (!destinationOrder.get_orderlines().includes(candidateLine)) {
            destinationOrder.add_orderline(candidateLine);
        }
        return candidateLine;
    },

    _removeMergedSourceOrder(sourceOrder, transfers) {
        if (!sourceOrder || !transfers.length) {
            return;
        }

        for (const transfer of transfers) {
            transfer.line.set_quantity(0, "do not recompute unit price");
        }

        const removedComboRoots = new Set();
        for (const transfer of transfers) {
            const line = transfer.line;
            if (line.comboParent) {
                const comboRoot = line.getAllLinesInCombo()[0];
                if (!removedComboRoots.has(comboRoot)) {
                    removedComboRoots.add(comboRoot);
                    sourceOrder.removeOrderline(comboRoot);
                }
            } else if (line.comboLines?.length) {
                if (!removedComboRoots.has(line)) {
                    removedComboRoots.add(line);
                    sourceOrder.removeOrderline(line);
                }
            } else if (sourceOrder.get_orderline(line.id)) {
                sourceOrder.removeOrderline(line);
            }
        }

        if (this.orderPreparationCategories?.size) {
            sourceOrder.updateLastOrderChange();
        }

        sourceOrder.save_to_db();
        this.ordersToUpdateSet.add(sourceOrder);
        this.removeOrder(sourceOrder);
    },

    _recomputeRestaurantTableState(tableId) {
        const table = this.tables_by_id[tableId];

        if (!table) {
            return;
        }

        const activeOrders = this.getTableOrders(tableId).filter(
            (order) => !order.finalized
        );

        table.order_count = activeOrders.length;

        table.changes_count = activeOrders.reduce((count, order) => {
            return count + (order.get_orderlines?.()?.length || 0);
        }, 0);

        table.skip_changes = 0;
    },
});
