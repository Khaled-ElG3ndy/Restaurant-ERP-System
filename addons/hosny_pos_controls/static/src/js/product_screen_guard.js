/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

patch(ProductScreen.prototype, {
    get items() {
        return this.currentOrder?.orderlines?.reduce((items, line) => items + line.quantity, 0) ?? 0;
    },

    selectLine(orderline) {
        if (!this.currentOrder) {
            return;
        }
        return super.selectLine(orderline);
    },

    async updateSelectedOrderline() {
        if (!this.pos.get_order()) {
            this.numberBuffer.reset();
            return;
        }
        return super.updateSelectedOrderline(...arguments);
    },

    _setValue(val) {
        if (!this.currentOrder) {
            return;
        }
        return super._setValue(val);
    },

    get selectedOrderlineQuantity() {
        return this.currentOrder?.get_selected_orderline()?.get_quantity_str() ?? "";
    },

    get selectedOrderlineDisplayName() {
        return this.currentOrder?.get_selected_orderline()?.get_full_product_name() ?? "";
    },

    get selectedOrderlineTotal() {
        return this.env.utils.formatCurrency(
            this.currentOrder?.get_selected_orderline()?.get_display_price() ?? 0
        );
    },

    get animationKey() {
        return [
            this.currentOrder?.get_selected_orderline()?.uuid ?? "",
            this.selectedOrderlineQuantity,
            this.selectedOrderlineDisplayName,
            this.selectedOrderlineTotal,
        ].join(",");
    },

    primaryPayButton() {
        return this.currentOrder ? !this.currentOrder.is_empty() : false;
    },
});
