/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AppsBar } from "@muk_web_appsbar/webclient/appsbar/appsbar";

const STORAGE_KEY = "hosny_appsbar_state";
const STATES = ["large", "small"];
const BODY_STATES = ["large", "small", "invisible"];

function getBody() {
    return typeof document === "undefined" ? null : document.body;
}

function getHtml() {
    return typeof document === "undefined" ? null : document.documentElement;
}

function getWebClient() {
    return typeof document === "undefined" ? null : document.querySelector(".o_web_client");
}

function getStoredState() {
    const state = localStorage.getItem(STORAGE_KEY);
    return STATES.includes(state) ? state : null;
}

function getBodyState() {
    const body = getBody();
    if (!body) {
        return "large";
    }
    return STATES.find((state) => body.classList.contains(`mk_sidebar_type_${state}`)) || "large";
}

function setBodyState(state) {
    const body = getBody();
    const targets = [getHtml(), body, getWebClient()].filter(Boolean);
    for (const target of targets) {
        for (const item of BODY_STATES) {
            target.classList.toggle(`mk_sidebar_type_${item}`, item === state);
        }
    }
    localStorage.setItem(STORAGE_KEY, state);
}

function syncStateAfterRender(state) {
    if (typeof window === "undefined") {
        return;
    }
    window.requestAnimationFrame(() => setBodyState(state));
}

function nextState() {
    const current = getStoredState() || getBodyState();
    return STATES[(STATES.indexOf(current) + 1) % STATES.length];
}

const appsbarToggleMethods = {
    hosnySetupAppsbarState() {
        const state = getStoredState() || getBodyState();
        setBodyState(state);
        syncStateAfterRender(state);
    },

    hosnyGetAppsbarState() {
        return getStoredState() || getBodyState();
    },

    hosnyCycleAppsbar() {
        const state = nextState();
        setBodyState(state);
        this.render();
        syncStateAfterRender(state);
    },

    hosnyGetAppsbarToggleIcon() {
        const state = this.hosnyGetAppsbarState();
        return state === "large" ? "fa fa-angle-right" : "fa fa-angle-left";
    },

    hosnyGetAppsbarToggleTitle() {
        const state = this.hosnyGetAppsbarState();
        return state === "large" ? "إظهار الأيقونات فقط" : "إظهار الشريط كاملا";
    },
};

patch(AppsBar.prototype, {
    setup() {
        super.setup();
        this.hosnySetupAppsbarState();
    },
    ...appsbarToggleMethods,
});
