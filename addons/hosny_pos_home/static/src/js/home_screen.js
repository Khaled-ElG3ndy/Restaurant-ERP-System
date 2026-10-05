/** @odoo-module **/

/**
 * الشاشة الرئيسية: أول ما يظهر عند فتح نقطة البيع (بدل بطاقة «إلغاء قفل
 * الكاشير»)، وما يرجع إليه الكاشير بعد شاشة التوقف أو من زر «الرئيسية» في
 * الشريط العلوي. منها: المبيعات (الكاشير)، الطاولات، الطلبات، إيداع / سحب،
 * تقرير الوردية، إغلاق الوردية.
 *
 * تعمل فقط مع «الكاشير أولاً» وبلا pos_hr — هناك تكون شاشة الدخول زراً واحداً
 * بلا اختيار كاشير، فلا يضيع شيء باستبدالها.
 */
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { LoginScreen } from "@point_of_sale/app/screens/login_screen/login_screen";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { handleSaleDetails } from "@point_of_sale/app/components/navbar/sale_details_button/sale_details_button";
import { dineInFloors } from "@pos_entry_selector/js/entry_selector";

const HOME = "HosnyHomeScreen";
const pad = (n) => String(n).padStart(2, "0");

function branchName(config) {
    const name = config?.name || "";
    for (const city of ["الرياض", "المدينة", "جدة"]) {
        if (name.includes(city)) {
            return city === "المدينة" ? "المدينة المنورة" : city;
        }
    }
    if (name.includes("جده")) {
        return "جدة";
    }
    return name.replace("مطعم حسني", "").replace("-", "").trim() || name;
}

/**
 * 1,240.50 SR — الرمز بعد الرقم أياً كان موضعه في إعدادات العملة. معزول
 * باتجاه LTR (LRI … PDI) وإلا قلبته الشاشة العربية إلى SR 1,240.50.
 */
function money(component, amount) {
    const pos = component.pos;
    const symbol = pos.currency?.symbol ?? pos.config.currency_id?.symbol ?? "";
    const number = component.env.utils.formatCurrency(amount || 0, false);
    return symbol ? `\u2066${number}\u00a0${symbol}\u2069` : number;
}

function formatDate(date, locale, options) {
    try {
        return new Intl.DateTimeFormat(locale, options).format(date);
    } catch {
        return "";
    }
}

export class HosnyShiftReport extends Component {
    static template = "hosny_pos_home.ShiftReport";
    static components = { Dialog };
    static props = { summary: Object, close: Function };

    setup() {
        this.pos = usePos();
        this.hardwareProxy = useService("hardware_proxy");
        this.dialog = useService("dialog");
    }
    get canPrint() {
        return Boolean(this.hardwareProxy.printer);
    }
    fmt(amount) {
        return money(this, amount);
    }
    qty(value) {
        return Number.isInteger(value) ? value : Number(value || 0).toFixed(2);
    }
    async print() {
        await handleSaleDetails(this.pos, this.hardwareProxy, this.dialog);
    }
}

