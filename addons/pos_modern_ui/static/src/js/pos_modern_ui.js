/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

patch(Navbar.prototype, {
    get shouldShowWorkplaceButton() {
        const pos = this.env.services.pos;

        const currentScreen = pos.getCurrentScreen
            ? pos.getCurrentScreen()
            : pos.mainScreen?.component?.name;

        return currentScreen !== "ProductScreen";
    },

    goToWorkplaceSelector() {
        const pos = this.env.services.pos;

        if (pos.entrySelectorVisible !== undefined) {
            pos.entrySelectorVisible = true;
        }

        if (typeof pos.showScreen === "function") {
            pos.showScreen("FloorScreen");
        } else {
            pos.navigate?.("FloorScreen");
        }

        setTimeout(() => {
            const floorScreen = pos.mainScreen?.component;
            floorScreen?.refreshFloorState?.();
            floorScreen?.render?.();
        }, 50);
    },
});

patch(ProductScreen.prototype, {
    getProductImage() {
        return false;
    },
});
