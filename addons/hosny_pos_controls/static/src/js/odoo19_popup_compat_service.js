/** @odoo-module **/

import { registry } from "@web/core/registry";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

registry.category("services").add(
    "popup",
    {
        dependencies: ["dialog"],
        start(_env, { dialog }) {
            return {
                async add(component, props = {}, options = {}) {
                    const result = await makeAwaitable(dialog, component, props, options);
                    if (result && typeof result === "object" && "confirmed" in result) {
                        return result;
                    }
                    return { confirmed: result !== undefined, payload: result };
                },
            };
        },
    },
    { force: true }
);
