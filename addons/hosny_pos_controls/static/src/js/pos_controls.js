/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { CategorySelector } from "@point_of_sale/app/components/category_selector/category_selector";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { BACKSPACE } from "@point_of_sale/app/components/numpad/numpad";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ManagerPinPopup } from "./manager_pin_popup";

// Log audit action to server
async function logAuditAction(orm, action, reason, approvedBy, cashier, amount, sessionId) {
    try {
        await orm.call("pos.audit.log", "log_action", [], {
            action, reason, approved_by: approvedBy,
            cashier, amount, session_id: sessionId,
        });
    } catch (e) {
        console.warn("Audit log failed:", e);
    }
}

function hosnyCouponErrorMessage(message) {
    const text = String(message || "");
    if (text.includes("already been scanned") || text.includes("already been activated")) {
        return _t("تم إدخال هذا الكود في الطلب الحالي بالفعل.");
    }
    if (
        text.includes("No reward can be claimed") ||
        text.includes("not enough points") ||
        text.includes("There are not enough points")
    ) {
        return _t("تم استخدام هذا الكود بالكامل أو لا يوجد به رصيد كاف.");
    }
    if (text.includes("expired")) {
        return _t("انتهت صلاحية هذا الكود.");
    }
    if (text.includes("not yet valid")) {
        return _t("هذا الكود غير صالح للاستخدام حالياً.");
    }
    if (text.includes("pricelist")) {
        return _t("هذا الكود غير متاح مع قائمة الأسعار الحالية.");
    }
    if (text.includes("invalid")) {
        return _t("الكود غير صحيح. تحقق من الرقم وحاول مرة أخرى.");
    }
    return text || _t("تعذر تطبيق هذا الكود.");
}

function hosnyGetOrderDue(order) {
    if (typeof order?.get_due === "function") {
        return order.get_due();
    }
    return order?.remainingDue ?? order?.get_total_with_tax?.() ?? 0;
}

function hosnyGetCurrentOrder(component) {
    return (
        component.currentOrder ||
        component.pos?.get_order?.() ||
        component.pos?.getOrder?.() ||
        component.pos?.selectedOrder ||
        null
    );
}

function hosnyGetActivatedCoupons(order) {
    return order?._code_activated_coupon_ids || order?.codeActivatedCoupons || [];
}

function hosnyGetLineCouponId(line) {
    return line?.coupon_id?.id || line?.coupon_id || false;
}

const HOSNY_ARABIC_LETTER_ORDER = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي";
const HOSNY_ARABIC_LETTER_MAP = {
    أ: "ا",
    إ: "ا",
    آ: "ا",
    ٱ: "ا",
    ؤ: "و",
    ئ: "ي",
    ى: "ي",
    ة: "ه",
};

function hosnyProductLetter(product) {
    const rawName = String(product?.display_name || product?.name || "").trim();
    const name = rawName
        .replace(/[\u064B-\u065F\u0670\u0640]/g, "")
        .replace(/^ال(?=[\u0621-\u064A])/, "");

    for (const char of name) {
        if (!/[\u0621-\u064A]/.test(char)) {
            continue;
        }
        return HOSNY_ARABIC_LETTER_MAP[char] || char;
    }
    return "";
}

function hosnySortLetters(letters) {
    return [...letters].sort((a, b) => {
        const indexA = HOSNY_ARABIC_LETTER_ORDER.indexOf(a);
        const indexB = HOSNY_ARABIC_LETTER_ORDER.indexOf(b);
        if (indexA === -1 && indexB === -1) {
            return a.localeCompare(b, "ar");
        }
        if (indexA === -1) {
            return 1;
        }
        if (indexB === -1) {
            return -1;
        }
        return indexA - indexB;
    });
}

function hosnyShouldDebugLetterFilter() {
    return typeof window !== "undefined" && window.location?.search?.includes("debug=1");
}

