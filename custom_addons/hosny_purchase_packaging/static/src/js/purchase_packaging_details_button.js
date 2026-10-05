/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Field } from "@web/views/fields/field";
import { getFieldDomain } from "@web/model/relational_model/utils";
import {
    X2ManyField,
    x2ManyField,
} from "@web/views/fields/x2many/x2many_field";
import {
    ProductLabelSectionAndNoteOne2Many,
    productLabelSectionAndNoteOne2Many,
} from "@account/components/product_label_section_and_note_field/product_label_section_and_note_field_o2m";
import {
    X2ManyFieldDialog,
    useSpecialData,
} from "@web/views/fields/relational_utils";

import { Component } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

function relationalDisplayName(value, fallback = "") {
    if (Array.isArray(value)) {
        return value[1] || fallback;
    }
    return value?.display_name || value?.name || value?.label || fallback;
}

function relationalId(value) {
    if (Array.isArray(value)) {
        return value[0];
    }
    return value?.id || value?.resId || false;
}

function compactNumber(value) {
    return new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 4,
        useGrouping: false,
    }).format(Number(value || 0));
}

/**
 * Derive the two values displayed in the product template's one2many list.
 *
 * Stored computed fields are recalculated correctly by the server, but an
 * extended x2many dialog does not reload its parent row after it closes.  Keep
 * the browser-side row in sync from the exact levels already held by the
 * dialog; the server compute remains the source of truth when the product is
 * saved.
 */
function getTemplateListPresentation(record) {
    const levels = [...(record.data.line_ids?.records || [])].sort((left, right) => {
        const sequenceDiff = Number(left.data.sequence || 0) - Number(right.data.sequence || 0);
        return sequenceDiff || String(left.id).localeCompare(String(right.id));
    });
    const outerName = relationalDisplayName(record.data.main_packaging_type_id);
    if (!outerName || !levels.length) {
        return { final_base_qty: 0, summary: false };
    }

    let finalBaseQuantity = 1;
    const summaryParts = [outerName];
    for (const level of levels) {
        const quantity = Number(level.data.quantity || 0);
        const isFinal = level.data.content_type === "base_uom";
        const contentName = relationalDisplayName(
            isFinal ? level.data.final_uom_id : level.data.packaging_type_id
        );
        if (!quantity || !contentName) {
            return { final_base_qty: 0, summary: false };
        }
        summaryParts.push(`${compactNumber(quantity)} ${contentName}`);
        finalBaseQuantity *= quantity;
        if (isFinal) {
            finalBaseQuantity *= Number(level.data.base_uom_factor || 0);
        }
    }
    return {
        final_base_qty: finalBaseQuantity,
        summary: summaryParts.join(" × "),
    };
}

/**
 * Odoo normally hides "Save & New" while editing an existing one2many row.
 * Packaging entry is a repeatable line workflow, so keep the full three-button
 * footer for this form only.  X2ManyFieldDialog.saveAndNew already saves the
 * current row and creates the next virtual purchase line safely.
 */
