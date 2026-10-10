/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";

function getTableAmount(component, table) {
    const pos = component.pos || component.env.services.pos;
    if (!pos || !table) {
        return null;
    }

    const orders = pos.getTableOrders ? pos.getTableOrders(table.id) : pos.get_order_list?.() || [];

    let total = 0;

    for (const order of orders) {
        if (!order || order.finalized || order.validation_date) {
            continue;
        }
        total += order.get_total_with_tax ? order.get_total_with_tax() : 0;
    }

    if (!total) {
        return null;
    }

    // 51.00 SR — الرمز بعد الرقم كبقية الشاشات، معزول LTR وإلا قلبته
    // الشاشة العربية إلى SR 51.00.
    const symbol = pos.currency?.symbol ?? pos.config?.currency_id?.symbol ?? "";
    const number = component.env.utils.formatCurrency(total, false);
    return symbol ? `\u2066${number}\u00a0${symbol}\u2069` : number;
}

patch(FloorScreen.prototype, {
    getTableAmount(table) {
        return getTableAmount(this, table);
    },
});
