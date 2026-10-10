/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { Order as PosOrder, Orderline as PosOrderline } from "@point_of_sale/app/store/models";
import { OrderDisplay } from "@point_of_sale/app/components/order_display/order_display";

function getGetterDescriptor(proto, name) {
    let cursor = proto;
    while (cursor) {
        const descriptor = Object.getOwnPropertyDescriptor(cursor, name);
        if (descriptor) {
            return descriptor;
        }
        cursor = Object.getPrototypeOf(cursor);
    }
    return undefined;
}

const originalDisplayPrice = getGetterDescriptor(PosOrderline.prototype, "displayPrice")?.get;
const originalDisplayPriceNoDiscount =
    getGetterDescriptor(PosOrderline.prototype, "displayPriceNoDiscount")?.get;
const originalComboSortedLines = getGetterDescriptor(OrderDisplay.prototype, "comboSortedLines")?.get;

function getMealComponentLines(pos, productTemplate) {
    const lines = productTemplate?.meal_component_line_ids?.length
        ? productTemplate.meal_component_line_ids
        : pos.models["product.meal.component.line"]
              ?.getAll()
              ?.filter((line) => line.meal_product_tmpl_id?.id === productTemplate?.id) || [];
    return [...lines].sort((a, b) => (a.sequence || 0) - (b.sequence || 0) || a.id - b.id);
}

function getAdditionalFinalProductLines(pos, productTemplate) {
    const lines = productTemplate?.additional_final_product_line_ids?.length
        ? productTemplate.additional_final_product_line_ids
        : pos.models["product.additional.final.line"]
              ?.getAll()
              ?.filter((line) => line.parent_product_tmpl_id?.id === productTemplate?.id) || [];
    return [...lines].sort((a, b) => (a.sequence || 0) - (b.sequence || 0) || a.id - b.id);
}

function getAdditionalFinalChildren(order, parentLine) {
    return (order?.lines || []).filter(
        (line) =>
            line.is_additional_final_product &&
            line.additional_final_parent_uuid === parentLine.uuid
    );
}

function getAdditionalFinalDisplayAmount(order, parentLine, noDiscount = false) {
    return getAdditionalFinalChildren(order, parentLine).reduce((total, line) => {
        return total + (noDiscount ? line.displayPriceNoDiscount : line.displayPrice);
    }, 0);
}

function getComponentDisplayMode(parentLine) {
    return parentLine.product_id?.product_tmpl_id?.component_display_mode || "pos_receipt";
}

/** الكمية التي وصلت الأقسام من هذا السطر (0 لو لم يُرسل). */
function getSentQuantity(line) {
    const sent = line?.order_id?.last_order_preparation_change?.lines?.[line.preparationKey];
    return Math.max(0, Number(sent?.quantity) || 0);
}

// صحيح أثناء إضافة صنف من الشاشة فقط؛ النقل والدمج بين الطاولات لا يمرّان من هنا.
let addingProduct = false;

