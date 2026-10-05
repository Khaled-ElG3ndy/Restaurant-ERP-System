/** @odoo-module */

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

import { MergeTablesPopup } from "./merge_popup";

function getCurrentTable(pos, order) {
    return order?.getTable?.() || order?.table_id || pos?.selectedTable || pos?.table || null;
}

export class MergeTablesButton extends Component {
    static template = "hosny_pos_table_merge.MergeTablesButton";
    static props = {};

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }

    get currentOrder() {
        return this.pos.get_order();
    }

    get isDisabled() {
        return (
            !this.currentOrder ||
            !getCurrentTable(this.pos, this.currentOrder) ||
            this.currentOrder.finalized
        );
    }

    async click() {
        if (this.isDisabled) {
            return;
        }

        await this.popup.add(MergeTablesPopup, {
            order: this.currentOrder,
        });
    }
}

patch(ControlButtons, {
    components: {
        ...ControlButtons.components,
        MergeTablesButton,
    },
});
