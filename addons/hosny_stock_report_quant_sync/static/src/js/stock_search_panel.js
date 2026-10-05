/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { SearchPanel } from "@web/search/search_panel/search_panel";

const HOSNY_SEARCH_PANEL_CLASS = "o_hosny_product_category_search_panel";

function isProductCategorySection(section) {
    return section?.type === "category" && section.fieldName === "categ_id";
}

function getRootCategoryId(section) {
    if (!section?.values) {
        return false;
    }
    for (const [valueId, value] of section.values) {
        if (valueId !== false && value && !value.parentId) {
            return valueId;
        }
    }
    return false;
}

function isHosnyProductCategorySection(searchModel, section) {
    const className = searchModel.searchPanelInfo?.className || "";
    return (
        isProductCategorySection(section) &&
        className.includes(HOSNY_SEARCH_PANEL_CLASS)
    );
}

patch(SearchPanel.prototype, {
    getHosnyCategoryItemClass(isChildList, valueId) {
        const baseClass = isChildList ? (this.env.isSmall ? "" : "o_treeEntry") : "ps-0";
        const className = this.env.searchModel.searchPanelInfo?.className || "";
        if (className.includes(HOSNY_SEARCH_PANEL_CLASS) && valueId === false) {
            return `${baseClass} d-none`;
        }
        return baseClass;
    },

    updateActiveValues() {
        super.updateActiveValues(...arguments);
        for (const section of this.sections) {
            if (!isHosnyProductCategorySection(this.env.searchModel, section)) {
                continue;
            }
            const rootCategoryId = getRootCategoryId(section);
            if (!section.activeValueId && rootCategoryId) {
                this.state.active[section.id] = rootCategoryId;
            }
        }
    },

    async toggleCategory(category, value) {
        if (!isHosnyProductCategorySection(this.env.searchModel, category)) {
            return super.toggleCategory(category, value);
        }

        const rootCategoryId = getRootCategoryId(category);
        if (value.id !== rootCategoryId) {
            return super.toggleCategory(category, value);
        }

        if (value.childrenIds.length) {
            this.state.expanded[category.id][value.id] = true;
        }
        this.state.active[category.id] = value.id;
        if (category.activeValueId) {
            this.env.searchModel.toggleCategoryValue(category.id, false);
        }
    },
});