patch(PosStore.prototype, {
    /**
     * ما أُرسل للأقسام لا يتكرر (طلب المسؤول 2026-10-09): لو طلب العميل نفس
     * الصنف بعد «إرسال الطلب» تظهر الإضافة في سطر جديد، والسطر المرسل يبقى
     * كما وصل المطبخ. قبل الإرسال يبقى الدمج كما هو.
     */
    tryMergeOrderline() {
        addingProduct = true;
        try {
            return super.tryMergeOrderline(...arguments);
        } finally {
            addingProduct = false;
        }
    },

    async addLineToOrder(vals, order, opts = {}, configure = true) {
        const line = await super.addLineToOrder(...arguments);
        if (!line || opts.mealComponentCreation || opts.additionalFinalProductCreation) {
            return line;
        }

        // نفس الوجبة مرة ثانية ← تزيد كمية سطرها (2026-10-09). أودو لا يدمجها
        // (سطر الوجبة له مكوّنات = combo)، فنزيد كمية الوجبة الموجودة —
        // setQuantity يضاعف مكوّناتها والمنتجات النهائية الإضافية — ونحذف الجديد
        // قبل أن تُبنى له مكوّنات. نفس شروط أودو للدمج: لا سعر صريح ولا merge:false.
        const target =
            opts.merge !== false && !("price_unit" in (vals || {}))
                ? this._hosnyMergeableMealLine(order, line)
                : null;
        if (target) {
            const newQty = target.getQuantity() + line.getQuantity();
            // نختار السطر الباقي قبل حذف المكرر، فلا يبقى المحذوف هو المختار
            this.selectOrderLine(order, target);
            line.delete();
            target.setQuantity(newQty, Boolean(target.combo_line_ids?.length));
            target.setHasChange?.(true);
            order.triggerRecomputeAllPrices?.();
            return target;
        }

        const productTemplate = line.product_id?.product_tmpl_id;
        if (productTemplate?.is_meal_combo) {
            this._createMealComponentLines(order, line);
        }

        await this._createAdditionalFinalProductLines(order, line);
        this.selectOrderLine(order, line);
        return line;
    },

    /** سطر وجبة (أو صنف بمنتجات نهائية إضافية) مطابق للسطر الجديد في الطلب. */
    _hosnyMergeableMealLine(order, line) {
        const template = line.product_id?.product_tmpl_id;
        const isMealProduct =
            template?.is_meal_combo || getAdditionalFinalProductLines(this, template).length > 0;
        if (!isMealProduct || !order || order.finalized || line.getQuantity() <= 0) {
            return null;
        }
        const round = (value) => this.currency?.round?.(value || 0) ?? value;
        return (
            order.lines.find(
                (other) =>
                    other !== line &&
                    other.uuid !== line.uuid &&
                    other.product_id?.id === line.product_id?.id &&
                    !other.is_meal_component &&
                    !other.is_additional_final_product &&
                    !other.combo_parent_id &&
                    !other.refunded_orderline_id &&
                    !line.refunded_orderline_id &&
                    other.getQuantity() > 0 &&
                    getSentQuantity(other) === 0 &&
                    (other.getNote?.() || "") === (line.getNote?.() || "") &&
                    (other.getCustomerNote?.() || "") === (line.getCustomerNote?.() || "") &&
                    (other.getDiscount?.() || 0) === (line.getDiscount?.() || 0) &&
                    other.price_type === line.price_type &&
                    round(other.price_unit) === round(line.price_unit) &&
                    (other.full_product_name || "") === (line.full_product_name || "")
            ) || null
        );
    },

    _createMealComponentLines(order, parentLine) {
        const productTemplate = parentLine.product_id?.product_tmpl_id;
        const componentLines = getMealComponentLines(this, productTemplate);
        const displayMode = getComponentDisplayMode(parentLine);

        parentLine.update({
            is_meal_parent: true,
            is_meal_component: false,
            meal_parent_uuid: false,
            meal_component_product_id: false,
            meal_component_display_mode: displayMode,
        });

        if (!componentLines.length) {
            return;
        }

        const children = [];
        for (const component of componentLines) {
            const product = component.product_id;
            if (!product) {
                continue;
            }
            const childLine = this.models["pos.order.line"].create({
                order_id: order,
                product_id: product,
                tax_ids: [],
                price_unit: 0,
                price_type: "manual",
                discount: 0,
                qty: (component.quantity || 1) * parentLine.getQuantity(),
                full_product_name: product.display_name || product.name,
                is_meal_parent: false,
                is_meal_component: true,
                meal_parent_uuid: parentLine.uuid,
                meal_component_product_id: product,
                meal_component_display_mode: displayMode,
            });
            childLine.setUnitPrice(0);
            childLine.setQuantity((component.quantity || 1) * parentLine.getQuantity(), true);
            childLine.setFullProductName?.();
            children.push(childLine);
        }

        if (children.length) {
            parentLine.update({ combo_line_ids: [["link", ...children]] });
            parentLine.setHasChange(true);
            order.triggerRecomputeAllPrices();
        }
    },

    async _createAdditionalFinalProductLines(order, parentLine) {
        const productTemplate = parentLine.product_id?.product_tmpl_id;
        const additionalLines = getAdditionalFinalProductLines(this, productTemplate);
        if (!additionalLines.length) {
            return;
        }

        const createdChildren = [];
        for (const additional of additionalLines) {
            const product = additional.product_id;
            if (!product?.product_tmpl_id) {
                continue;
            }
            const childLine = await this.addLineToOrder(
                {
                    product_tmpl_id: product.product_tmpl_id,
                    product_id: product,
                    qty: (additional.quantity || 1) * parentLine.getQuantity(),
                    price_unit: additional.price_unit || 0,
                    discount: additional.discount || 0,
                    price_type: "manual",
                    note: additional.note || "",
                    is_additional_final_parent: false,
                    is_additional_final_product: true,
                    additional_final_parent_uuid: parentLine.uuid,
                    additional_final_line_id: additional,
                },
                order,
                { additionalFinalProductCreation: true },
                false
            );
            if (!childLine) {
                continue;
            }
            childLine.update({
                is_additional_final_parent: false,
                is_additional_final_product: true,
                additional_final_parent_uuid: parentLine.uuid,
                additional_final_line_id: additional,
            });
            childLine.setUnitPrice(additional.price_unit || 0);
            childLine.setQuantity((additional.quantity || 1) * parentLine.getQuantity(), true);
            childLine.setDiscount(additional.discount || 0);
            childLine.setFullProductName?.();
            createdChildren.push(childLine);
        }

        if (createdChildren.length) {
            parentLine.update({
                is_additional_final_parent: true,
                is_additional_final_product: false,
                additional_final_parent_uuid: false,
                additional_final_line_id: false,
            });
            parentLine.setHasChange(true);
            order.triggerRecomputeAllPrices();
        }
    },
});

