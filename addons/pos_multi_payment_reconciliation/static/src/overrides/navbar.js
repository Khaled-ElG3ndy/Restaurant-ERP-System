/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

import { Navbar } from "@point_of_sale/app/navbar/navbar";
import { MultiCashMovePopup } from "@pos_multi_payment_reconciliation/app/navbar/multi_cash_move_popup/multi_cash_move_popup";

patch(Navbar.prototype, {
    get showCashMoveButton() {
        return Boolean(this.pos?.config?.cash_control && this.pos?.config?.has_cash_move_permission);
    },

    onCashMoveButtonClick() {
        this.hardwareProxy.openCashbox(_t("Cash in / out"));
        this.popup.add(MultiCashMovePopup);
    },
});