function hosnyFilterProductsByLetter(pos, products) {
    const selectedLetter = pos?.hosnyProductLetterFilter;
    // No category test here on purpose: the rail is shown from the moment the
    // product screen opens, so a letter has to narrow the grid whether or not
    // a category is chosen. Khaled asked for that on 2026-09-14.
    if (!selectedLetter || !Array.isArray(products)) {
        return products;
    }
    return products.filter((product) => hosnyProductLetter(product) === selectedLetter);
}

function hosnyAnimateLetterFilter() {
    if (typeof document === "undefined") {
        return;
    }
    const pane = document.querySelector(".pos .product-screen .rightpane");
    if (!pane) {
        return;
    }
    pane.classList.remove("hosny-letter-filter-switching");
    pane.getBoundingClientRect();
    pane.classList.add("hosny-letter-filter-switching");
    window.clearTimeout(pane.hosnyLetterFilterTimer);
    pane.hosnyLetterFilterTimer = window.setTimeout(() => {
        pane.classList.remove("hosny-letter-filter-switching");
    }, 220);
}

function hosnyDeleteOrderline(component, line) {
    const targetLine = line?.combo_parent_id || line;
    const order = targetLine?.order_id;
    const dialog = component.dialog || component.env.services.dialog;

    if (!targetLine || !order) {
        return;
    }

    try {
        // ما أُرسل للمطبخ يحتاج سبباً واعتماداً (void_approval.js).
        const pos = component.pos || component.env.services.pos;
        const removal = pos?.hosnyGuardedRemoveLine
            ? pos.hosnyGuardedRemoveLine(targetLine)
            : order.removeOrderline(targetLine);
        Promise.resolve(removal).catch((error) =>
            dialog?.add(AlertDialog, {
                title: _t("تعذر حذف الصنف"),
                body: error.message || _t("لا يمكن حذف هذا الصنف الآن."),
            })
        );
    } catch (error) {
        dialog?.add(AlertDialog, {
            title: _t("تعذر حذف الصنف"),
            body: error.message || _t("لا يمكن حذف هذا الصنف الآن."),
        });
    }
}

async function hosnyActivateOrderCode(pos, order, code) {
    if (typeof pos?.activateCode === "function") {
        return pos.activateCode(code);
    }
    if (typeof order?._activateCode === "function") {
        return order._activateCode(code);
    }
    if (typeof order?.activateCode === "function") {
        const notification = order.env?.services?.pos_notification;
        const originalAdd = notification?.add;
        let capturedMessage = null;
        if (notification && originalAdd) {
            notification.add = function (message, ...args) {
                capturedMessage = message;
                return originalAdd.call(this, message, ...args);
            };
        }
        try {
            await order.activateCode(code);
        } finally {
            if (notification && originalAdd) {
                notification.add = originalAdd;
            }
        }
        return capturedMessage || true;
    }
    return _t("لم يتم تحميل نظام الكوبونات في نقطة البيع. أعد تحميل الصفحة ثم حاول مرة أخرى.");
}

