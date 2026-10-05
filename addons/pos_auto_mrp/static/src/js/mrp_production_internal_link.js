/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

import { Component } from "@odoo/owl";

/** Make the displayed MO reference itself the direct internal link. */
export class PosMrpProductionInternalLink extends Component {
    static template = "pos_auto_mrp.PosMrpProductionInternalLink";
    static props = { ...standardFieldProps };

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
    }

    get production() {
        return this.props.record.data[this.props.name];
    }

    get productionName() {
        return this.production?.display_name || "";
    }

    get productionHref() {
        return this.production?.id
            ? `/odoo/m-mrp.production/${this.production.id}`
            : "#";
    }

    async openProduction() {
        if (!this.production?.id) {
            return;
        }
        const productionAction = await this.orm.call(
            "mrp.production",
            "get_formview_action",
            [[this.production.id]],
            { context: this.props.record.context || {} }
        );
        if (this.env.inDialog) {
            await this.action.doAction({ type: "ir.actions.act_window_close" });
        }
        await this.action.doAction(productionAction);
    }
}

export const posMrpProductionInternalLink = {
    component: PosMrpProductionInternalLink,
    displayName: _t("Manufacturing Order Internal Link"),
    supportedTypes: ["many2one"],
};

registry
    .category("fields")
    .add("pos_mrp_production_internal_link", posMrpProductionInternalLink);