patch(X2ManyFieldDialog.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
        if (
            this.record.resModel === "purchase.order.line" &&
            this.contentClass.includes("o_hosny_packaging_dialog_form")
        ) {
            this.canCreate = true;
        }
    },

    _hosnyHasUnacknowledgedDuplicateProduct() {
        if (
            this.record.resModel !== "purchase.order.line" ||
            this.record.data.hosny_duplicate_warning_acknowledged
        ) {
            return false;
        }
        const productId = relationalId(this.record.data.product_id);
        const root = this.record.model.root;
        const orderLines = root.resModel === "purchase.order"
            ? root.data.order_line?.records || []
            : [];
        return Boolean(productId) && orderLines.some((line) =>
            line.id !== this.record.id &&
            !line.data.display_type &&
            relationalId(line.data.product_id) === productId
        );
    },

    _hosnyConfirmSeparateDuplicateLine() {
        const productName = relationalDisplayName(this.record.data.product_id, _t("this product"));
        return new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Duplicate Product Warning"),
                body: _t(
                    'The product "%s" already exists on another purchase line. ' +
                    "Continuing will keep this as a separate line with its own purchase packaging, quantity, and price.",
                    productName
                ),
                confirmLabel: _t("Keep as Separate Line"),
                confirmClass: "btn-warning",
                cancelLabel: _t("Go Back"),
                confirm: async () => {
                    await this.record.update({
                        hosny_duplicate_warning_acknowledged: true,
                    });
                    resolve(true);
                },
                cancel: () => resolve(false),
                dismiss: () => resolve(false),
            });
        });
    },

    async save({ saveAndNew }) {
        const isPackagingDialog = this.contentClass.includes(
            "o_hosny_packaging_dialog_form"
        );
        const levelFieldName =
            this.record.resModel === "purchase.order.line"
                ? "hosny_packaging_level_ids"
                : this.record.resModel === "hosny.purchase.packaging.template"
                  ? "line_ids"
                  : false;
        if (isPackagingDialog && levelFieldName) {
            const levels = this.record.data[levelFieldName];
            const editedLevel = levels?.editedRecord;
            if (editedLevel) {
                // A many2one can still be applying its last UI value when the
                // dialog save button is clicked.  Flush those local changes,
                // then commit the edited one2many row before the parent record
                // is checked and converted into ORM commands.
                const pendingChanges = [];
                levels.model.bus.trigger("NEED_LOCAL_CHANGES", {
                    proms: pendingChanges,
                });
                await Promise.all([
                    ...pendingChanges,
                    editedLevel._updatePromise,
                ]);
                const committed = await levels.leaveEditMode({ canAbandon: false });
                if (!committed) {
                    return false;
                }
            }
            if (
                this.record.resModel === "purchase.order.line" &&
                this._hosnyHasUnacknowledgedDuplicateProduct() &&
                !(await this._hosnyConfirmSeparateDuplicateLine())
            ) {
                return false;
            }
            if (this.record.resModel === "hosny.purchase.packaging.template") {
                // validateExtendedRecord() copies this extended record back to
                // the existing one2many row.  Updating the presentation fields
                // before that callback makes both columns repaint immediately,
                // with no parent form or browser reload.
                await this.record.update(getTemplateListPresentation(this.record));
            }
        }
        return super.save({ saveAndNew });
    },
});

/**
 * Keep Purchase's section/note renderer, but open the current x2many record in
 * Odoo's native dialog instead of X2ManyField.switchToForm().  In Odoo 19 the
 * latter deliberately saves the parent and navigates to a full-page line form.
 * `_openRecord` uses useOpenX2ManyRecord, so it also edits virtual (unsaved)
 * lines and only applies the extended record when the dialog is saved.
 */
export class PurchasePackagingLines extends ProductLabelSectionAndNoteOne2Many {
    async switchToForm(record) {
        return this._openRecord({
            record,
            context: this.props.context,
            readonly: this.props.readonly,
            title: _t("Packaging Details"),
        });
    }
}

export const purchasePackagingLines = {
    ...productLabelSectionAndNoteOne2Many,
    component: PurchasePackagingLines,
};

registry.category("fields").add("hosny_purchase_packaging_lines", purchasePackagingLines);

/**
 * A clear proxy for Odoo's native x2many open-form action.
 *
 * The native action is deliberately kept in the list and routed by the custom
 * x2many widget above to Odoo's unsaved-record dialog.  This field widget only
 * gives that action a visible Arabic label in the requested column; it never
 * creates a transient copy of the purchase line.
 */
export class PurchasePackagingDetailsButton extends Component {
    static template = "hosny_purchase_packaging.PurchasePackagingDetailsButton";
    static props = { ...standardFieldProps };

    setup() {
        this.notification = useService("notification");
    }

    openDetails(event) {
        const row = event.currentTarget.closest("tr");
        const nativeOpenCell = row?.querySelector(".o_list_record_open_form_view");
        if (!nativeOpenCell) {
            this.notification.add(_t("Packaging details could not be opened. Reload the page and try again."), {
                type: "danger",
            });
            return;
        }
        nativeOpenCell.click();
    }
}

export const purchasePackagingDetailsButton = {
    component: PurchasePackagingDetailsButton,
    supportedTypes: ["boolean"],
    fieldDependencies: [
        { name: "hosny_line_packaging_summary", type: "char" },
    ],
};

registry
    .category("fields")
    .add("hosny_packaging_details_button", purchasePackagingDetailsButton);

/** Open the actual product one2many row so its summary refreshes on save. */
export class PackagingTemplateDetailsButton extends Component {
    static template = "hosny_purchase_packaging.PackagingTemplateDetailsButton";
    static props = { ...standardFieldProps };

    setup() {
        this.notification = useService("notification");
    }

    openDetails(event) {
        const row = event.currentTarget.closest("tr");
        const nativeOpenCell = row?.querySelector(".o_list_record_open_form_view");
        if (!nativeOpenCell) {
            this.notification.add(
                _t("Packaging details could not be opened. Reload the page and try again."),
                { type: "danger" }
            );
            return;
        }
        nativeOpenCell.click();
    }
}

