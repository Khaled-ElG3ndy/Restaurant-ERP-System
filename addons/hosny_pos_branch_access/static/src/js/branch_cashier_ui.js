/** @odoo-module **/

import { session } from "@web/session";

if (session.hosny_is_branch_cashier) {
    document.documentElement.classList.add("o_hosny_branch_cashier_ui");

    const styleId = "hosny-branch-cashier-navbar-spacing";
    if (!document.getElementById(styleId)) {
        const style = document.createElement("style");
        style.id = styleId;
        style.textContent = `
            html.o_hosny_branch_cashier_ui .o_main_navbar {
                padding-right: clamp(20px, 1.8vw, 32px) !important;
            }

            html.o_hosny_branch_cashier_ui .o_main_navbar > .o_menu_brand {
                margin-right: clamp(20px, 1.8vw, 32px) !important;
                margin-left: 0 !important;
            }
        `;
        document.head.appendChild(style);
    }
}
