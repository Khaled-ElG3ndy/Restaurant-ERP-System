/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const SIDEBAR_STORAGE_KEY = "hosny_sidebar_collapsed";

export class HosnyAppsSidebar extends Component {
    static template = "hosny_backend_theme.HosnyAppsSidebar";
    static props = {};

    setup() {
        this.appMenuService = useService("app_menu");
        this.sidebarCollapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
    }

    isHosnyRtl() {
        if (typeof document === "undefined") {
            return false;
        }
        return document.documentElement.dir === "rtl" || document.body.dir === "rtl";
    }

    getHosnySidebarToggleIcon() {
        const rtl = this.isHosnyRtl();
        const pointsToOpenSide = this.sidebarCollapsed;
        const direction = pointsToOpenSide !== rtl ? "right" : "left";
        return `oi oi-chevron-${direction} fs-4`;
    }

    getHosnySidebarToggleTitle() {
        return this.sidebarCollapsed ? "Open Sidebar" : "Close Sidebar";
    }

    toggleSidebar() {
        this.sidebarCollapsed = !this.sidebarCollapsed;
        localStorage.setItem(SIDEBAR_STORAGE_KEY, String(this.sidebarCollapsed));
        this.render();
    }
}