export class HosnyHomeScreen extends Component {
    static template = "hosny_pos_home.HomeScreen";
    static storeOnOrder = false;
    static props = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.state = useState({ now: new Date(), summary: null, syncedAt: null, failed: false });
        this.logo = "/pos_modern_ui/static/src/img/logo.png";
        let clock, refresh;
        onMounted(() => {
            clock = setInterval(() => (this.state.now = new Date()), 1000);
            refresh = setInterval(() => this.loadSummary(), 60000);
            this.loadSummary();
            this.pos.openOpeningControl();
        });
        onWillUnmount(() => {
            clearInterval(clock);
            clearInterval(refresh);
        });
    }

    async loadSummary() {
        try {
            this.state.summary = await this.pos.data.call("pos.session", "hosny_home_summary", [
                [this.pos.session.id],
            ]);
            this.state.syncedAt = new Date();
            this.state.failed = false;
        } catch {
            // بلا اتصال: يبقى تقرير الوردية على آخر بيانات، و«آخر مزامنة» على آخر نجاح
            this.state.failed = true;
        }
    }

    // ── المربعات العلوية ────────────────────────────────────────────────
    get branch() {
        return branchName(this.pos.config);
    }
    /** نفس عنوان الفاتورة: عنوان الفرع، وإلا عنوان الشركة، وإلا اسم المدينة. */
    get branchAddress() {
        const config = this.pos.config;
        const company = config.company_id || this.pos.company;
        return (
            config.hosny_receipt_address ||
            [company?.street, company?.street2, company?.city].filter(Boolean).join(" ") ||
            this.branch
        );
    }
    /** 17:36 و 54 — الثواني تُعرض أخفت. */
    get time() {
        const d = this.state.now;
        return { hm: `${pad(d.getHours())}:${pad(d.getMinutes())}`, s: pad(d.getSeconds()) };
    }
    /** 05/10/2026 */
    get date() {
        const d = this.state.now;
        return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
    }
    get hijri() {
        const text = formatDate(this.state.now, "ar-SA-u-ca-islamic-umalqura-nu-latn", {
            day: "numeric",
            month: "long",
            year: "numeric",
        });
        return text.replace(/\s*هـ$/, "") + " هـ";
    }
    get syncedAt() {
        const d = this.state.syncedAt;
        if (!d) {
            return "…";
        }
        return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} ${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
    }
    get cashierName() {
        return this.pos.cashier?.name || this.pos.user?.name || "";
    }
    get isManager() {
        return this.pos.cashier?._role === "manager";
    }
    get online() {
        return !this.pos.data.network?.offline;
    }
    get openOrders() {
        return this.pos.getOpenOrders().filter((o) => !o.finalized && o.lines.length);
    }

    // ── الأزرار ─────────────────────────────────────────────────────────
    /** بترتيب القراءة من اليمين؛ خمسة في الصف، والباقي تحتها من اليمين. */
    get tiles() {
        const pos = this.pos;
        const tiles = [
            { key: "sell", tone: "green", icon: "fa-shopping-cart", title: "المبيعات", run: () => this.startSelling() },
            { key: "tables", tone: "navy", icon: "fa-cutlery", title: "الطاولات", run: () => this.openTables() },
            {
                key: "orders",
                tone: "blue",
                icon: "fa-list-alt",
                title: "الطلبات والفواتير",
                badge: this.openOrders.length,
                run: () => pos.navigate("TicketScreen"),
            },
        ];
        if (pos.showCashMoveButton && pos.cashier?._role !== "minimal") {
            tiles.push({ key: "cash", tone: "amber", icon: "fa-exchange", title: "إيداع / سحب", run: () => pos.cashMove() });
        }
        tiles.push({ key: "report", tone: "deep", icon: "fa-file-text", title: "تقرير الوردية", run: () => this.openReport() });
        if (this.isManager) {
            tiles.push({ key: "backend", tone: "slate", icon: "fa-cogs", title: "الإعدادات", run: () => this.openSettings() });
        }
        tiles.push({ key: "close", tone: "red", icon: "fa-power-off", title: "إغلاق الوردية", run: () => pos.closeSession() });
        return tiles;
    }

    startSelling() {
        const next = this.pos.defaultPage;
        this.pos.navigate(next.page, next.params);
    }
    openTables() {
        this.pos.currentFloor = dineInFloors(this.pos)[0] || this.pos.currentFloor;
        this.pos.navigate("FloorScreen");
    }
    /**
     * إعدادات نقطة البيع في تبويب جديد، على نقطة البيع هذه (انظر
     * views/pos_settings_action.xml)؛ الكاشير يبقى مفتوحاً في تبويبه.
     */
    openSettings() {
        window.open(`/odoo/${this.pos.config.id}/action-hosny_pos_home.action_pos_settings_current`, "_blank");
    }
    async openReport() {
        await this.loadSummary();
        this.dialog.add(HosnyShiftReport, { summary: this.state.summary || {} });
    }
}

registry.category("pos_pages").add(HOME, {
    name: HOME,
    component: HosnyHomeScreen,
    route: `/pos/ui/${odoo.pos_config_id}/home`,
    params: {},
});

patch(PosStore.prototype, {
    hosnyHomeEnabled() {
        return this.hosnyCashierFirst() && !this.config.module_pos_hr;
    },
    hosnyHomePage() {
        if (!this.cashier) {
            this.setCashier(this.user);
        }
        return { page: HOME, params: {} };
    },
    get firstPage() {
        const page = super.firstPage;
        return this.hosnyHomeEnabled() ? this.hosnyHomePage() : page;
    },
    async showLoginScreen() {
        if (this.hosnyHomeEnabled()) {
            const home = this.hosnyHomePage();
            this.navigate(home.page, home.params);
            this.dialog.closeAll();
            return;
        }
        return super.showLoginScreen(...arguments);
    },
    hosnyGoHome() {
        const home = this.hosnyHomePage();
        this.navigate(home.page, home.params);
    },
    /** الرئيسية هي شاشة الانتظار نفسها (ساعة وتاريخ): لا تغطيها شاشة التوقف. */
    get idleTimeout() {
        return super.idleTimeout.map((step) => ({
            ...step,
            action: () => (this.router.state.current === HOME ? false : step.action()),
        }));
    },
});

patch(LoginScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            if (this.pos.hosnyHomeEnabled()) {
                this.pos.hosnyGoHome();
            }
        });
    },
});

patch(Navbar.prototype, {
    get hosnyShowHomeButton() {
        return this.pos.hosnyHomeEnabled() && this.pos.router.state.current !== HOME;
    },
});
