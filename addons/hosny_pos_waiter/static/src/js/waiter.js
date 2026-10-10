/** @odoo-module **/

/**
 * حساب «المتر» (طلب 2026-10-09): طلبات محلي على الطاولات فقط.
 *
 *   • يبدأ من خريطة الطاولات، والسفري لا يظهر عنده: لا خيار «سفري» في الشريط،
 *     ولا طابق «سفري» في الخريطة، و«فاتورة جديدة» بلا طاولة تفتح الخريطة.
 *   • لا دفع ولا تسديد فواتير ولا استرداد ولا تقسيم، ولا إيداع / سحب ولا إغلاق
 *     الوردية — الأزرار مخفية (waiter.xml) والشاشات نفسها ممنوعة هنا.
 *   • الخادم يرفض نفس الأشياء (models/)، فهذه الطبقة للواجهة فقط.
 *
 * المتر يُعرف من _hosny_waiter على المستخدم (models/res_users.py).
 */
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosData } from "@point_of_sale/app/services/data_service";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";
import { HosnyHomeScreen } from "@hosny_pos_home/js/home_screen";
import { isTakeawayFloor } from "@pos_entry_selector/js/entry_selector";

/** شاشات الكاشير: الدفع والإيصال والتقسيم والطلبات والتسديد والمرتجع. */
const WAITER_BLOCKED_PAGES = new Set([
    "PaymentScreen",
    "ReceiptScreen",
    "FeedbackScreen",
    "SplitBillScreen",
    "TicketScreen",
    "HosnyPaymentOrdersScreen",
    "HosnyReturnScreen",
]);

const RESET_KEY = `hosny-pos-reset-cache-${odoo.pos_config_id}`;

const DENIED = {
    pay: "الدفع وتسديد الفواتير من الكاشير — المتر يرسل الطلب للمطبخ فقط.",
    takeaway: "طلبات السفري من الكاشير — المتر يعمل طلبات محلي على الطاولات.",
    shift: "الوردية والإيداع / السحب من الكاشير.",
    page: "هذه الشاشة للكاشير فقط.",
};

patch(PosStore.prototype, {
    hosnyIsWaiter() {
        return Boolean(this.user?._hosny_waiter);
    },

    hosnyWaiterDenied(reason = "page") {
        this.notification.add(DENIED[reason] || DENIED.page, { type: "warning" });
    },

    /** المتر يبدأ وينتهي على خريطة الطاولات (بعد «إرسال الطلب» أيضاً). */
    get defaultPage() {
        if (this.hosnyIsWaiter()) {
            return { page: "FloorScreen", params: {} };
        }
        return super.defaultPage;
    },

    navigate(routeName, routeParams = {}) {
        if (this.hosnyIsWaiter() && WAITER_BLOCKED_PAGES.has(routeName)) {
            this.hosnyWaiterDenied(routeName === "PaymentScreen" ? "pay" : "page");
            // طلب طاولة تركه الكاشير على شاشة الدفع: يفتح على الأصناف
            const order = routeParams.orderUuid
                ? this.models["pos.order"].getBy("uuid", routeParams.orderUuid)
                : null;
            if (order && !order.finalized && order.table_id && this.router.state.current !== "ProductScreen") {
                return super.navigate("ProductScreen", { orderUuid: order.uuid });
            }
            return false;
        }
        return super.navigate(...arguments);
    },

    /** F5 على رابط شاشة ممنوعة (‎/pos/ui/<id>/payment/…‎) يرجع للرئيسية. */
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        if (await this.hosnyRefreshStaleUser()) {
            return result;
        }
        if (this.hosnyIsWaiter() && WAITER_BLOCKED_PAGES.has(this.router.state.current)) {
            const first = this.firstPage;
            this.router.navigate(first.page, first.params);
        }
        return result;
    },

    /**
     * أودو 19 لا يقرأ من الخادم عند F5 ما دامت الوردية المفتوحة نفسها في
     * المتصفح، ومخزن المتصفح لنقطة البيع لا للمستخدم. لو كان المستخدم المخزَّن
     * غير الداخل الآن، أو تغيّرت علامة «متر» عليه، نزامن الطلبات ونمسح المخزن
     * ونعيد التحميل مرة واحدة من الخادم.
     */
    async hosnyRefreshStaleUser() {
        let profile;
        try {
            profile = await this.data.call("res.users", "hosny_pos_profile", []);
        } catch {
            return false; // بلا اتصال: نكمل ببيانات الجهاز
        }
        const cached = this.user;
        if (!profile || (cached?.id === profile.id && Boolean(cached?._hosny_waiter) === profile.waiter)) {
            return false;
        }
        const key = `hosny-pos-profile-reset-${odoo.pos_config_id}`;
        const stamp = `${profile.id}:${profile.waiter}`;
        let already = null;
        try {
            already = sessionStorage.getItem(key);
        } catch {
            // التخزين غير متاح
        }
        if (already === stamp) {
            // أُعيد التحميل مرة ولم يتغيّر شيء: نصحح الذاكرة فقط بدل حلقة إعادة تحميل
            if (cached?.id === profile.id) {
                cached._hosny_waiter = profile.waiter;
            }
            return false;
        }
        try {
            await this.syncAllOrders({ throw: true });
        } catch {
            if (cached?.id === profile.id) {
                cached._hosny_waiter = profile.waiter;
            }
            return false; // طلبات لم تُرسل: لا نمسح شيئاً
        }
        if (this.data.network.unsyncData.length) {
            return false;
        }
        try {
            sessionStorage.setItem(key, stamp);
            // المسح نفسه في بداية التحميل التالي (PosData أدناه): مسحه الآن
            // يصطدم بكتابات الصفحة الجارية في المخزن
            sessionStorage.setItem(RESET_KEY, "1");
        } catch {
            return false; // بلا sessionStorage لا نضمن المسح بعد إعادة التحميل
        }
        window.location.reload();
        return true;
    },

    async pay() {
        if (this.hosnyIsWaiter()) {
            this.hosnyWaiterDenied("pay");
            return;
        }
        return await super.pay(...arguments);
    },

    cashMove() {
        if (this.hosnyIsWaiter()) {
            this.hosnyWaiterDenied("shift");
            return;
        }
        return super.cashMove(...arguments);
    },

    async closeSession() {
        if (this.hosnyIsWaiter()) {
            this.hosnyWaiterDenied("shift");
            return;
        }
        return await super.closeSession(...arguments);
    },

    /** طلب المتر الجديد محلي دائماً (أودو يجعل الطلب بلا طاولة سفري). */
    newOrderType(data) {
        if (this.hosnyIsWaiter()) {
            return this.localOrderType;
        }
        return super.newOrderType(...arguments);
    },

    setOrderType(order, type) {
        if (this.hosnyIsWaiter() && type && !this.orderTypeRequiresTable(type)) {
            this.hosnyWaiterDenied("takeaway");
            return;
        }
        return super.setOrderType(...arguments);
    },
});

