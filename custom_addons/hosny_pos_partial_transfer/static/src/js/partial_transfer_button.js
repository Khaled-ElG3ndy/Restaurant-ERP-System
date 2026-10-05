/** @odoo-module */

import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";

import { PartialTransferPopup } from "./partial_transfer_popup";

function getAllTables(pos) {
    const modelTables = pos?.models?.["restaurant.table"]?.getAll?.();
    if (modelTables?.length) {
        return modelTables;
    }
    const floors = pos?.config?.floor_ids || pos?.floors || [];
    return floors.flatMap((floor) => floor?.table_ids || floor?.tables || []);
}

function getCurrentTable(pos, order) {
    return order?.getTable?.() || order?.table_id || pos?.selectedTable || pos?.table || null;
}

export class PartialTransferButton extends Component {
    static template = "hosny_pos_partial_transfer.PartialTransferButton";
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
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
        console.log("PARTIAL CLICK WORKING");
        if (this.isDisabled) {
            return;
        }

        if (!this.currentOrder.get_orderlines().length) {
            await this.dialog.add(AlertDialog, {
                title: _t("لا توجد عناصر للتحويل"),
                body: _t("أضف منتجات إلى الطلب قبل محاولة تحويل جزء منه إلى طاولة أخرى."),
            });
            return;
        }

        const currentTable = getCurrentTable(this.pos, this.currentOrder);
        const availableTables = getAllTables(this.pos).filter(
            (table) => table.id !== currentTable.id
        );

        if (!availableTables.length) {
            await this.dialog.add(AlertDialog, {
                title: _t("لا توجد طاولة وجهة"),
                body: _t("أنشئ طاولة مطعم أخرى قبل استخدام التحويل الجزئي."),
            });
            return;
        }

        await this.dialog.add(PartialTransferPopup, {
            order: this.currentOrder,
            getPayload: () => { },
        });
    }
}

// BUG FIX 2: ControlButtons.prototype was patched TWICE with the identical body.
// The second patch silently overwrites setup(), causing the first patch's super.setup()
// chain to break. Keep only ONE patch.
patch(ControlButtons.prototype, {
    setup() {
        super.setup?.();
        this.partialTransferButton = PartialTransferButton;
    },
});

ControlButtons.components = {
    ...ControlButtons.components,
    PartialTransferButton,
};