// Patch PosStore to add manager PIN check utility
patch(PosStore.prototype, {
    get productsToDisplay() {
        const products = super.productsToDisplay;
        return hosnyFilterProductsByLetter(this, products);
    },

    get productToDisplayByCateg() {
        const groups = super.productToDisplayByCateg;
        if (!this.hosnyProductLetterFilter || !Array.isArray(groups)) {
            return groups;
        }
        return groups
            .map(([categoryId, products]) => [
                categoryId,
                hosnyFilterProductsByLetter(this, products),
            ])
            .filter(([, products]) => products.length);
    },

    async requireManagerApproval(action, title, subtitle) {
        return new Promise((resolve) => {
            this.dialog.add(ManagerPinPopup, {
                title: title || `Manager Required / يلزم مدير`,
                subtitle: subtitle || `Action: ${action}`,
                confirm: (result) => resolve({ approved: true, ...result }),
                close: () => resolve({ approved: false }),
            });
        });
    },

    // Override discount application
    async applyDiscount(discount) {
        if (discount > 5) { // Threshold — anything above 5% needs manager
            const result = await this.requireManagerApproval(
                "discount",
                `Discount Authorization / تفويض الخصم`,
                `Discount: ${discount}% — Manager approval required`
            );
            if (!result.approved) {
                this.notification.add("Discount cancelled — no manager approval", { type: "warning" });
                return false;
            }
            // Log it
            const session = this.pos_session;
            await logAuditAction(
                this.env.services.orm,
                "discount", result.reason, result.approvedBy,
                this.cashierName, discount, session?.id
            );
            this.notification.add(`✅ Discount approved by: ${result.approvedBy}`, { type: "success" });
        }
        return true;
    },

    // pos_restaurant's pay() and validateOrderFast() await this «تحذير!» prompt,
    // then core reads getOrder() again. If the floor plan takes over meanwhile —
    // a «إرسال الطلب» finishing behind the prompt — FloorScreen.resetTable() has
    // called setOrder(null) and core pay() throws on getOrder().canPay().
    // Reselect the order the cashier was paying while it is still open.
    async _askForPreparation() {
        const order = this.getOrder();
        await super._askForPreparation(...arguments);
        if (
            order &&
            !this.getOrder() &&
            !order.finalized &&
            this.models["pos.order"].getBy("uuid", order.uuid)
        ) {
            this.setOrder(order);
        }
    },
});

