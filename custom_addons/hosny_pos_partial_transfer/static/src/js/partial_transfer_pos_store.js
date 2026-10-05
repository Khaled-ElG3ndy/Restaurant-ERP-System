/** @odoo-module */

import { ConnectionLostError } from "@web/core/network/rpc";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { Order, Orderline, Packlotline } from "@point_of_sale/app/store/models";
import { ProductCustomAttribute } from "@point_of_sale/app/store/models/product_custom_attribute";

const EPSILON = 0.00001;

patch(PosStore.prototype, {
    async partialTransferOrderLines(sourceOrder, destinationTableId, transfers) {
        const sourceTable =
            sourceOrder?.getTable?.() ||
            sourceOrder?.table_id ||
            this.selectedTable ||
            null;
        const destinationTable = this.tables_by_id[destinationTableId];

        if (!sourceOrder || !sourceTable) {
            throw new Error(_t("لم يعد الطلب الحالي مرتبطاً بطاولة مطعم."));
        }
        if (!destinationTable) {
            throw new Error(_t("طاولة الوجهة لم تعد موجودة."));
        }
        if (sourceTable.id === destinationTable.id) {
            throw new Error(_t("يرجى اختيار طاولة وجهة مختلفة."));
        }
        if (!transfers?.length) {
            throw new Error(_t("لا توجد كميات محددة للتحويل."));
        }

        const normalizedTransfers = this._normalizePartialTransfers(sourceOrder, transfers);
        if (!normalizedTransfers.length) {
            throw new Error(_t("لا توجد عناصر صالحة متبقية للتحويل."));
        }

        await this._syncTableOrdersFromServer(destinationTable.id);

        const destinationOrder =
            this.getTableOrders(destinationTable.id).find((order) => !order.finalized) ||
            this._createPartialTransferDestinationOrder(destinationTable, sourceOrder);

        const createdLinesMap = new Map();
        for (const transfer of normalizedTransfers) {
            const newLine = this._cloneLineForTransfer(
                transfer.line,
                destinationOrder,
                transfer.quantity
            );
            const insertedLine = this._mergeOrAddTransferredLine(destinationOrder, newLine);
            createdLinesMap.set(transfer.line, insertedLine);
        }

        for (const transfer of normalizedTransfers) {
            const sourceLine = transfer.line;
            const destinationLine = createdLinesMap.get(sourceLine);
            if (!destinationLine) {
                continue;
            }

            destinationLine.comboLine = sourceLine.comboLine;
            if (!sourceLine.comboParent) {
                destinationLine.comboLines = [];
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

        this._applySourceOrderTransfer(sourceOrder, normalizedTransfers);
        // كان هنا updateLastOrderChange للطلبين تحت orderPreparationCategories،
        // وهي خاصية أودو 17 غير موجودة في 19 فلم يعمل أبداً: الصنف المنقول كان
        // سيُطبع مرة ثانية من طاولة الوجهة، وطاولة المصدر تطبع «إلغاء». ثم إنها
        // كانت ستعلّم كل ما لم يُرسل في الطلبين كأنه أُرسل.
        this._carryKitchenStateOnTransfer(
            sourceOrder,
            destinationOrder,
            normalizedTransfers,
            createdLinesMap
        );

        sourceOrder.save_to_db();
        destinationOrder.save_to_db();
        this.ordersToUpdateSet.add(sourceOrder);
        this.ordersToUpdateSet.add(destinationOrder);

        if (!sourceOrder.get_orderlines().length) {
            const wasSelectedOrder = this.get_order() === sourceOrder;
            this.removeOrder(sourceOrder);
            if (wasSelectedOrder) {
                const nextSourceOrder = this.getTableOrders(sourceTable.id).find(
                    (order) => !order.finalized
                );
                if (nextSourceOrder) {
                    this.set_order(nextSourceOrder);
                } else {
                    this.set_order(null);
                    this.showScreen("FloorScreen", { floor: sourceTable.floor });
                }
            }
        } else if (this.get_order() === sourceOrder) {
            this.set_order(sourceOrder);
        }

        this._recomputeRestaurantTableState(sourceTable.id);
        this._recomputeRestaurantTableState(destinationTable.id);

        try {
            await this.sendDraftToServer();
        } catch (error) {
            if (!(error instanceof ConnectionLostError)) {
                throw error;
            }
            Promise.reject(error);
        }

        return destinationOrder;
    },

    _normalizePartialTransfers(sourceOrder, transfers) {
        const normalizedTransfers = [];

        for (const transfer of transfers) {
            const line = sourceOrder.get_orderline(transfer.lineId);
            if (!line) {
                continue;
            }
            const quantity = parseFloat(transfer.quantity) || 0;
            if (quantity <= EPSILON) {
                continue;
            }
            const availableQty = line.get_quantity();
            if (quantity - availableQty > EPSILON) {
                throw new Error(
                    `${line.get_full_product_name()}: ${_t("الكمية المحددة أكبر من الكمية المتاحة.")}`
                );
            }
            normalizedTransfers.push({
                line,
                quantity: Math.min(quantity, availableQty),
            });
        }

        return normalizedTransfers;
    },

    /**
     * ما أُرسل للمطبخ ينتقل مع الصنف: الكمية المرسلة تُخصم من «آخر ما أُرسل»
     * في المصدر وتُسجَّل للسطر الجديد في الوجهة، فلا تذكرة «جديد» مكررة ولا
     * «إلغاء» للصنف نفسه. الجزء الذي لم يُرسل بعد يبقى منتظراً في الوجهة.
     * المنقول يُحسب من المرسَل أولاً: 3 أُرسل منها 2 ونُقل 1 ⇒ يبقى في
     * المصدر 2 أُرسل منهما 1 (وما زال 1 ينتظر).
     */
    _carryKitchenStateOnTransfer(sourceOrder, destinationOrder, transfers, createdLinesMap) {
        const sourceSent = sourceOrder.last_order_preparation_change?.lines;
        if (!sourceSent || !Object.keys(sourceSent).length) {
            return;
        }
        const destinationChange = destinationOrder.last_order_preparation_change || {};
        destinationChange.lines = destinationChange.lines || {};
        const uuidMap = new Map(
            [...createdLinesMap.entries()].map(([from, to]) => [from.uuid, to.uuid])
        );
        let moved = false;
        for (const { line, quantity } of transfers) {
            const key = Object.keys(sourceSent).find((k) => k.startsWith(line.uuid));
            if (!key) {
                continue;
            }
            const entry = sourceSent[key];
            const sentQty = entry.quantity || 0;
            const movedQty = Math.min(quantity, sentQty);
            if (movedQty <= EPSILON) {
                continue;
            }
            if (sentQty - movedQty > EPSILON) {
                sourceSent[key] = { ...entry, quantity: sentQty - movedQty };
            } else {
                delete sourceSent[key];
            }
            const destinationLine = createdLinesMap.get(line);
            if (destinationLine) {
                const destinationKey = destinationLine.preparationKey || destinationLine.uuid;
                const previous = destinationChange.lines[destinationKey];
                destinationChange.lines[destinationKey] = previous
                    ? { ...previous, quantity: (previous.quantity || 0) + movedQty }
                    : {
                          ...entry,
                          uuid: destinationLine.uuid,
                          combo_parent_uuid: entry.combo_parent_uuid
                              ? uuidMap.get(entry.combo_parent_uuid) || entry.combo_parent_uuid
                              : entry.combo_parent_uuid,
                          quantity: movedQty,
                      };
            }
            moved = true;
        }
        if (!moved) {
            return;
        }
        destinationOrder.last_order_preparation_change = destinationChange;
        // الوجهة فيها الآن ما أُرسل: زر «إرسال الطلب» يقرأ «تم الإرسال»، وعدّاد
        // الطاولة (hosny_pos_send_order) يبدأ من وقت إرسال المصدر.
        if ("preparation_state" in destinationOrder && destinationOrder.preparation_state !== "sent") {
            destinationOrder.preparation_state = "sent";
            if (!destinationOrder.preparation_sent_at && sourceOrder.preparation_sent_at) {
                destinationOrder.preparation_sent_at = sourceOrder.preparation_sent_at;
            }
        }
        sourceOrder._markDirty?.();
        destinationOrder._markDirty?.();
    },

    _createPartialTransferDestinationOrder(destinationTable, sourceOrder) {
        // الطاولة من لحظة الإنشاء: hosny_pos_printer_matrix يعطي الطلب الجديد
        // بلا طاولة نوع «سفري»، والسفري يُنزع منه أي طاولة (هنا وعلى الخادم)،
        // فكان المنقول يذهب إلى طلب سفري عائم لا يظهر على طاولة الوجهة.
        const destinationOrder = this.createReactiveOrder({ table_id: destinationTable });
        destinationOrder.tableId = destinationTable.id;
        destinationOrder.setBooked(true);
        destinationOrder.set_screen_data({ name: "ProductScreen" });
        // أودو 19: setPartner(undefined) يقرأ partner.is_company فيرمي خطأ، وأغلب
        // طلبات المطعم بلا عميل — فكان التحويل إلى طاولة فارغة يفشل دائماً
        // («تعذر إتمام التحويل … reading 'is_company'»).
        const partner = sourceOrder.get_partner?.();
        if (partner) {
            destinationOrder.set_partner(partner);
        }
        destinationOrder.set_pricelist(sourceOrder.pricelist || sourceOrder.pricelist_id);
        destinationOrder.set_fiscal_position(sourceOrder.fiscal_position || sourceOrder.fiscal_position_id);
        destinationOrder.to_invoice = sourceOrder.to_invoice;
        destinationOrder.shippingDate = sourceOrder.shippingDate || sourceOrder.shipping_date;
        this.orders.add(destinationOrder);
        return destinationOrder;
    },

    _cloneCustomAttributes(line) {
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

    _extractPackLotNames(sourceLine, quantity) {
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

    _applyPackLots(destinationLine, lotNames) {
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

    _cloneLineForTransfer(sourceLine, destinationOrder, quantity) {
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
            this._applyPackLots(destinationLine, this._extractPackLotNames(sourceLine, quantity));
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
        destinationLine.custom_attribute_value_ids = this._cloneCustomAttributes(sourceLine);
        destinationLine.full_product_name = sourceLine.full_product_name;
        destinationLine.price_type = sourceLine.price_type;
        destinationLine.skipChange = sourceLine.skipChange;
        destinationLine.refunded_orderline_id = sourceLine.refunded_orderline_id;
        destinationLine.refunded_qty = sourceLine.refunded_qty;
        destinationLine.saved_quantity = quantity;
        destinationLine.set_full_product_name();
        this._applyPackLots(destinationLine, this._extractPackLotNames(sourceLine, quantity));

        return destinationLine;
    },

    _mergeOrAddTransferredLine(destinationOrder, candidateLine) {
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

    _createDecreaseTransferLine(sourceLine, sourceOrder, quantity) {
        const decreaseLine = this._cloneLineForTransfer(sourceLine, sourceOrder, quantity);
        decreaseLine.order = sourceOrder;
        decreaseLine.noDecrease = true;
        decreaseLine.comboParent = undefined;
        decreaseLine.comboLines = undefined;
        decreaseLine.set_quantity(-quantity, "do not recompute unit price");
        decreaseLine.saved_quantity = -quantity;
        return decreaseLine;
    },

    _applySourceOrderTransfer(sourceOrder, normalizedTransfers) {
        const shouldUseDecreaseLines = this.disallowLineQuantityChange();

        if (shouldUseDecreaseLines) {
            for (const transfer of normalizedTransfers) {
                const decreaseLine = this._createDecreaseTransferLine(
                    transfer.line,
                    sourceOrder,
                    transfer.quantity
                );
                sourceOrder.add_orderline(decreaseLine);
            }
            return;
        }

        for (const transfer of normalizedTransfers) {
            transfer.line.set_quantity(
                transfer.line.get_quantity() - transfer.quantity,
                "do not recompute unit price"
            );
        }

        const removedComboRoots = new Set();
        for (const transfer of normalizedTransfers) {
            const line = transfer.line;
            if (Math.abs(line.get_quantity()) >= EPSILON) {
                continue;
            }

            if (line.comboParent) {
                const comboRoot = line.getAllLinesInCombo?.()?.[0] || line;
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
    },

    _recomputeRestaurantTableState(tableId) {
        const table = this.tables_by_id[tableId];
        if (!table) {
            return;
        }

        const activeOrders = this.getTableOrders(tableId).filter((order) => !order.finalized);
        table.order_count = activeOrders.length;
        table.changes_count = 0;
        table.skip_changes = 0;
    },
});
