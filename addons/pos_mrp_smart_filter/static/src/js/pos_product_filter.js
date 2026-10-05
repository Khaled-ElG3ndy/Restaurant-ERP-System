/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ProductsWidget } from "@point_of_sale/app/screens/product_screen/product_list/product_list";

patch(ProductsWidget.prototype, {
    get productsToDisplay() {
        const products = super.productsToDisplay;
        if (!Array.isArray(products)) {
            return products;
        }
        return products.filter((product) => {
            if (!product) {
                return false;
            }
            if (typeof product.getFormattedUnitPrice !== "function") {
                return false;
            }
            if (product.type === "service" || product.type === "consu") {
                return true;
            }
            if (product.pos_can_be_sold_or_manufactured === undefined) {
                return true;
            }
            return !!product.pos_can_be_sold_or_manufactured;
        });
    },
}); 