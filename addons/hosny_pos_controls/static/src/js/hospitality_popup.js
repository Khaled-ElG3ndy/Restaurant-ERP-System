/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";


export class HospitalityPopup extends Component {
    static template = "hosny_pos_controls.HospitalityPopup";
    static components = { Dialog };
    static props = ["close"];

    setup() {
        this.pos = usePos();
        this.state = useState({ selectedIds: new Set(), adding: false });
    }

    get hospitalityProducts() {
        const configs = this.pos.models["pos.hospitality.config"]?.getAll?.() || [];
        const products = new Map();
        for (const config of configs) {
            for (const product of config.product_ids || []) {
                if (product?.active !== false && product?.available_in_pos !== false) {
                    products.set(product.id, product);
                }
            }
        }
        return [...products.values()].sort((a, b) =>
            (a.display_name || a.name || "").localeCompare(b.display_name || b.name || "")
        );
    }

    get filteredProducts() {
        return this.hospitalityProducts;
    }

    get selectedCount() {
        return this.state.selectedIds.size;
    }

    isSelected(product) {
        return this.state.selectedIds.has(product.id);
    }

    toggleProduct(product) {
        const selectedIds = new Set(this.state.selectedIds);
        if (selectedIds.has(product.id)) {
            selectedIds.delete(product.id);
        } else {
            selectedIds.add(product.id);
        }
        this.state.selectedIds = selectedIds;
    }

    selectAll() {
        this.state.selectedIds = new Set(this.filteredProducts.map((product) => product.id));
    }

    clearSelection() {
        this.state.selectedIds = new Set();
    }

    originalPrice(product) {
        const order = this.pos.getOrder();
        return product.getPrice(order?.pricelist_id || this.pos.config.pricelist_id, 1, 0, false);
    }

    formattedOriginalPrice(product) {
        return this.env.utils.formatCurrency(this.originalPrice(product));
    }

    async addSelected() {
        if (!this.selectedCount || this.state.adding) {
            return;
        }
        this.state.adding = true;
        try {
            for (const product of this.hospitalityProducts) {
                if (!this.state.selectedIds.has(product.id)) {
                    continue;
                }
                const line = await this.pos.addLineToCurrentOrder(
                    {
                        product_id: product,
                        product_tmpl_id: product.product_tmpl_id,
                        price_unit: 0,
                        is_hospitality: true,
                        hospitality_original_price: this.originalPrice(product),
                    },
                    {},
                    false
                );
                if (line) {
                    line.price_type = "manual";
                    line.setUnitPrice(0);
                    line.is_hospitality = true;
                    line.hospitality_original_price = this.originalPrice(product);
                    line.full_product_name = _t("Hospitality - %s", product.display_name || product.name);
                }
            }
            this.pos.notification.add(_t("Hospitality products added"), { type: "success" });
            this.props.close();
        } finally {
            this.state.adding = false;
        }
    }
}


patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.hospitalityButtonState = useState({ active: false });
    },

    openHospitalityPopup() {
        if (this.hospitalityButtonState.active) {
            return;
        }
        this.hospitalityButtonState.active = true;
        this.pos.dialog.add(HospitalityPopup, {}, {
            onClose: () => {
                this.hospitalityButtonState.active = false;
            },
        });
    },
});
