/** @odoo-module **/
/**
 * تحديث نقطة البيع تلقائياً بعد كل نشر (2026-10-09).
 *
 * أودو لا يقول للشاشة المفتوحة إن الكود تغيّر، فيبقى الكاشير الذي لم يضغط F5
 * على النسخة القديمة طول اليوم. هنا تسأل الشاشة السيرفر كل دقيقتين عن روابط
 * حزمة نقطة البيع الحالية (pos.config.hosny_pos_assets_links) وتقارنها بما
 * حمّلته. لو تغيّرت تنتظر لحظة فراغ ثم تزامن الطلبات وتعيد التحميل:
 *   • شاشة الأصناف بطلب فارغ، أو الطاولات / الرئيسية / القفل
 *   • لا نافذة مفتوحة ولا طباعة جارية
 *   • لا لمس ولا كتابة منذ 45 ثانية
 * لا شيء يُفقد: الطلبات تُزامن قبل التحميل، وتبقى في IndexedDB في كل الأحوال.
 * لو أعادت الشاشة التحميل ولم تصلها الروابط الجديدة (كاش في الطريق مثلاً)
 * لا تكرر المحاولة لنفس النسخة، حتى لا تدخل في حلقة تحميل.
 */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

const CHECK_EVERY_MS = 2 * 60 * 1000;
const RETRY_IDLE_MS = 10 * 1000;
const IDLE_FOR_MS = 45 * 1000;
const IDLE_PAGES = new Set([
    "ProductScreen",
    "FloorScreen",
    "HosnyHomeScreen",
    "LoginScreen",
    "SaverScreen",
]);
const TRIED_KEY = "hosny_pos_update_tried";
const DONE_KEY = "hosny_pos_update_done";

let lastActivity = Date.now();
for (const type of ["pointerdown", "keydown", "wheel", "touchstart"]) {
    window.addEventListener(type, () => (lastActivity = Date.now()), {
        capture: true,
        passive: true,
    });
}

const session = {
    get(key) {
        try {
            return sessionStorage.getItem(key);
        } catch {
            return null;
        }
    },
    set(key, value) {
        try {
            sessionStorage.setItem(key, value);
        } catch {
            // بلا sessionStorage: لا حماية من التكرار، فلا نعيد التحميل أصلاً
        }
    },
    remove(key) {
        try {
            sessionStorage.removeItem(key);
        } catch {
            // لا شيء
        }
    },
};

/** روابط حزمة نقطة البيع التي تعمل بها هذه الصفحة الآن. */
export function loadedPosAssets() {
    const urls = [
        ...document.querySelectorAll('script[src*="/web/assets/"], link[href*="/web/assets/"]'),
    ]
        .map((el) => {
            try {
                return new URL(el.getAttribute("src") || el.getAttribute("href"), location.href)
                    .pathname;
            } catch {
                return "";
            }
        })
        .filter((path) => /\/point_of_sale\.assets_prod(_dark)?\./.test(path));
    return {
        urls,
        bundle: urls.some((u) => u.includes("point_of_sale.assets_prod_dark."))
            ? "point_of_sale.assets_prod_dark"
            : "point_of_sale.assets_prod",
        rtl: urls.some((u) => u.includes(".rtl.")),
    };
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        this.hosnyStartAutoUpdate();
        return result;
    },

    hosnyStartAutoUpdate() {
        if (this._hosnyAutoUpdate) {
            return;
        }
        const loaded = loadedPosAssets();
        if (!loaded.urls.length) {
            // وضع debug=assets أو صفحة بلا حزمة الإنتاج: لا شيء نقارنه
            return;
        }
        this._hosnyAutoUpdate = { loaded, target: null, timer: null, idleFor: IDLE_FOR_MS };
        // أعدنا التحميل من هنا في التحديث السابق؟ نقول للكاشير إنه تم.
        const reloadedFor = session.get(DONE_KEY);
        session.remove(DONE_KEY);
        if (reloadedFor && reloadedFor === loaded.urls.slice().sort().join(" ")) {
            this.notification.add("تم تحديث نقطة البيع إلى آخر نسخة", { type: "success" });
        }
        setInterval(() => this.hosnyCheckForUpdate(), CHECK_EVERY_MS);
    },

    async hosnyCheckForUpdate() {
        const state = this._hosnyAutoUpdate;
        if (!state || state.target || this.data.network?.offline) {
            return;
        }
        let links;
        try {
            links = await this.data.call("pos.config", "hosny_pos_assets_links", [
                state.loaded.bundle,
                state.loaded.rtl,
                state.loaded.urls,
            ]);
        } catch {
            return;
        }
        if (!Array.isArray(links) || !links.length) {
            return;
        }
        const current = new Set(links);
        if (state.loaded.urls.every((url) => current.has(url))) {
            return;
        }
        const target = links.slice().sort().join(" ");
        if (session.get(TRIED_KEY) === target) {
            // أعدنا التحميل لهذه النسخة ولم تصل: لا حلقة
            return;
        }
        state.target = target;
        this.hosnyReloadWhenIdle();
    },

    /** صفحة لا يعمل عليها الكاشير الآن؟ */
    hosnyIsIdleForUpdate() {
        if (Date.now() - lastActivity < this._hosnyAutoUpdate.idleFor) {
            return false;
        }
        if (!IDLE_PAGES.has(this.router?.state?.current)) {
            return false;
        }
        if (document.querySelector(".modal, .o_dialog, .o-overlay-item .popover")) {
            return false;
        }
        if (this.env?.services?.printer?.state?.isPrinting) {
            return false;
        }
        if (this.router.state.current === "ProductScreen") {
            const order = this.getOrder();
            if (order && (order.lines?.length || order.payment_ids?.length)) {
                return false;
            }
        }
        return true;
    },

    async hosnyReloadWhenIdle() {
        const state = this._hosnyAutoUpdate;
        clearTimeout(state.timer);
        if (!this.hosnyIsIdleForUpdate() || this.data.network?.offline) {
            state.timer = setTimeout(() => this.hosnyReloadWhenIdle(), RETRY_IDLE_MS);
            return;
        }
        try {
            await this.syncAllOrders();
        } catch {
            state.timer = setTimeout(() => this.hosnyReloadWhenIdle(), RETRY_IDLE_MS);
            return;
        }
        // أثناء المزامنة ربما بدأ الكاشير طلباً
        if (!this.hosnyIsIdleForUpdate()) {
            state.timer = setTimeout(() => this.hosnyReloadWhenIdle(), RETRY_IDLE_MS);
            return;
        }
        session.set(TRIED_KEY, state.target);
        session.set(DONE_KEY, state.target);
        window.location.reload();
    },
});