patch(Orderline.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.numberBuffer = useService("number_buffer");
    },

    deleteHosnyOrderline(line) {
        hosnyDeleteOrderline(this, line);
    },
});

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.hosnyShowNumpad = false;
    },

    get isHosnyNumpadVisible() {
        return Boolean(this.state.hosnyShowNumpad);
    },

    toggleHosnyNumpad() {
        this.state.hosnyShowNumpad = !this.state.hosnyShowNumpad;
    },

    setHosnyNumpadMode(mode) {
        this.pos.numpadMode = mode;
        this.state.hosnyShowNumpad = true;
        this.numberBuffer.reset();
    },

    hosnyNumpadModeClass(mode) {
        // the mode the keyboard and the number grid are typing into
        return this.pos.numpadMode === mode ? `is-active is-mode-${mode}` : "";
    },

    getHosnyNumpadButtons() {
        const decimalPoint = this.env.services.localization.decimalPoint;
        const buttons = [
            { value: "1" },
            { value: "2" },
            { value: "3" },
            { value: "4" },
            { value: "5" },
            { value: "6" },
            { value: "7" },
            { value: "8" },
            { value: "9" },
            {
                value: "price",
                text: _t("Price"),
                disabled:
                    !this.pos.cashierHasPriceControlRights() ||
                    this.pos.cashier._role === "minimal",
            },
            { value: "-", text: "+/-" },
            { value: "0" },
            { value: decimalPoint, text: decimalPoint },
            BACKSPACE,
            { value: "__hosny_empty__", text: "", disabled: true, class: "hosny-hidden-key" },
        ];

        return buttons.map((button) => ({
            ...button,
            disabled:
                button.disabled ||
                (button.value === "-" && this.pos.cashier._role === "minimal"),
            class: `
                ${button.class || ""}
                ${this.pos.numpadMode === button.value ? "active" : ""}
                ${button.value === "price" ? "numpad-price" : ""}
            `,
        }));
    },

    getHosnyLetterFilterProducts() {
        const selectedCategory = this.pos.selectedCategory;
        const productsById = new Map();

        if (selectedCategory?.id) {
            const categoryIds = selectedCategory.getAllChildren?.().map(
                (category) => category.id
            ) || [selectedCategory.id];
            const productTemplateModel = this.pos.models["product.template"].toRaw();
            const productsByCategory = productTemplateModel.getAllBy?.("pos_categ_ids") || {};

            for (const categoryId of categoryIds) {
                const products = productsByCategory[categoryId] || [];
                for (const product of products) {
                    productsById.set(product.id, product);
                }
            }

            if (!productsById.size) {
                const fallbackProducts = selectedCategory.associatedProducts || [];
                for (const product of fallbackProducts) {
                    productsById.set(product.id, product);
                }
            }
        } else {
            // Nothing chosen: the rail spans the whole catalogue, so it is
            // there the moment the screen opens rather than appearing once a
            // category is picked. Deliberately NOT read off
            // `pos.productsToDisplay` — that getter is patched to apply the
            // letter filter, so the rail would collapse to the one letter
            // already active and the cashier could not get back out of it.
            for (const product of this.pos.models["product.template"].getAll?.() || []) {
                productsById.set(product.id, product);
            }
        }

        let products = [...productsById.values()];
        const searchWord = (this.pos.searchProductWord || "").trim();
        if (searchWord) {
            products = this.pos.getProductsBySearchWord(searchWord, products);
        }
        products = this.pos.filterExcludedProducts(products);

        if (hosnyShouldDebugLetterFilter()) {
            const letters = hosnySortLetters(new Set(products.map(hosnyProductLetter).filter(Boolean)));
            const debugKey = JSON.stringify({
                categoryId: selectedCategory?.id || 0,
                categoryName: selectedCategory?.name || "",
                products: products.length,
                letters,
                searchWord,
            });
            if (this._hosnyLetterDebugKey !== debugKey) {
                this._hosnyLetterDebugKey = debugKey;
                console.info("[Hosny Letter Filter]", JSON.parse(debugKey));
            }
        }

        return products;
    },

    getHosnyAvailableLetters() {
        const letters = new Set();
        for (const product of this.getHosnyLetterFilterProducts()) {
            const letter = hosnyProductLetter(product);
            if (letter) {
                letters.add(letter);
            }
        }
        return hosnySortLetters(letters);
    },

    isHosnyProductLetterActive(letter) {
        return this.pos.hosnyProductLetterFilter === letter;
    },

    selectHosnyProductLetter(letter) {
        hosnyAnimateLetterFilter();
        this.pos.hosnyProductLetterFilter =
            this.pos.hosnyProductLetterFilter === letter ? "" : letter;
    },

    clearHosnyProductLetterFilter() {
        hosnyAnimateLetterFilter();
        this.pos.hosnyProductLetterFilter = "";
    },

    directHosnyPayment() {
        const order = this.currentOrder || this.pos.getOrder();
        // A send still in flight ends on the floor plan and deselects the order
        // under pay(); the button is disabled for the same window (controls.xml).
        if (this.doSubmitOrder?.status === "loading" || !order?.canPay?.()) {
            return;
        }
        if (typeof this.pos.pay === "function") {
            return this.pos.pay();
        }
        this.pos.mobile_pane = "right";
        order.setScreenData?.({ name: "PaymentScreen" });
        return this.pos.navigate("PaymentScreen", {
            orderUuid: this.pos.selectedOrderUuid || order.uuid,
        });
    },

    /**
     * حالة زر «إرسال الطلب» (طلب 2026-09-28): «تم الإرسال ✓» حين لا يوجد ما
     * يُرسل، و«إرسال الطلب» مع عدد الأصناف المتغيّرة حين يُضاف صنف أو تتغيّر
     * كمية أو ملاحظة. «ما يُرسل» بنفس تعريف أودو (getOrderChanges): الكمية،
     * ملاحظة السطر، والملاحظة العامة/الداخلية — nbrOfChanges وحده لا يحسب
     * الملاحظات. طلب أصنافه كلها خارج طابعات التحضير لم يُرسل أصلاً، فيبقى
     * زره كما كان.
     */
    get hosnySendState() {
        const order = this.currentOrder;
        if (!order || order.isEmpty()) {
            return { pending: false, sent: false, count: 0 };
        }
        const changes = this.pos.getOrderChanges(order);
        const changedLines = new Set([
            ...Object.keys(changes.orderlines || {}),
            ...Object.keys(changes.noteUpdate || {}),
        ]);
        const pending = Boolean(
            changedLines.size ||
                changes.general_customer_note !== undefined ||
                changes.internal_note !== undefined
        );
        const everSent =
            order.preparation_state === "sent" ||
            Object.keys(order.last_order_preparation_change?.lines || {}).length > 0;
        return { pending, sent: !pending && everSent, count: changedLines.size };
    },

    async sendHosnyOrder() {
        const order = this.currentOrder || this.pos.getOrder();
        if (!order || order.isEmpty() || this.hosnySendState.sent) {
            return;
        }
        if (this.doSubmitOrder?.call) {
            return this.doSubmitOrder.call();
        }
        return this.pos.submitOrder?.();
    },

    onHosnyCategorySearchInput(ev) {
        this.pos.searchProductWord = ev.target.value || "";
    },

    clearHosnyCategorySearch() {
        this.pos.searchProductWord = "";
    },
});

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        const order = hosnyGetCurrentOrder(this);
        if (paymentMethod?.type === "pay_later" && order && !order.getPartner?.()) {
            const partner = await this.pos.selectPartner(order);
            if (!partner) {
                const notification = this.notification || this.env.services.notification;
                notification.add(_t("اختار العميل الأول قبل الدفع الآجل."), {
                    type: "warning",
                });
                return false;
            }
        }
        return super.addNewPaymentLine(...arguments);
    },

    async hosnyLoadRewardDiscountProducts() {
        const rewardModel = this.pos.models?.["loyalty.reward"];
        const productModel = this.pos.models?.["product.product"];
        const rewards = rewardModel?.getAll?.() || [];
        const missingProductIds = [
            ...new Set(
                rewards
                    .map((reward) => reward.raw?.discount_line_product_id)
                    .filter((productId) => productId && !productModel?.get?.(productId))
            ),
        ];

        if (!missingProductIds.length) {
            return true;
        }

        try {
            await this.pos.data.callRelated(
                "product.template",
                "load_product_from_pos",
                [
                    this.pos.config.id,
                    [["product_variant_ids.id", "in", missingProductIds]],
                    0,
                    0,
                ],
                { context: { load_archived: true } }
            );
        } catch (error) {
            console.warn("Could not load POS reward products", error);
            return false;
        }

        return missingProductIds.every((productId) => productModel?.get?.(productId));
    },

    async hosnyApplyAlreadyActivatedCode(code) {
        const order = hosnyGetCurrentOrder(this);
        const coupon = hosnyGetActivatedCoupons(order).find?.((coupon) => coupon.code === code);
        if (!coupon || typeof order.getClaimableRewards !== "function") {
            return false;
        }

        await this.hosnyLoadRewardDiscountProducts();
        const claimableRewards = order.getClaimableRewards(coupon.id);
        if (
            claimableRewards?.length === 1 &&
            (claimableRewards[0].reward.reward_type !== "product" ||
                !claimableRewards[0].reward.multi_product)
        ) {
            order._applyReward(claimableRewards[0].reward, claimableRewards[0].coupon_id);
            this.pos.updateRewards?.();
            return true;
        }
        return false;
    },

    async openPromoCode() {
        const dialog = this.dialog || this.env.services.dialog;
        const notification = this.notification || this.env.services.notification;
        const order = hosnyGetCurrentOrder(this);
        const code = await makeAwaitable(dialog, TextInputPopup, {
            title: _t("إدخال كود"),
            placeholder: _t("أدخل كود بطاقة الهدية أو الخصم"),
        });
        const trimmedCode = (code || "").trim();
        if (!trimmedCode) {
            return;
        }

        if (!order) {
            notification.add(_t("لا يوجد طلب حالي لتطبيق الكود عليه."), { type: "warning" });
            return;
        }
        if (hosnyGetActivatedCoupons(order).some((coupon) => coupon.code === trimmedCode)) {
            notification.add(_t("تم إدخال هذا الكود في الطلب الحالي بالفعل."), {
                type: "warning",
            });
            return;
        }

        await this.hosnyLoadRewardDiscountProducts();
        const dueBefore = Math.max(hosnyGetOrderDue(order), 0);
        try {
            const result = await hosnyActivateOrderCode(this.pos, order, trimmedCode);
            if (result !== true) {
                notification.add(hosnyCouponErrorMessage(result), { type: "warning" });
                return;
            }

            const coupon = hosnyGetActivatedCoupons(order).find((coupon) => coupon.code === trimmedCode);
            const rewardLines = coupon
                ? (order._get_reward_lines?.() || []).filter(
                      (line) => hosnyGetLineCouponId(line) === coupon.id
                  )
                : [];
            const dueAfter = Math.max(hosnyGetOrderDue(order), 0);
            const remainingCouponValue =
                coupon && typeof order._getRealCouponPoints === "function"
                    ? order._getRealCouponPoints(coupon.id)
                    : null;

            if (rewardLines.length || dueAfter < dueBefore) {
                if (remainingCouponValue !== null && remainingCouponValue <= 0) {
                    notification.add(
                        _t("تم تطبيق الكود واستُخدم الرصيد بالكامل. لن يمكن استخدامه مرة أخرى."),
                        { type: "success" }
                    );
                } else if (remainingCouponValue !== null) {
                    notification.add(
                        _t(
                            "تم تطبيق الكود. المتبقي في الكود: %s",
                            this.env.utils.formatCurrency(remainingCouponValue)
                        ),
                        { type: "success" }
                    );
                } else {
                    notification.add(_t("تم تطبيق الكود بنجاح."), { type: "success" });
                }
            } else {
                notification.add(
                    _t("تم تفعيل الكود، لكن لا يوجد خصم متاح لهذا الطلب."),
                    { type: "warning" }
                );
            }
        } catch (error) {
            console.error("Coupon activation failed", error);
            if (await this.hosnyApplyAlreadyActivatedCode(trimmedCode)) {
                return;
            }
            notification.add(
                _t("تعذر تطبيق هذا الكود. أعد تحميل نقطة البيع وحاول مرة أخرى."),
                { type: "danger" }
            );
        }
    },
});

