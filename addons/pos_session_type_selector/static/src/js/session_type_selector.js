/** @odoo-module **/

/**
 * POS Session Type Selector
 * =========================
 * Shows a full-screen Arabic modal overlay immediately after the POS loads,
 * letting the cashier choose سفري (Takeout → ProductScreen)
 *                         or  محلي (Dine-in  → FloorScreen).
 *
 * Strategy
 * --------
 * 1. Patch PosStore.prototype.setup  → set `this.showOrderSelector = true`
 *    BEFORE calling super.setup() so the flag is reactive from the first render.
 * 2. Patch PosStore.prototype        → add `selectOrderType(type)` that clears
 *    the flag and navigates to the correct screen.
 * 3. Register OrderTypeSelector in Chrome.components so the XML template can
 *    reference it.
 * 4. The XML file extends point_of_sale.Chrome to render <OrderTypeSelector />
 *    when `pos.isReady and pos.showOrderSelector`.
 *
 * Why NOT patch ProductScreen or FloorScreen?
 * -------------------------------------------
 * The initial screen depends on the POS config (restaurant vs. standard).
 * Patching a specific screen would miss the other. PosStore is always present.
 */

import { patch }    from "@web/core/utils/patch";
import { Component } from "@odoo/owl";
import { Chrome }    from "@point_of_sale/app/pos_app";
import { PosStore }  from "@point_of_sale/app/store/pos_store";

function asArray(value) {
    if (!value) {
        return [];
    }
    if (Array.isArray(value)) {
        return Array.from(value);
    }
    if (typeof value.getAll === "function") {
        return value.getAll();
    }
    if (typeof value.values === "function") {
        return Array.from(value.values());
    }
    if (typeof value[Symbol.iterator] === "function") {
        return Array.from(value);
    }
    return Object.values(value);
}

function getRecordId(record) {
    return record?.id || record || null;
}

function getConfiguredFloors(pos) {
    const floors = pos?.config?.floor_ids || pos?.floors || pos?.models?.["restaurant.floor"]?.getAll?.() || [];
    const configId = pos?.config?.id;

    return asArray(floors).filter((floor) => {
        if (!floor || floor.active === false) {
            return false;
        }
        const floorConfigIds = asArray(floor.pos_config_ids).map(getRecordId).filter(Boolean);
        return !configId || !floorConfigIds.length || floorConfigIds.includes(configId);
    });
}

function navigateTo(pos, screenName, params) {
    if (typeof pos.navigate === "function") {
        return pos.navigate(screenName, params);
    }
    return pos.showScreen?.(screenName, params);
}

// ─────────────────────────────────────────────────────────────────────────────
// OrderTypeSelector – the overlay component
// ─────────────────────────────────────────────────────────────────────────────

export class OrderTypeSelector extends Component {
    static template = "pos_session_type_selector.OrderTypeSelector";

    /**
     * Props:
     *   pos {PosStore} – reactive store injected from the Chrome template
     */
    static props = {
        pos: { type: Object },
    };

    /**
     * Called when the user taps one of the two cards.
     * Delegates to PosStore so all navigation logic stays in one place.
     *
     * @param {string} type  "takeout" | "dine-in"
     */
    selectType(type) {
        this.props.pos.selectOrderType(type);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// PosStore patch
// ─────────────────────────────────────────────────────────────────────────────

patch(PosStore.prototype, {

    /**
     * Override setup to inject `showOrderSelector` into the reactive store
     * BEFORE super.setup() runs.  Because PosStore extends OWL Reactive, every
     * property set on `this` is automatically observed by the template engine.
     *
     * Setting the flag *before* super() means that when `isReady` flips to true
     * at the end of super.setup(), the Chrome template immediately renders the
     * overlay — no extra re-render, no flash of the underlying screen.
     */
    async setup(...args) {
        // ➊ Declare reactive flag (false until POS is ready)
        this.showOrderSelector = false;

        // ➋ Run the original POS initialisation
        //    At the very end of super.setup(), isReady is set to true.
        await super.setup(...args);

        // ➌ Show the overlay now that the store is fully initialised
        this.showOrderSelector = true;
    },

    /**
     * Called by the overlay component when the cashier picks a type.
     *
     * Navigation rules
     * ----------------
     * "takeout"  → ProductScreen  (always)
     * "dine-in"  → FloorScreen    (only when pos_restaurant is active AND floors
     *                              exist); falls back to ProductScreen otherwise.
     *
     * @param {string} type  "takeout" | "dine-in"
     */
    selectOrderType(type) {
        // Hide the overlay first so it does not re-appear if the component
        // re-renders between hiding and navigating.
        this.showOrderSelector = false;

        const restaurantEnabled =
            !!this.config?.module_pos_restaurant;

        let hasFloors = false;
        try {
            hasFloors = restaurantEnabled && getConfiguredFloors(this).length > 0;
        } catch (error) {
            console.warn("[POS Selector] Could not resolve configured floors.", error);
        }

        if (type === "dine-in" && hasFloors) {
            navigateTo(this, "FloorScreen");
        } else {
            if (type === "dine-in" && !hasFloors) {
                console.warn(
                    "[POS Selector] محلي selected but no floors are configured." +
                    " Falling back to ProductScreen."
                );
            }
            navigateTo(this, "ProductScreen");
        }
    },
});

// ─────────────────────────────────────────────────────────────────────────────
// Register OrderTypeSelector in Chrome so the template can use the tag
// ─────────────────────────────────────────────────────────────────────────────

Chrome.components = Object.assign(Chrome.components || {}, {
    OrderTypeSelector,
});
