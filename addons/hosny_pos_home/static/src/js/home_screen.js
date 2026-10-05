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
        return this.env.utils.formatCurrency(amount || 0);
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
    get branchInfo() {
        const c = this.pos.config;
        return {
            address: c.hosny_receipt_address || "",
            phone: c.hosny_receipt_phone || "",
            vat: c.hosny_receipt_vat || "",
        };
    }
    get time() {
        const d = this.state.now;
        const h = d.getHours() % 12 || 12;
        return { hm: `${pad(h)}:${pad(d.getMinutes())}`, s: pad(d.getSeconds()), ampm: d.getHours() < 12 ? "ص" : "م" };
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
    get online() {
        return !this.pos.data.network?.offline;
    }

    // ── الأرقام ─────────────────────────────────────────────────────────
    fmt(amount) {
        return this.env.utils.formatCurrency(amount || 0);
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
    get average() {
        const s = this.summary;
        return s.today_count ? s.today_total / s.today_count : 0;
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
    get shift() {
        const s = this.summary;
        const start = s.session_start ? new Date(s.session_start.replace(" ", "T")) : null;
        return {
            name: s.session_name || this.pos.session.name,
            startText: start
                ? `${formatDate(start, "ar-EG-u-nu-latn", { day: "numeric", month: "short" })} · ${pad(start.getHours())}:${pad(start.getMinutes())}`
                : "",
            since: start ? arabicSince(this.state.now - start) : "",
        };
    }
    /** أعمدة المبيعات بالساعة: من أول ساعة فيها مبيعات (أو 8 ص) إلى الساعة الحالية. */
    get hours() {
        const s = this.summary;
        const hourly = s.hourly || [];
        if (!hourly.length) {
            return [];
        }
        const now = s.current_hour ?? this.state.now.getHours();
        const first = hourly.findIndex((v) => v);
        const from = Math.max(0, Math.min(first === -1 ? 8 : first, now - 7, 8));
        const slice = hourly.slice(from, now + 1);
        const max = Math.max(...slice, 1);
        return slice.map((amount, i) => {
            const h = from + i;
            return {
                h,
                label: `${h % 12 || 12} ${h < 12 ? "ص" : "م"}`,
                amount,
                pct: amount ? Math.max(6, Math.round((amount / max) * 100)) : 0,
                tip: `${pad(h)}:00 — ${this.fmt(amount)}`,
                now: h === now,
            };
        });
    }
    get payments() {
        const list = this.summary.payments || [];
        const max = Math.max(...list.map((p) => p.amount), 1);
        return list.map((p) => ({ ...p, pct: Math.max(3, Math.round((p.amount / max) * 100)) }));
    }

    // ── الاختصارات ──────────────────────────────────────────────────────
    get tiles() {
        const pos = this.pos;
        const role = pos.cashier?._role;
        const tiles = [
            {
                key: "tables",
                tone: "blue",
                icon: "fa-cutlery",
                title: "الطاولات",
                sub: `${this.tables.busy} مشغولة من ${this.tables.total}`,
                run: () => this.openTables(),
            },
            {
                key: "orders",
                tone: "violet",
                icon: "fa-file-text-o",
                title: "الطلبات والفواتير",
                sub: `${this.openOrders.length} طلب مفتوح`,
                run: () => pos.navigate("TicketScreen"),
            },
        ];
        if (pos.showCashMoveButton && role !== "minimal") {
            tiles.push({
                key: "cash",
                tone: "amber",
                icon: "fa-exchange",
                title: "إيداع / سحب",
                sub: "حركة نقدية في الدرج",
                run: () => pos.cashMove(),
            });
        }
        tiles.push({
            key: "report",
            tone: "magenta",
            icon: "fa-bar-chart",
            title: "تقرير الوردية",
            sub: "المبيعات وطرق الدفع",
            run: () => this.openReport(),
        });
        if (role === "manager") {
            tiles.push({
                key: "backend",
                tone: "slate",
                icon: "fa-cogs",
                title: "لوحة التحكم",
                sub: "الإعدادات والتقارير الكاملة",
                run: () => pos.closePos(),
            });
        }
        tiles.push({
            key: "close",
            tone: "red",
            icon: "fa-power-off",
            title: "إغلاق الوردية",
            sub: "جرد الصندوق وإقفال الجلسة",
            run: () => pos.closeSession(),
        });
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