export const packagingTemplateDetailsButton = {
    component: PackagingTemplateDetailsButton,
    supportedTypes: ["boolean"],
    fieldDependencies: [
        { name: "summary", type: "char" },
        { name: "final_base_qty", type: "float" },
    ],
};

registry.category("fields").add(
    "hosny_packaging_template_details_button",
    packagingTemplateDetailsButton
);

/** Rich selector for reusable product-template packaging snapshots. */
export class SavedPackagingCards extends Component {
    static template = "hosny_purchase_packaging.SavedPackagingCards";
    static props = {
        ...standardFieldProps,
        domain: { type: [Array, Function], optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.specialData = useSpecialData(async (orm, props) => {
            const { relation } = props.record.fields[props.name];
            const domain = getFieldDomain(props.record, props.name, props.domain);
            const { records } = await orm.call(relation, "web_search_read", [], {
                domain,
                specification: {
                    display_name: {},
                    name: {},
                },
                order: "sequence, name, id",
            });
            return records;
        });
    }

    get templates() {
        return this.specialData.data || [];
    }

    get selectedId() {
        return this.props.record.data[this.props.name]?.id || false;
    }

    async selectTemplate(template) {
        if (this.selectedId === template.id) {
            await this.props.record.update({ [this.props.name]: false });
            return;
        }
        await this.props.record.update({
            [this.props.name]: {
                id: template.id,
                display_name: template.display_name || template.name,
            },
        });
        this.notification.add(_t("The saved packaging has been loaded."), {
            type: "success",
        });
    }

}

export const savedPackagingCards = {
    component: SavedPackagingCards,
    supportedTypes: ["many2one"],
    extractProps: (_staticInfo, dynamicInfo) => ({ domain: dynamicInfo.domain }),
};

registry.category("fields").add("hosny_saved_packaging_cards", savedPackagingCards);

/** Insert a packaging component immediately before the terminal UoM row. */
export class AddPackagingLevelButton extends Component {
    static template = "hosny_purchase_packaging.AddPackagingLevelButton";
    static props = { ...standardFieldProps };

    setup() {
        this.notification = useService("notification");
    }

    async addLevel() {
        const list = this.props.record.data.hosny_packaging_level_ids;
        if (!list) {
            return;
        }
        if (list.records.length >= 10) {
            this.notification.add(_t("You cannot add more than 10 packaging levels."), {
                type: "warning",
            });
            return;
        }
        const canProceed = await list.leaveEditMode({ canAbandon: false });
        if (!canProceed) {
            return;
        }
        let terminalIndex = list.records.findIndex(
            (record) => record.data.content_type === "base_uom"
        );
        if (terminalIndex < 0) {
            const productUom = this.props.record.data.product_uom_id;
            await list.addNewRecord({
                position: "bottom",
                mode: "edit",
                context: {
                    default_content_type: "base_uom",
                    default_quantity: 1,
                    default_final_uom_id: productUom?.id || productUom?.resId || false,
                },
            });
            terminalIndex = list.records.length - 1;
        }
        const context = {
            default_content_type: "packaging",
            default_quantity: 1,
        };
        if (terminalIndex === 0) {
            await list.addNewRecord({ position: "top", mode: "edit", context });
        } else {
            await list.addNewRecordAtIndex(terminalIndex - 1, { mode: "edit", context });
        }
    }
}

export const addPackagingLevelButton = {
    component: AddPackagingLevelButton,
    supportedTypes: ["integer"],
    fieldDependencies: [
        { name: "hosny_packaging_level_ids", type: "one2many" },
        { name: "product_uom_id", type: "many2one" },
    ],
};

registry.category("fields").add(
    "hosny_add_packaging_level_button",
    addPackagingLevelButton
);

/** Render the existing level records as natural packaging sentences. */
export class PackagingSentenceLevels extends X2ManyField {
    static template = "hosny_purchase_packaging.PackagingSentenceLevels";
    static components = { ...X2ManyField.components, Field };

    setup() {
        super.setup();
        this.notification = useService("notification");
    }

    get orderedRecords() {
        return [...this.list.records].sort((left, right) => {
            const sequenceDiff = (left.data.sequence || 0) - (right.data.sequence || 0);
            return sequenceDiff || String(left.id).localeCompare(String(right.id));
        });
    }

    get isReadonly() {
        return this.props.readonly || !this.activeActions.write;
    }

    get isTemplateRecord() {
        return this.props.record.resModel === "hosny.purchase.packaging.template";
    }

    get outerPackagingValue() {
        return this.props.record.data[
            this.isTemplateRecord
                ? "main_packaging_type_id"
                : "hosny_outer_packaging_type_id"
        ];
    }

