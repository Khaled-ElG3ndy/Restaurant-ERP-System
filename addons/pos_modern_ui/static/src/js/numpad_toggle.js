/** @odoo-module **/

import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";

const PRODUCT_NUMPAD_OPEN_CLASS = "pos-modern-numpad-open";
const LEGACY_NUMPAD_OPEN_CLASS = "show-numpad";
const TOGGLE_BUTTON_CLASS = "toggle-numpad-btn";

function getCurrentProductScreen() {
    return (
        document.querySelector(".pos .product-screen:not(.d-none)") ||
        document.querySelector(".pos .product-screen")
    );
}

function clearLayoutInlineStyles(root) {
    if (!root) {
        return;
    }

    const layoutProperties = [
        "display",
        "width",
        "height",
        "min-width",
        "max-width",
        "min-height",
        "max-height",
        "flex",
        "flex-basis",
        "flex-grow",
        "flex-shrink",
        "grid-template-columns",
        "grid-template-rows",
        "gap",
        "padding",
        "margin",
    ];

    root.querySelectorAll(".numpad, .pads, .subpads, .rightpane, .leftpane").forEach((el) => {
        for (const property of layoutProperties) {
            el.style.removeProperty(property);
        }
    });
}

function cleanupProductNumpadState() {
    const posRoot = document.querySelector(".pos");
    if (posRoot) {
        posRoot.classList.remove(LEGACY_NUMPAD_OPEN_CLASS);
    }
    document
        .querySelectorAll(".pos .product-screen")
        .forEach((screen) => screen.classList.remove(PRODUCT_NUMPAD_OPEN_CLASS));
    document
        .querySelectorAll(`.pos .product-screen .${TOGGLE_BUTTON_CLASS}.active`)
        .forEach((button) => button.classList.remove("active"));
}

patch(ProductScreen.prototype, {
    setup() {
        super.setup();

        onMounted(() => {
            cleanupProductNumpadState();

            const productScreen = getCurrentProductScreen();
            if (!productScreen) return;

            const actionpad = productScreen.querySelector(".actionpad");
            if (!actionpad) return;

            const existingButton = actionpad.querySelector(`.${TOGGLE_BUTTON_CLASS}`);
            if (existingButton) {
                return;
            }

            const btn = document.createElement("button");
            btn.className = `button btn btn-light ${TOGGLE_BUTTON_CLASS}`;
            btn.innerHTML = `<i class="fa fa-calculator me-1"></i><span>Numpad</span>`;

            btn.addEventListener("click", () => {
                const isOpen = productScreen.classList.toggle(PRODUCT_NUMPAD_OPEN_CLASS);
                btn.classList.toggle("active", isOpen);
            });

            actionpad.prepend(btn);
        });

        onWillUnmount(() => {
            const productScreen = getCurrentProductScreen();
            cleanupProductNumpadState();
            clearLayoutInlineStyles(productScreen);
        });
    },
});

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);

        onMounted(() => {
            cleanupProductNumpadState();
            clearLayoutInlineStyles(document.querySelector(".pos .payment-screen"));
        });
    },
});

patch(PosStore.prototype, {
    navigate(routeName, routeParams = {}) {
        if (routeName !== "ProductScreen") {
            cleanupProductNumpadState();
        }

        const result = super.navigate ? super.navigate(...arguments) : this.showScreen(routeName, routeParams);

        if (routeName === "PaymentScreen") {
            setTimeout(() => {
                cleanupProductNumpadState();
                clearLayoutInlineStyles(document.querySelector(".pos .payment-screen"));
            }, 0);
        }

        return result;
    },
});
