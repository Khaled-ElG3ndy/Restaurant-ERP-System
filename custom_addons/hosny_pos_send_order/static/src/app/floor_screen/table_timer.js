/** @odoo-module */

import { onMounted, onWillUnmount, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";

function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60)
        .toString()
        .padStart(2, "0");
    const remainder = Math.max(0, seconds % 60)
        .toString()
        .padStart(2, "0");
    return `${minutes}:${remainder}`;
}

patch(FloorScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.timerState = useState({ now: Date.now() });
        onMounted(() => {
            this.timerInterval = setInterval(() => {
                this.timerState.now = Date.now();
            }, 1000);
        });
        onWillUnmount(() => clearInterval(this.timerInterval));
    },

    /**
     * أقدم وقت إرسال بين طلبات الطاولة. طلبات الطاولات المفتوحة محمّلة أصلاً
     * في شاشة الصالة، والحقل يزامَن مع الخادم، فالقيمة نفسها تظهر على كل جهاز.
     */
    getTableSentAtDate(table) {
        const sentDates = this.pos
            .getTableOrders(table.id)
            .filter((order) => !order.finalized)
            .map((order) => order.getPreparationSentDate?.())
            .filter(Boolean);

        if (!sentDates.length) {
            return null;
        }
        return sentDates.reduce((oldest, date) => (date < oldest ? date : oldest));
    },

    hasTableSentPreparation(table) {
        return !!this.getTableSentAtDate(table);
    },

    getTableSentElapsedDisplay(table) {
        const sentAtDate = this.getTableSentAtDate(table);
        if (!sentAtDate) {
            return "";
        }
        const elapsedSeconds = Math.floor((this.timerState.now - sentAtDate.toMillis()) / 1000);
        return formatDuration(Math.max(0, elapsedSeconds));
    },
});
