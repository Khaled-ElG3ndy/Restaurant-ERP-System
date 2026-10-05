/** @odoo-module **/

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    goToWorkplaceSelector() {
        if (this.pos.entrySelectorVisible !== undefined) {
            this.pos.entrySelectorVisible = true;
        }

        this.pos.navigate("FloorScreen");

        setTimeout(() => {
            const floorScreen = this.pos.mainScreen?.component;
            floorScreen?.refreshFloorState?.();
            floorScreen?.render?.();
        }, 50);
    },
});
