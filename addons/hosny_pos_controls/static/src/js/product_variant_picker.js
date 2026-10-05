/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { normalize } from "@web/core/l10n/utils";
import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { ProductProduct } from "@point_of_sale/app/models/product_product";
import { ProductTemplate } from "@point_of_sale/app/models/product_template";

/** Below this, scanning the grid is faster than typing. */
const SEARCH_FROM = 10;

// Product pictures are served at 512px wherever the POS renders one.
patch(ProductProduct.prototype, {
    getImageUrl() {
        return `/web/image?model=product.product&field=image_512&id=${this.id}&unique=${this.write_date}`;
    },
});

patch(ProductTemplate.prototype, {
    getImageUrl() {
        return `/web/image?model=product.template&field=image_512&id=${this.id}&unique=${this.write_date}`;
    },
});

/**
 * Price Odoo puts on the order line for a variant.
 *
 * Same call as `PosOrderline.canBeMergedWith`, i.e. the POS port of
 * `product.pricelist._get_product_price`: pricelist rules, variant price extras
 * (already inside `lst_price`) and the tax-inclusive prices this POS stores all
 * come from Odoo. Nothing about pricing is reimplemented here.
 */
function variantPrice(pos, variant) {
    const pricelist = pos.getOrder()?.pricelist_id || pos.config.pricelist_id || false;
    return variant.getPrice(pricelist, 1, 0, false, variant);
}

/** Name of the variant alone, e.g. "كبير" rather than "أرز صيادية (كبير)". */
function variantName(variant, productTemplate) {
    const values = variant.product_template_variant_value_ids || [];
    const label = values
        .map((value) => value.name)
        .filter(Boolean)
        .join(" / ");

    if (label) {
        return label;
    }

    return (variant.display_name || variant.name || "")
        .replace(productTemplate?.name || "", "")
        .replace(/[()[\]]/g, "")
        .trim();
}

/** True when the variant holds one value per attribute line. */
function isCompleteCombination(attributeLines, variant) {
    const valueIds = new Set(
        (variant.product_template_variant_value_ids || []).map((value) => value.id)
    );

    return attributeLines.every((line) =>
        line.product_template_value_ids.some((value) => valueIds.has(value.id))
    );
}

/** Attribute values are loaded in their configured order: sell them that way. */
function inAttributeOrder(attributeLines, variants) {
    const ranks = new Map();
    for (const line of attributeLines) {
        for (const value of line.product_template_value_ids) {
            ranks.set(value.id, ranks.size);
        }
    }
    const rankOf = (variant) =>
        (variant.product_template_variant_value_ids || []).map((value) => ranks.get(value.id) ?? 0);

    return [...variants].sort((left, right) => {
        const leftRanks = rankOf(left);
        const rightRanks = rankOf(right);
        for (let index = 0; index < Math.max(leftRanks.length, rightRanks.length); index++) {
            const difference = (leftRanks[index] ?? -1) - (rightRanks[index] ?? -1);
            if (difference) {
                return difference;
            }
        }
        return left.id - right.id;
    });
}

patch(ProductTemplate.prototype, {
    /**
     * Variants a cashier can pick in one tap, or an empty list when Odoo has to
     * run a configurator of its own.
     *
     * The quick picker only claims products whose every attribute line creates
     * variants up front and asks nothing else, so picking a value is the same as
     * picking an existing `product.product`. Everything else — `no_variant` and
     * `dynamic` attributes, custom values, combos, incomplete combinations —
     * stays on the native flow, which knows how to ask for the rest.
     *
     * Cached on the record: it describes how the product is set up and never
     * depends on session state, and `onUpdate` drops it when the record changes.
     */
    get hosnyQuickVariants() {
        return this.cacheValues("hosnyQuickVariants", () => {
            const attributeLines = this.attribute_line_ids || [];
            if (!attributeLines.length || this.isCombo()) {
                return [];
            }

            const isPlainChoice = attributeLines.every(
                (line) =>
                    line.attribute_id?.create_variant === "always" &&
                    !line.product_template_value_ids.some((value) => value.is_custom)
            );
            if (!isPlainChoice) {
                return [];
            }

            const variants = this.product_variant_ids || [];
            if (
                variants.length < 2 ||
                !variants.every((variant) => isCompleteCombination(attributeLines, variant))
            ) {
                return [];
            }

            return inAttributeOrder(attributeLines, variants);
        });
    },
});

/**
 * Variant picker: the product card is the first tap, a variant tile the second.
 */
export class VariantQuickPickPopup extends Component {
    static template = "hosny_pos_controls.VariantQuickPickPopup";
    static components = { Dialog };
    static props = {
        productTemplate: Object,
        selectVariant: Function,
        close: Function,
    };

    setup() {
        this.pos = usePos();
        this.state = useState({ search: "", adding: false });
        // Priced once, when the picker opens: it closes on the first tap, so
        // neither the pricelist nor the order can move underneath it.
        this.options = this.props.productTemplate.hosnyQuickVariants.map((variant) => {
            const name = variantName(variant, this.props.productTemplate);
            return {
                id: variant.id,
                variant: variant,
                name: name,
                searchKey: normalize(name),
                price: this.env.utils.formatCurrency(variantPrice(this.pos, variant)),
            };
        });
    }