patch(ControlButtons.prototype, {
    clickHosnyNewInvoice() {
        const currentOrder = this.currentOrder || this.pos.getOrder();
        const table = currentOrder?.table_id || this.pos.selectedTable;
        const order = table ? this.pos.addNewOrder({ table_id: table }) : this.pos.addNewOrder();
        this.pos.navigate("ProductScreen", { orderUuid: order.uuid });
    },
});

patch(CategorySelector.prototype, {
    hosnyIsCategorySelected(categoryId) {
        return !!categoryId && this.pos.selectedCategory?.id === categoryId;
    },

    hosnyToggleCategory(categoryId) {
        if (!categoryId) {
            this.pos.setSelectedCategory(0);
            this.pos.hosnyProductLetterFilter = "";
            return;
        }
        if (this.pos.selectedCategory?.id === categoryId) {
            this.pos.setSelectedCategory(0);
            this.pos.hosnyProductLetterFilter = "";
            return;
        }
        this.pos.setSelectedCategory(categoryId);
        this.pos.hosnyProductLetterFilter = "";
    },

    onHosnyCategorySearchInput(ev) {
        this.pos.searchProductWord = ev.target.value || "";
        this.pos.hosnyProductLetterFilter = "";
    },

    clearHosnyCategorySearch() {
        this.pos.searchProductWord = "";
        this.pos.hosnyProductLetterFilter = "";
    },
});

console.log("✅ Hosny POS Controls loaded — Manager PIN protection active");
