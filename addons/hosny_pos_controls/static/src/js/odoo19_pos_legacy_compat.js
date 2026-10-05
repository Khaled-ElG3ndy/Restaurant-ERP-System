/** @odoo-module ignore **/

odoo.define(
    "@point_of_sale/app/store/pos_hook",
    ["@point_of_sale/app/hooks/pos_hook"],
    function (require) {
        "use strict";
        return require("@point_of_sale/app/hooks/pos_hook");
    }
);

odoo.define(
    "@point_of_sale/app/store/pos_store",
    ["@point_of_sale/app/services/pos_store"],
    function (require) {
        "use strict";
        return require("@point_of_sale/app/services/pos_store");
    }
);

odoo.define(
    "@point_of_sale/app/navbar/navbar",
    ["@point_of_sale/app/components/navbar/navbar"],
    function (require) {
        "use strict";
        return require("@point_of_sale/app/components/navbar/navbar");
    }
);

odoo.define(
    "@point_of_sale/app/screens/product_screen/product_list/product_list",
    ["@point_of_sale/app/screens/product_screen/product_screen"],
    function (require) {
        "use strict";
        const { ProductScreen } = require("@point_of_sale/app/screens/product_screen/product_screen");
        return { ProductsWidget: ProductScreen };
    }
);

odoo.define(
    "@point_of_sale/app/generic_components/inputs/input/input",
    ["@point_of_sale/app/components/inputs/input/input"],
    function (require) {
        "use strict";
        return require("@point_of_sale/app/components/inputs/input/input");
    }
);

odoo.define(
    "@point_of_sale/app/hooks/hooks",
    ["@web/core/utils/hooks"],
    function (require) {
        "use strict";
        return require("@web/core/utils/hooks");
    }
);

odoo.define(
    "@point_of_sale/app/utils/input_popups/number_popup",
    ["@point_of_sale/app/components/popups/number_popup/number_popup"],
    function (require) {
        "use strict";
        return require("@point_of_sale/app/components/popups/number_popup/number_popup");
    }
);

odoo.define(
    "@point_of_sale/app/errors/popups/error_popup",
    ["@web/core/confirmation_dialog/confirmation_dialog"],
    function (require) {
        "use strict";
        const { AlertDialog } = require("@web/core/confirmation_dialog/confirmation_dialog");
        return { ErrorPopup: AlertDialog };
    }
);

odoo.define(
    "@point_of_sale/app/popup/abstract_awaitable_popup",
    ["@odoo/owl"],
    function (require) {
        "use strict";
        const { Component } = require("@odoo/owl");

        class AbstractAwaitablePopup extends Component {
            confirm() {
                const payload =
                    typeof this.getPayload === "function" ? this.getPayload() : undefined;
                this.props.getPayload?.({ confirmed: true, payload });
                this.props.close?.();
            }

            cancel() {
                this.props.getPayload?.({ confirmed: false, payload: null });
                this.props.close?.();
            }
        }

        return { AbstractAwaitablePopup };
    }
);

odoo.define(
    "@point_of_sale/app/store/models",
    [
        "@point_of_sale/app/models/pos_order",
        "@point_of_sale/app/models/pos_order_line",
        "@point_of_sale/app/models/pos_payment",
    ],
    function (require) {
        "use strict";
        const { PosOrder } = require("@point_of_sale/app/models/pos_order");
        const { PosOrderline } = require("@point_of_sale/app/models/pos_order_line");
        const { PosPayment } = require("@point_of_sale/app/models/pos_payment");

        class Packlotline {
            constructor(_env, values = {}) {
                Object.assign(this, values);
            }

            set_lot_name(lotName) {
                this.lot_name = lotName;
            }

            get_lot_name() {
                return this.lot_name;
            }
        }

        return {
            Order: PosOrder,
            Orderline: PosOrderline,
            Payment: PosPayment,
            Packlotline,
        };
    }
);

odoo.define(
    "@point_of_sale/app/store/models/product_custom_attribute",
    ["@point_of_sale/app/models/product_attribute_custom_value"],
    function (require) {
        "use strict";
        const { ProductAttributeCustomValue } = require(
            "@point_of_sale/app/models/product_attribute_custom_value"
        );
        return { ProductCustomAttribute: ProductAttributeCustomValue };
    }
);
