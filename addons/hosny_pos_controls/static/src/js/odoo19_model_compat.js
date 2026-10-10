/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    get_orderlines() {
        return this.getOrderlines?.() || this.lines || [];
    },

    get_paymentlines() {
        return this.payment_ids || [];
    },

    get_paymentline(lineId) {
        return this.get_paymentlines().find(
            (line) => line.id === lineId || line.uuid === lineId || line.cid === lineId
        );
    },

    add_paymentline(paymentMethod) {
        return this.addPaymentline?.(paymentMethod);
    },

    remove_paymentline(line) {
        return this.removePaymentline?.(line);
    },

    select_paymentline(line) {
        return this.selectPaymentline?.(line);
    },

    get_orderline(lineId) {
        return this.get_orderlines().find((line) => line.id === lineId || line.uuid === lineId);
    },

    get_partner() {
        return this.getPartner?.();
    },

    set_partner(partner) {
        return this.setPartner?.(partner);
    },

    set_pricelist(pricelist) {
        return this.setPricelist?.(pricelist);
    },

    set_fiscal_position(fiscalPosition) {
        this.fiscal_position_id = fiscalPosition;
    },

    set_screen_data(screenData) {
        return this.setScreenData?.(screenData);
    },

    get_screen_data() {
        return this.getScreenData?.();
    },

    add_orderline(line) {
        line.order_id = this;
        if (Array.isArray(this.lines) && !this.lines.includes(line)) {
            this.lines.push(line);
        }
        this.selectOrderline?.(line);
    },

    get_total_with_tax() {
        return this.totalDue ?? this.amount_total ?? 0;
    },

    get_rounding_applied() {
        return this.roundingApplied ?? 0;
    },

    get_due() {
        return this.remainingDue ?? 0;
    },

    get_change() {
        return this.change ?? 0;
    },

    save_to_db() {
        this._markDirty?.();
    },
});

Object.defineProperty(PosOrder.prototype, "paymentlines", {
    get() {
        return this.payment_ids || [];
    },
    set(paymentLines) {
        this.payment_ids = paymentLines || [];
    },
    configurable: true,
});

Object.defineProperty(PosOrder.prototype, "selected_paymentline", {
    get() {
        return this.getSelectedPaymentline?.() || null;
    },
    set(line) {
        this.selectPaymentline?.(line);
    },
    configurable: true,
});

Object.defineProperty(PosOrder.prototype, "tableId", {
    get() {
        return this.table_id?.id || this.table_id || null;
    },
    set(tableId) {
        this.table_id =
            typeof tableId === "number" ? this.models["restaurant.table"]?.get(tableId) : tableId;
    },
    configurable: true,
});

patch(PosOrderline.prototype, {
    getDisplayData() {
        const product = this.getProduct?.() || this.product_id;
        const unit = this.getUnit?.();
        const price =
            this.env?.utils?.formatCurrency?.(this.prices?.total_included_currency) ||
            this.env?.utils?.formatCurrency?.(this.price_unit * this.qty) ||
            "";
        return {
            productName:
                this.getFullProductName?.() || this.full_product_name || product?.display_name || "",
            price,
            unitPrice: this.env?.utils?.formatCurrency?.(this.price_unit || 0) || "",
            unit: unit?.name || "",
            quantity: this.getQuantity?.() || this.qty || 0,
            customerNote: this.getCustomerNote?.() || "",
            internalNote: this.getNote?.() || "",
            comboParent: this.combo_parent_id?.getFullProductName?.() || "",
            attributes: [],
        };
    },

    get_quantity() {
        return this.getQuantity?.() || this.qty || 0;
    },

    set_quantity(quantity, keepPrice) {
        return this.setQuantity?.(quantity, keepPrice);
    },

    get_product() {
        return this.getProduct?.() || this.product_id;
    },

    get_unit_price() {
        return this.price_unit || 0;
    },

    set_unit_price(price) {
        return this.setUnitPrice?.(price);
    },

    get_discount() {
        return this.getDiscount?.() || this.discount || 0;
    },

    set_discount(discount) {
        return this.setDiscount?.(discount);
    },

    get_price_extra() {
        return this.getPriceExtra?.() || this.price_extra || 0;
    },

    set_price_extra(priceExtra) {
        this.price_extra = priceExtra || 0;
    },

    get_customer_note() {
        return this.getCustomerNote?.() || "";
    },

    set_customer_note(note) {
        return this.setCustomerNote?.(note);
    },

    get_full_product_name() {
        return this.getFullProductName?.() || this.full_product_name || this.product_id?.display_name || "";
    },

    set_full_product_name() {
        return this.setFullProductName?.();
    },

    get_lot_lines() {
        return this.pack_lot_ids || [];
    },

    get_unit() {
        return this.getUnit?.();
    },

    get_all_prices(quantity = this.get_quantity()) {
        const currentQty = this.get_quantity() || 1;
        const ratio = quantity / currentQty;
        const totalWithTax =
            this.prices?.total_included_currency ??
            this.priceIncl ??
            this.displayPrice ??
            this.price_unit * currentQty;
        const totalWithoutTax =
            this.prices?.total_excluded_currency ??
            this.priceExcl ??
            this.displayPrice ??
            this.price_unit * currentQty;
        return {
            priceWithTax: (totalWithTax || 0) * ratio,
            priceWithoutTax: (totalWithoutTax || 0) * ratio,
        };
    },

    can_be_merged_with(line) {
        return this.canBeMergedWith?.(line);
    },
});