    get baseUomValue() {
        return this.props.record.data[
            this.isTemplateRecord ? "base_uom_id" : "product_uom_id"
        ];
    }

    relationalName(value, fallback) {
        if (Array.isArray(value)) {
            return value[1] || fallback;
        }
        return value?.display_name || value?.name || value?.label || fallback;
    }

    formatNumber(value, maximumFractionDigits = 4) {
        return new Intl.NumberFormat("en-US", {
            minimumFractionDigits: 0,
            maximumFractionDigits,
        }).format(Number(value || 0));
    }

    containerName(index) {
        if (index === 0) {
            return this.relationalName(
                this.outerPackagingValue,
                _t("Main packaging")
            );
        }
        return this.relationalName(
            this.orderedRecords[index - 1]?.data.packaging_type_id,
            _t("Previous packaging")
        );
    }

    isFinal(record) {
        return record.data.content_type === "base_uom";
    }

    canMoveUp(record, index) {
        return !this.isReadonly && !this.isFinal(record) && index > 0;
    }

    canMoveDown(record, index) {
        return (
            !this.isReadonly &&
            !this.isFinal(record) &&
            index < this.orderedRecords.length - 2
        );
    }

    async editRecord(record) {
        if (!this.isReadonly && this.list.editedRecord !== record) {
            await this.list.enterEditMode(record);
        }
    }

    async deleteLevel(record) {
        if (this.isReadonly) {
            return;
        }
        if (this.isFinal(record)) {
            this.notification.add(
                _t("The final content row must remain last. Change its unit or add an internal packaging before it."),
                { type: "warning" }
            );
            return;
        }
        await this.list.delete(record);
    }

    async moveLevel(record, index, direction) {
        if (direction === "up" && !this.canMoveUp(record, index)) {
            return;
        }
        if (direction === "down" && !this.canMoveDown(record, index)) {
            return;
        }
        const canProceed = await this.list.leaveEditMode({ canAbandon: false });
        if (!canProceed) {
            return;
        }
        const records = this.orderedRecords;
        if (direction === "up") {
            const targetId = index > 1 ? records[index - 2].id : null;
            await this.list.resequence(record.id, targetId);
        } else {
            await this.list.resequence(record.id, records[index + 1].id);
        }
    }

    async addInternalLevel() {
        if (this.isReadonly) {
            return;
        }
        if (this.list.records.length >= 10) {
            this.notification.add(_t("You cannot add more than 10 packaging levels."), {
                type: "warning",
            });
            return;
        }
        const canProceed = await this.list.leaveEditMode({ canAbandon: false });
        if (!canProceed) {
            return;
        }
        let terminalIndex = this.orderedRecords.findIndex((record) => this.isFinal(record));
        if (terminalIndex < 0) {
            const productUom = this.baseUomValue;
            await this.list.addNewRecord({
                position: "bottom",
                mode: "readonly",
                context: {
                    default_content_type: "base_uom",
                    default_quantity: 1,
                    default_final_uom_id: productUom?.id || productUom?.resId || false,
                },
            });
            terminalIndex = this.orderedRecords.length - 1;
        }
        const context = {
            default_content_type: "packaging",
            default_quantity: 1,
        };
        if (terminalIndex === 0) {
            await this.list.addNewRecord({ position: "top", mode: "edit", context });
        } else {
            await this.list.addNewRecordAtIndex(terminalIndex - 1, { mode: "edit", context });
        }
    }
}

export const packagingSentenceLevels = {
    ...x2ManyField,
    component: PackagingSentenceLevels,
};

registry
    .category("fields")
    .add("hosny_packaging_sentence_levels", packagingSentenceLevels);

/** Read-only explanation of the values already calculated by the server. */
export class PackagingCalculationSummary extends Component {
    static template = "hosny_purchase_packaging.PackagingCalculationSummary";
    static props = {
        ...standardFieldProps,
        mode: { type: String, optional: true },
    };

    get levels() {
        const list = this.props.record.data[
            this.props.mode === "template"
                ? "line_ids"
                : "hosny_packaging_level_ids"
        ];
        return [...(list?.records || [])].sort((left, right) => {
            const sequenceDiff = (left.data.sequence || 0) - (right.data.sequence || 0);
            return sequenceDiff || String(left.id).localeCompare(String(right.id));
        });
    }

    relationalName(value, fallback = "—") {
        if (Array.isArray(value)) {
            return value[1] || fallback;
        }
        return value?.display_name || value?.name || value?.label || fallback;
    }

    formatNumber(value, maximumFractionDigits = 4) {
        const number = Number(value || 0);
        return new Intl.NumberFormat("en-US", {
            minimumFractionDigits: 0,
            maximumFractionDigits,
        }).format(number);
    }