patch(FloorScreen.prototype, {
    get hosnyFloorTabs() {
        const tabs = super.hosnyFloorTabs;
        return this.pos.hosnyIsWaiter() ? tabs.filter((floor) => !isTakeawayFloor(floor)) : tabs;
    },
});

patch(ControlButtons.prototype, {
    clickHosnyNewInvoice() {
        const order = this.currentOrder || this.pos.getOrder();
        if (this.pos.hosnyIsWaiter() && !(order?.table_id || this.pos.selectedTable)) {
            this.pos.navigate("FloorScreen");
            return;
        }
        return super.clickHosnyNewInvoice(...arguments);
    },
});

patch(Navbar.prototype, {
    get hosnyIsWaiter() {
        return this.pos.hosnyIsWaiter();
    },
    /** «تحرير الخطة» (نقل الطاولات وحذفها) ليس للمتر. */
    get showEditPlanButton() {
        return !this.pos.hosnyIsWaiter() && super.showEditPlanButton;
    },
});

patch(HosnyHomeScreen.prototype, {
    /** المتر: الطاولات فقط (لا مبيعات سفري، ولا طلبات، ولا تقرير، ولا إغلاق). */
    get tiles() {
        const tiles = super.tiles;
        if (!this.pos.hosnyIsWaiter()) {
            return tiles;
        }
        return tiles
            .filter((tile) => tile.key === "tables")
            .map((tile) => ({ ...tile, tone: "green", badge: this.waiterBusyTables }));
    },

    /** عدد الطاولات المفتوحة (بدون طاولات «سفري»). */
    get waiterBusyTables() {
        const tables = new Set();
        for (const order of this.openOrders) {
            const table = order.table_id?.rootTable || order.table_id;
            if (table && !isTakeawayFloor(table.floor_id)) {
                tables.add(table.id);
            }
        }
        return tables.size;
    },
});

patch(PosData.prototype, {
    /** مسح مخزن المتصفح طلبه hosnyRefreshStaleUser، قبل أن يُقرأ منه شيء. */
    async loadInitialData() {
        let reset = false;
        try {
            reset = sessionStorage.getItem(RESET_KEY) === "1";
            sessionStorage.removeItem(RESET_KEY);
        } catch {
            // التخزين غير متاح
        }
        if (reset) {
            await this.resetIndexedDB();
            await this.initIndexedDB(this.relations);
        }
        return await super.loadInitialData(...arguments);
    },
});
