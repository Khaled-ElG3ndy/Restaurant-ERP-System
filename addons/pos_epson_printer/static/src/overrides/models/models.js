/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { EpsonPrinter } from "@pos_epson_printer/app/epson_printer";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    createPrinter(config) {
        if (config.printer_type === "epson_epos") {
            return new EpsonPrinter({ ip: config.epson_printer_ip });
        } else {
            return super.createPrinter(...arguments);
        }
    },
});
