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
import { deserializeDateTime } from "@web/core/l10n/dates";
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

/** 9:05 ص — بأرقام لاتينية كبقية الشاشة. */
function clock12(date) {
    const h = date.getHours();
    return `${pad(h % 12 || 12)}:${pad(date.getMinutes())} ${h < 12 ? "ص" : "م"}`;
}

/** حقول التاريخ تصل luxon أو نصاً. */
const toDateTime = (value) =>
    value ? (typeof value === "string" ? deserializeDateTime(value) : value) : null;

function formatDate(date, locale, options) {
    try {
        return new Intl.DateTimeFormat(locale, options).format(date);
    } catch {
        return "";
    }
}

/** «منذ ...» بالعربية مع صيغ المثنى والجمع. */
function arabicSince(ms) {
    const minutes = Math.max(0, Math.floor(ms / 60000));
    const unit = (n, one, two, few, many) =>
        n === 1 ? one : n === 2 ? two : n <= 10 ? `${n} ${few}` : `${n} ${many}`;
    if (minutes < 60) {
        return minutes < 1 ? "الآن" : unit(minutes, "دقيقة", "دقيقتين", "دقائق", "دقيقة");
    }
    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
        return unit(hours, "ساعة", "ساعتين", "ساعات", "ساعة");
    }
    const days = Math.floor(hours / 24);
    return unit(days, "يوم", "يومين", "أيام", "يوماً");
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
        this.state = useState({ now: new Date(), summary: null, loading: true, failed: false });
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
            this.state.failed = false;
        } catch {
            // بلا اتصال: تبقى الأرقام السابقة، وما يُحسب محلياً يبقى صحيحاً
            this.state.failed = true;
        } finally {
            this.state.loading = false;
        }
    }

    // ── الرأس ───────────────────────────────────────────────────────────
    get branch() {
        return branchName(this.pos.config);
    }
    get time() {
        const d = this.state.now;
        const h = d.getHours() % 12 || 12;
        return { hm: `${pad(h)}:${pad(d.getMinutes())}`, ampm: d.getHours() < 12 ? "ص" : "م" };
    }
    get weekday() {
        return formatDate(this.state.now, "ar-EG", { weekday: "long" });
    }
    get gregorian() {
        return formatDate(this.state.now, "ar-EG-u-nu-latn", { day: "numeric", month: "long", year: "numeric" });
    }
    get hijri() {
        const text = formatDate(this.state.now, "ar-SA-u-ca-islamic-umalqura-nu-latn", {
            day: "numeric",
            month: "long",
            year: "numeric",
        });
        return text.replace(/\s*هـ$/, "") + " هـ";
    }
    get greeting() {
        return this.state.now.getHours() < 12 ? "صباح الخير" : "مساء الخير";
    }
    get cashierName() {
        return this.pos.cashier?.name || this.pos.user?.name || "";
    }
    get cashierInitial() {
        return (this.cashierName.trim()[0] || "ح").toUpperCase();
    }
    get isManager() {
        return this.pos.cashier?._role === "manager";
    }
    get cashierRole() {
        return this.isManager ? "مدير" : "كاشير";
    }
    get online() {
        return !this.pos.data.network?.offline;
    }
    get shift() {
        const s = this.summary;
        const start = s.session_start ? new Date(s.session_start.replace(" ", "T")) : null;
        const hour = start ? start.getHours() : this.state.now.getHours();
        return {
            name: s.session_name || this.pos.session.name,
            label: hour >= 5 && hour < 15 ? "الوردية الصباحية" : "الوردية المسائية",
            startText: start
                ? `${formatDate(start, "ar-EG-u-nu-latn", { day: "numeric", month: "short" })} ${clock12(start)}`
                : "",
            since: start ? arabicSince(this.state.now - start) : "",
        };
    }

    // ── الأرقام ─────────────────────────────────────────────────────────
    fmt(amount) {
        return money(this, amount);
    }
    get summary() {
        return this.state.summary || {};
    }
    get delta() {
        const s = this.summary;
        if (!s.yesterday_total) {
            return null;
        }
        const pct = Math.round(((s.today_total - s.yesterday_total) / s.yesterday_total) * 100);
        return { pct: Math.abs(pct), up: pct >= 0 };
    }
    get openOrders() {
        return this.pos.getOpenOrders().filter((o) => !o.finalized && o.lines.length);
    }
    get tables() {
        const all = dineInFloors(this.pos).flatMap((f) => f.table_ids || []);
        const busy = new Set(
            this.openOrders.filter((o) => o.table_id).map((o) => (o.table_id.rootTable || o.table_id).id)
        );
        const count = all.filter((t) => busy.has(t.id)).length;
        return { busy: count, total: all.length, pct: all.length ? Math.round((count * 100) / all.length) : 0 };
    }
    /** أعمدة صغيرة لمبيعات آخر ساعات اليوم حتى الساعة الحالية. */
    get hours() {
        const s = this.summary;
        const hourly = s.hourly || [];
        if (!hourly.length) {
            return [];
        }
        const now = s.current_hour ?? this.state.now.getHours();
        const from = Math.max(0, now - 7);
        const slice = hourly.slice(from, now + 1);
        const max = Math.max(...slice, 1);
        return slice.map((amount, i) => {
            const h = from + i;
            return {
                h,
                pct: amount ? Math.max(18, Math.round((amount / max) * 100)) : 12,
                tip: `${pad(h)}:00 — ${this.fmt(amount)}`,
                now: h === now,
            };
        });
    }
    get payments() {
        return this.summary.payments || [];
    }
    get paymentsDetail() {
        return this.payments.map((p) => `${p.name}: ${this.fmt(p.amount)}`).join("\n");
    }
    /** الطلبات المفتوحة على الجهاز ثم آخر المدفوعة اليوم، الأحدث أولاً. */
    get recentOrders() {
        const open = this.openOrders.map((o) => {
            const date = toDateTime(o.date_order);
            return {
                key: `open-${o.uuid || o.id}`,
                ref: o.tracking_number || o.name,
                place: o.table_id ? `طاولة ${o.table_id.table_number}` : "سفري",
                amount: o.priceIncl,
                ts: date?.isValid ? date.toMillis() : Date.now(),
                state: "قيد التنفيذ",
                tone: "amber",
            };
        });
        const done = (this.summary.last_orders || []).map((o, i) => ({
            key: `done-${o.ref}-${i}`,
            ref: o.ref,
            place: o.place,
            amount: o.amount,
            ts: o.ts * 1000,
            state: o.invoiced ? "مفوترة" : "مدفوعة",
            tone: o.invoiced ? "blue" : "green",
        }));
        return [...open, ...done]
            .sort((a, b) => b.ts - a.ts)
            .slice(0, 6)
            .map((o) => ({ ...o, time: clock12(new Date(o.ts)) }));
    }

    // ── الاختصارات ──────────────────────────────────────────────────────
    get actions() {
        const pos = this.pos;
        const open = this.openOrders.length;
        return {
            home: { icon: "fa-home", title: "الرئيسية", run: () => {} },
            orders: {
                icon: "fa-file-text-o",
                tone: "violet",
                title: "الطلبات والفواتير",
                navTitle: "الطلبات المفتوحة",
                sub: "عرض الطلبات والفواتير",
                badge: open,
                run: () => pos.navigate("TicketScreen"),
            },
            sell: {
                icon: "fa-shopping-cart",
                tone: "green",
                title: "المبيعات",
                sub: "ابدأ البيع مباشرة",
                run: () => this.startSelling(),
            },
            tables: {
                icon: "fa-cutlery",
                tone: "blue",
                title: "الطاولات",
                sub: `${this.tables.busy} مشغولة من ${this.tables.total}`,
                run: () => this.openTables(),
            },
            cash: pos.showCashMoveButton && pos.cashier?._role !== "minimal" && {
                icon: "fa-money",
                tone: "amber",
                title: "إيداع / سحب",
                sub: "حركات النقدية",
                run: () => pos.cashMove(),
            },
            report: {
                icon: "fa-bar-chart",
                tone: "purple",
                title: "تقرير الوردية",
                sub: "المبيعات وطرق الدفع",
                run: () => this.openReport(),
            },
            close: {
                icon: "fa-power-off",
                tone: "red",
                title: "إغلاق الوردية",
                sub: "الإغلاق اليومي",
                run: () => pos.closeSession(),
            },
            backend: this.isManager && {
                icon: "fa-cog",
                tone: "slate",
                title: "لوحة التحكم",
                sub: "الإعدادات والتقارير",
                run: () => pos.closePos(),
            },
        };
    }
    pick(keys) {
        const actions = this.actions;
        return keys.filter((key) => actions[key]).map((key) => ({ key, ...actions[key] }));
    }
    /** بترتيب القراءة من اليمين: الطاولات، المبيعات، الطلبات. */
    get mainTiles() {
        return this.pick(["tables", "sell", "orders"]);
    }
    get moreTiles() {
        return this.pick(["backend", "close", "report", "cash"]);
    }
    get navItems() {
        return this.pick(["home", "orders", "tables", "sell", "report", "cash", "close"]).map((item) => ({
            ...item,
            title: item.navTitle || item.title,
            active: item.key === "home",
            badge: item.key === "orders" ? item.badge : 0,
        }));
    }

    startSelling() {
        const next = this.pos.defaultPage;
        this.pos.navigate(next.page, next.params);
    }
    openTables() {
        this.pos.currentFloor = dineInFloors(this.pos)[0] || this.pos.currentFloor;
        this.pos.navigate("FloorScreen");
    }
    async openReport() {
        await this.loadSummary();
        this.dialog.add(HosnyShiftReport, { summary: this.summary });
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
