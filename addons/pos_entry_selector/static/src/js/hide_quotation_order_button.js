/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { patch } from "@web/core/utils/patch";

/** Hides pos_sale "Quotation/Order" (عرض السعر/الطلب) from control buttons entirely. */
patch(ProductScreen.prototype, {
    get controlButtons() {
        return super.controlButtons.filter((cb) => cb.name !== "SetSaleOrderButton");
    },
});
