/** @odoo-module */

// BUG FIX 4: This code was concatenated directly into partial_transfer_button.js.
// Since that file already imports and uses @odoo/owl, @web/core/utils/patch, etc.,
// the duplicate import statements and the stray module comment "/** @odoo-module */"
// mid-file caused a parse/load error in some bundler versions, silently preventing
// the whole asset from executing. Keep each logical unit in its own file.

import { patch } from "@web/core/utils/patch";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";

patch(ProductScreen.prototype, {
    get bottomControlButtons() {
        const buttons = [...(super.bottomControlButtons || [])];
        const partialTransferIndex = buttons.findIndex(
            (button) => button.name === "PartialTransferButton"
        );

        if (partialTransferIndex === -1) {
            return buttons;
        }

        const [partialTransferButton] = buttons.splice(partialTransferIndex, 1);
        const transferIndex = buttons.findIndex((button) => button.name === "TransferOrderButton");
        const splitIndex = buttons.findIndex((button) => button.name === "SplitBillButton");
        const printBillIndex = buttons.findIndex((button) => button.name === "PrintBillButton");
        const anchorIndex = [printBillIndex, transferIndex, splitIndex].find((index) => index !== -1);

        buttons.splice(
            anchorIndex === undefined ? buttons.length : anchorIndex + 1,
            0,
            partialTransferButton
        );
        return buttons;
    },
});