/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component } from "@odoo/owl";

/**
 * Read-only cost value with its details action in the same field cell.
 *
 * Keeping the action inside the field widget prevents Odoo's list renderer
 * from allocating a separate button column, so the icon always stays beside
 * the formatted amount in both LTR and RTL layouts.
 */
export class PosAdditionalCostField extends Component {
    static template = "hosny_pos_meal_combo.PosAdditionalCostField";
    static props = { ...standardFieldProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get hasDetails() {
        return Boolean(
            this.props.record.resId &&
            this.props.record.data.ui_has_additional_products
        );
    }

    get detailsTitle() {
        return _t("Details");
    }

    async openDetails() {
        const action = await this.orm.call(
            "pos.order.line",
            "action_open_additional_cost_breakdown",
            [[this.props.record.resId]],
            { context: this.props.record.context }
        );
        await this.action.doAction(action);
    }
}

export const posAdditionalCostField = {
    component: PosAdditionalCostField,
    displayName: _t("Additional Products Cost"),
    supportedTypes: ["char"],
    fieldDependencies: [
        { name: "ui_has_additional_products", type: "boolean" },
    ],
};

registry.category("fields").add("pos_additional_cost", posAdditionalCostField);

/**
 * Explicit product link for the read-only breakdown list.
 *
 * Odoo can suppress the native many2one link inside nested read-only lists.
 * Close the cost dialog first, then navigate to the actual product variant
 * form as a normal current action.
 */
export class PosProductInternalLink extends Component {
    static template = "hosny_pos_meal_combo.PosProductInternalLink";
    static props = { ...standardFieldProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    get product() {
        return this.props.record.data[this.props.name];
    }

    get productName() {
        return this.product?.display_name || "";
    }

    get productHref() {
        return this.product?.id ? `/odoo/m-product.product/${this.product.id}` : "#";
    }

    async openProduct() {
        if (!this.product?.id) {
            return;
        }
        const productAction = await this.orm.call(
            "product.product",
            "get_formview_action",
            [[this.product.id]],
            { context: this.props.record.context || {} }
        );
        await this.action.doAction({ type: "ir.actions.act_window_close" });
        await this.action.doAction(productAction);
    }
}

export const posProductInternalLink = {
    component: PosProductInternalLink,
    displayName: _t("Product Internal Link"),
    supportedTypes: ["many2one"],
};

registry.category("fields").add("pos_product_internal_link", posProductInternalLink);