Object.defineProperty(PosOrderline.prototype, "comboParent", {
    get() {
        return this.combo_parent_id;
    },
    set(line) {
        this.combo_parent_id = line;
    },
    configurable: true,
});

Object.defineProperty(PosOrderline.prototype, "comboLines", {
    get() {
        return this.combo_line_ids || [];
    },
    set(lines) {
        this.combo_line_ids = lines || [];
    },
    configurable: true,
});

Object.defineProperty(PosOrderline.prototype, "comboLine", {
    get() {
        return this.combo_item_id;
    },
    set(comboItem) {
        this.combo_item_id = comboItem;
    },
    configurable: true,
});

patch(PosStore.prototype, {
    get_order() {
        return this.getOrder?.();
    },

    set_order(order) {
        return this.setOrder?.(order);
    },

    get_order_list() {
        return this.getOpenOrders?.() || [];
    },

    add_new_order(data) {
        return this.addNewOrder?.(data);
    },

    showScreen(screenName, params) {
        return this.navigate?.(screenName, params);
    },

    createReactiveOrder(data = {}) {
        return this.createNewOrder?.(data);
    },

    async sendDraftToServer(options = {}) {
        return this.syncAllOrders?.(options);
    },

    async _syncTableOrdersFromServer(tableId) {
        if (tableId && this.syncAllOrders) {
            await this.syncAllOrders({ table_ids: [tableId] });
        }
        return this.getTableOrders?.(tableId) || [];
    },

    async _removeOrdersFromServer() {
        return true;
    },

    async _getTableOrdersFromServer() {
        return [];
    },

    async _loadMissingProducts() {
        return true;
    },

    async _loadMissingPartners() {
        return true;
    },

    async _addPricelists() {
        return true;
    },

    async _addFiscalPositions() {
        return true;
    },

    _replaceOrders() {
        return true;
    },

    _recomputeRestaurantTableState(tableId) {
        const table = this.models?.["restaurant.table"]?.get?.(tableId);
        if (table) {
            table.order_count = table.getOrders?.().filter((order) => !order.finalized).length || 0;
        }
    },
});

Object.defineProperty(PosStore.prototype, "tables_by_id", {
    get() {
        const tablesById = this.models?.["restaurant.table"]?.getAllBy?.("id");
        if (!tablesById?.get) {
            return tablesById || {};
        }
        return new Proxy(
            {},
            {
                get(_target, prop) {
                    if (prop === "values") {
                        return () => tablesById.values();
                    }
                    if (prop === Symbol.iterator) {
                        return tablesById[Symbol.iterator].bind(tablesById);
                    }
                    return tablesById.get(Number(prop)) || tablesById.get(prop);
                },
                ownKeys() {
                    return Array.from(tablesById.keys()).map(String);
                },
                getOwnPropertyDescriptor() {
                    return { enumerable: true, configurable: true };
                },
            }
        );
    },
    configurable: true,
});

Object.defineProperty(PosStore.prototype, "orders", {
    get() {
        return {
            models: this.getOpenOrders?.() || [],
            add: () => true,
        };
    },
    configurable: true,
});

Object.defineProperty(PosStore.prototype, "ordersToUpdateSet", {
    get() {
        return {
            add: (order) => order?.id && this.addPendingOrder?.([order.id]),
        };
    },
    configurable: true,
});

/**
 * سطر حُذف من طلبه (دمج صنف مكرر، أو حذف) قد يبقى مرسوماً لحظة؛ أودو يقرأ
 * this.order_id.fiscal_position_id في taxGroupLabels فينهار الكاشير بـ
 * «Cannot read properties of undefined (reading 'fiscal_position_id')».
 * السطر بلا طلب ليس له تسمية ضريبة (2026-10-09).
 */
patch(PosOrderline.prototype, {
    get taxGroupLabels() {
        if (!this.order_id) {
            return "";
        }
        return super.taxGroupLabels;
    },
});

/**
 * ونفس الشيء مع العملة: أودو يقرأ this.order_id.currency في getter السطر،
 * فينهار بـ «Cannot read properties of undefined (reading 'currency')» لسطر
 * حُذف ولا يزال مرسوماً. نرجع عملة نقطة البيع بدل الانهيار (2026-10-09).
 */
patch(PosOrderline.prototype, {
    get currency() {
        if (!this.order_id) {
            return this.models?.["pos.config"]?.getFirst?.()?.currency_id;
        }
        return super.currency;
    },
});
