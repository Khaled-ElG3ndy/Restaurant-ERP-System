/** @odoo-module **/

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    async openPaymentOrders() {
        if (typeof this.pos?.syncAllOrders === "function") {
            try {
                await this.pos.syncAllOrders();
            } catch (error) {
                console.warn("Failed to refresh unpaid POS orders before opening payment list.", error);
            }
        }
        this.pos.navigate("HosnyPaymentOrdersScreen");
    },
});