    get outerName() {
        return this.relationalName(
            this.props.record.data[
                this.props.mode === "template"
                    ? "main_packaging_type_id"
                    : "hosny_outer_packaging_type_id"
            ],
            _t("Main packaging")
        );
    }

    get outerQuantity() {
        return this.props.mode === "template"
            ? 1
            : Number(this.props.record.data.hosny_outer_package_qty || 0);
    }

    get baseUnitName() {
        return this.relationalName(
            this.props.record.data[
                this.props.mode === "template" ? "base_uom_id" : "product_uom_id"
            ],
            _t("Base unit")
        );
    }

    get currencyName() {
        return this.relationalName(this.props.record.data.currency_id, "");
    }

    get factors() {
        return this.levels.map((level) => ({
            quantity: Number(level.data.quantity || 0),
            name: this.relationalName(
                level.data.content_type === "base_uom"
                    ? level.data.final_uom_id
                    : level.data.packaging_type_id
            ),
            isFinal: level.data.content_type === "base_uom",
            baseUomFactor: Number(level.data.base_uom_factor || 0),
        }));
    }

    get rawFinalQuantity() {
        return this.factors.reduce((total, factor) => total * factor.quantity, 1);
    }

    get finalUnitName() {
        return this.factors.find((factor) => factor.isFinal)?.name || this.baseUnitName;
    }

    get showsBaseConversion() {
        return (
            this.finalUnitName !== this.baseUnitName ||
            Math.abs(this.rawFinalQuantity - this.basePerPackage) > 0.0001
        );
    }

    get basePerPackage() {
        if (this.props.mode === "template") {
            if (!this.factors.length) {
                return 0;
            }
            return this.factors.reduce((total, factor) => {
                const conversion = factor.isFinal ? factor.baseUomFactor : 1;
                return total * factor.quantity * conversion;
            }, 1);
        }
        return Number(
            this.props.record.data.hosny_main_package_base_qty || 0
        );
    }

    get totalBaseQuantity() {
        return Number(this.props.record.data.hosny_line_base_qty || 0);
    }

    get inputPrice() {
        return Number(this.props.record.data.hosny_packaging_input_price || 0);
    }

    get equivalentPrice() {
        return Number(this.props.record.data.hosny_packaging_equivalent_unit_price || 0);
    }

    get subtotal() {
        return Number(this.props.record.data.price_subtotal || 0);
    }

    get total() {
        return Number(this.props.record.data.price_total || 0);
    }

    get isPackagePricing() {
        return this.props.record.data.hosny_packaging_price_method === "package";
    }

    get pricingUnitName() {
        return this.isPackagePricing ? this.outerName : this.baseUnitName;
    }

    containerName(index) {
        if (index === 0) {
            return this.outerName;
        }
        return this.relationalName(
            this.levels[index - 1]?.data.packaging_type_id,
            _t("Previous packaging")
        );
    }
}

export const packagingCalculationSummary = {
    component: PackagingCalculationSummary,
    supportedTypes: ["integer"],
    extractProps: ({ options }) => ({ mode: options.mode || "summary" }),
    fieldDependencies: [
        { name: "currency_id", type: "many2one" },
        { name: "product_uom_id", type: "many2one" },
        { name: "hosny_packaging_level_ids", type: "one2many" },
        { name: "hosny_outer_packaging_type_id", type: "many2one" },
        { name: "hosny_outer_package_qty", type: "float" },
        { name: "hosny_main_package_base_qty", type: "float" },
        { name: "hosny_line_base_qty", type: "float" },
        { name: "hosny_packaging_price_method", type: "selection" },
        { name: "hosny_packaging_input_price", type: "monetary" },
        { name: "hosny_packaging_equivalent_unit_price", type: "monetary" },
        { name: "price_subtotal", type: "monetary" },
        { name: "price_total", type: "monetary" },
    ],
};

registry
    .category("fields")
    .add("hosny_packaging_calculation_summary", packagingCalculationSummary);

export const packagingTemplateCalculationSummary = {
    component: PackagingCalculationSummary,
    supportedTypes: ["integer"],
    extractProps: () => ({ mode: "template" }),
    fieldDependencies: [
        { name: "base_uom_id", type: "many2one" },
        { name: "line_ids", type: "one2many" },
        { name: "main_packaging_type_id", type: "many2one" },
        { name: "final_base_qty", type: "float" },
    ],
};

registry.category("fields").add(
    "hosny_packaging_template_calculation_summary",
    packagingTemplateCalculationSummary
);
