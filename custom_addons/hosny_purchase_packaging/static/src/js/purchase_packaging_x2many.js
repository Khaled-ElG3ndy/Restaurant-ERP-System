/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    X2ManyField,
    x2ManyField,
} from "@web/views/fields/x2many/x2many_field";

/**
 * Persist the completed packaging row before opening the next inline row.
 *
 * A Many2one autocomplete can only return database records.  Without this,
 * a packaging added earlier in the same unsaved product edit still has a
 * virtual client id, so it cannot immediately be selected as an inner
 * packaging.  Saving the existing product here converts all completed rows
 * to real ids and reloads the x2many before the next row is opened.
 */
export class PurchasePackagingX2ManyField extends X2ManyField {
    async onAdd({ context, editable } = {}) {
        const saved = await this.props.record.model.root.save();
        if (!saved) {
            return;
        }
        return super.onAdd({ context, editable });
    }
}

export const purchasePackagingX2ManyField = {
    ...x2ManyField,
    component: PurchasePackagingX2ManyField,
};

registry
    .category("fields")
    .add("hosny_purchase_packaging_x2many", purchasePackagingX2ManyField);