    get promptLabel() {
        return (this.props.productTemplate.attribute_line_ids || [])
            .map((line) => line.attribute_id?.name)
            .filter(Boolean)
            .join(" · ");
    }

    get showSearch() {
        return this.options.length >= SEARCH_FROM;
    }

    get visibleOptions() {
        const term = normalize(this.state.search.trim());
        if (!term) {
            return this.options;
        }
        return this.options.filter((option) => option.searchKey.includes(term));
    }

    async selectOption(option) {
        // A second tap landing before the first add resolves must not duplicate
        // the order line.
        if (this.state.adding) {
            return;
        }
        this.state.adding = true;
        // Close first: the line is added right after, so anything the native flow
        // still needs to ask (lots, optional products) opens over the product
        // screen instead of over a picker that is already done.
        this.props.close();
        await this.props.selectVariant(option.variant);
    }
}

patch(ProductCard.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = usePos();
    },

    /**
     * The amount and the currency come back apart because the card sets them
     * in different sizes — the number leads, the symbol trails it small and
     * quiet. `formatCurrency(value, false)` is the same formatter Odoo uses,
     * only without the symbol appended.
     */
    hosnyPriceParts(value) {
        return {
            amount: this.env.utils.formatCurrency(value, false),
            currency: this.pos.currency?.symbol || "",
        };
    },

    /**
     * The card price: the price of the variant Odoo would add, or the cheapest
     * variant price when a tap opens the picker instead. `null` renders no
     * price line at all.
     */
    get hosnyCardPrice() {
        const product = this.props.product;
        if (!product) {
            return null;
        }

        // Combo tiles carry their own `comboExtraPrice` badge and are handed a
        // variant rather than a template: keep showing the plain product price.
        if (this.props.isComboPopup) {
            const price = product.lst_price || product.list_price || 0;
            return price ? this.hosnyPriceParts(price) : null;
        }

        // A product sold in options is priced from its cheapest one, and says
        // so. The badge used to add "يبدأ من" only when the options cost
        // DIFFERENT amounts, which left a card that opens a picker looking
        // exactly like a card that adds a line — the cashier could not tell
        // the tap would ask a question. Khaled asked on 2026-09-14 for the
        // lead on every product that has options; equal-priced options get it
        // too, and there it reads as "this is what any of them costs".
        const quick = product.hosnyQuickVariants || [];
        if (quick.length) {
            const prices = quick.map((variant) => variantPrice(this.pos, variant));
            return {
                ...this.hosnyPriceParts(Math.min(...prices)),
                isFrom: true,
            };
        }

        // Cards carry a template. This branch is everything the quick picker
        // cannot claim — a `dynamic` or `no_variant` attribute, a custom value,
        // an incomplete combination — and it used to price the card off
        // `product_variant_ids[0]`, whichever that happened to be. On a
        // product whose variants cost different amounts that is simply a wrong
        // price on the card, and silently so. Price it off the cheapest
        // variant, the same rule as above.
        const variants = product.product_variant_ids || [];
        if (!variants.length) {
            return null;
        }
        const prices = variants.map((variant) => variantPrice(this.pos, variant));
        return {
            ...this.hosnyPriceParts(Math.min(...prices)),
            isFrom: variants.length > 1,
        };
    },
});

patch(ProductScreen.prototype, {
    async addProductToOrder(product) {
        if (product.hosnyQuickVariants?.length && !this.hosnyScannedVariant(product)) {
            this.hosnyOpenVariantPicker(product);
            return;
        }

        return super.addProductToOrder(...arguments);
    },

    hosnyOpenVariantPicker(productTemplate) {
        // A double tap on the card must not stack two pickers.
        if (this.hosnyVariantPickerOpen) {
            return;
        }
        this.hosnyVariantPickerOpen = true;

        this.dialog.add(
            VariantQuickPickPopup,
            {
                productTemplate: productTemplate,
                selectVariant: (variant) => this.hosnyAddVariant(productTemplate, variant),
            },
            {
                onClose: () => {
                    this.hosnyVariantPickerOpen = false;
                },
            }
        );
    },

    /**
     * A barcode search narrowed down to a single variant needs no picker: the
     * native flow adds that variant straight away.
     */
    hosnyScannedVariant(product) {
        const barcode = this.searchWord;
        if (!barcode) {
            return false;
        }

        const matches = product.product_variant_ids.filter(
            (variant) => variant.barcode && variant.barcode.includes(barcode)
        );
        return matches.length === 1 && matches[0];
    },

    /**
     * `presetVariant` is the supported way to hand Odoo a chosen variant: it
     * narrows the configurator down to that combination and then builds the line
     * natively — attribute values, price extras, taxes, lots, merging, optional
     * products. No order line is created here.
     */
    async hosnyAddVariant(productTemplate, variant) {
        await this.pos.addLineToCurrentOrder(
            { product_tmpl_id: productTemplate },
            { presetVariant: variant }
        );
        this.showOptionalProductPopupIfNeeded(productTemplate);
    },
});