patch(PosOrderline.prototype, {
    get displayPrice() {
        if (this.is_meal_parent) {
            return this.config.iface_tax_included === "total" ? this.priceIncl : this.priceExcl;
        }
        const displayPrice = originalDisplayPrice.call(this);
        if (this.is_additional_final_parent) {
            return displayPrice + getAdditionalFinalDisplayAmount(this.order_id, this);
        }
        return displayPrice;
    },

    get displayPriceNoDiscount() {
        if (this.is_meal_parent) {
            return this.config.iface_tax_included === "total"
                ? this.priceInclNoDiscount
                : this.priceExclNoDiscount;
        }
        const displayPrice = originalDisplayPriceNoDiscount.call(this);
        if (this.is_additional_final_parent) {
            return displayPrice + getAdditionalFinalDisplayAmount(this.order_id, this, true);
        }
        return displayPrice;
    },

    getDisplayClasses() {
        return {
            ...super.getDisplayClasses(...arguments),
            "hosny-meal-parent": this.is_meal_parent,
            "hosny-meal-component": this.is_meal_component,
            "hosny-additional-final-parent": this.is_additional_final_parent,
            "hosny-additional-final-product": this.is_additional_final_product,
            "d-none": this.is_meal_component || this.is_additional_final_product,
        };
    },

    canBeMergedWith(orderline) {
        if (
            this.is_meal_parent ||
            this.is_meal_component ||
            this.is_additional_final_parent ||
            this.is_additional_final_product ||
            orderline.is_meal_parent ||
            orderline.is_meal_component ||
            orderline.is_additional_final_parent ||
            orderline.is_additional_final_product
        ) {
            return false;
        }
        // this هو السطر الموجود في الطلب، و orderline الضغطة الجديدة
        if (addingProduct && getSentQuantity(this) > 0) {
            return false;
        }
        return super.canBeMergedWith(...arguments);
    },

    setQuantity(quantity, keepPrice) {
        const result = super.setQuantity(...arguments);
        if (result !== true || !this.is_additional_final_parent) {
            return result;
        }
        for (const childLine of getAdditionalFinalChildren(this.order_id, this)) {
            const baseQty = childLine.additional_final_line_id?.quantity || 1;
            childLine.setQuantity(baseQty * this.getQuantity(), true);
        }
        return result;
    },
});

patch(PosOrder.prototype, {
    /**
     * مكوّنات الوجبة مربوطة بالوجبة كأسطر combo لكن بلا combo_item_id، وأودو
     * يقرأ cLine.combo_item_id.combo_id عند إعادة تسعير الكومبو (setPricelist،
     * مثلاً عند اختيار العميل في الدفع) فينهار بـ «reading 'combo_id'»
     * (2026-10-09). نمرّر له أسطر الكومبو الحقيقية فقط؛ الوجبة بلا كومبو
     * حقيقي ترجع قوائم فارغة.
     */
    getFreeAndExtraChildLines(pLine) {
        const children = pLine?.combo_line_ids || [];
        if (children.every((child) => child.combo_item_id)) {
            return super.getFreeAndExtraChildLines(...arguments);
        }
        const realItems = children.filter((child) => child.combo_item_id);
        if (!realItems.length) {
            return { childLineFree: [], childLineExtra: [] };
        }
        const view = Object.create(pLine, { combo_line_ids: { value: realItems } });
        return super.getFreeAndExtraChildLines(view);
    },

    removeOrderline(line) {
        if (line?.is_additional_final_parent) {
            for (const childLine of getAdditionalFinalChildren(this, line)) {
                if (childLine.refunded_orderline_id?.uuid in this.uiState.lineToRefund) {
                    delete this.uiState.lineToRefund[childLine.refunded_orderline_id.uuid];
                }
                if (this.assertEditable()) {
                    childLine.delete();
                }
            }
        }
        return super.removeOrderline(...arguments);
    },

    getLinesToCompute() {
        return this.lines.filter(
            (line) =>
                line.price_type === "original" &&
                (!line.combo_line_ids?.length || line.is_meal_parent) &&
                !line.combo_parent_id
        );
    },
});

patch(OrderDisplay.prototype, {
    get comboSortedLines() {
        const lines = originalComboSortedLines.call(this);
        return lines.filter((line) => !line.is_meal_component && !line.is_additional_final_product);
    },
});
