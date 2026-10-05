import {
    Component,
    onWillDestroy,
    onWillStart,
    onWillUpdateProps,
    status,
    useExternalListener,
    useRef,
    useState,
} from "@odoo/owl";

import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { browser } from "@web/core/browser/browser";
import {
    serializeDateTime,
} from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { useSetupAction } from "@web/search/action_hook";
import { standardViewProps } from "@web/views/standard_view_props";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

import {
    BASE_HOUR_WIDTHS,
    TIMELINE_HEADER_HEIGHT,
    TIMELINE_ROW_HEIGHT,
    buildTimelineRows,
    filterTimelineEmployees,
    getTimelineSelection,
    getTimelineRange,
} from "./timeline_utils";

const { DateTime } = luxon;

const BUS_CHANNEL = "hosny.attendance.timeline";
const BUS_EVENT = "hosny_attendance_timeline/changed";
const LIVE_REFRESH_DELAY = 350;
const POLLING_INTERVAL = 60000;
const EMPTY_EMPLOYEE_FILTERS = Object.freeze({
    departmentId: "",
    workLocationId: "",
    checkedIn: false,
    late: false,
    missingCheckout: false,
    overtime: false,
    attendanceToday: false,
});

export class AttendanceTimelineController extends Component {
    static components = {
        CogMenu,
        Layout,
        SearchBar,
    };
    static template =
        "hosny_attendance_timeline.AttendanceTimelineView";
    static props = {
        ...standardViewProps,
        archInfo: Object,
        Renderer: Function,
        buttonTemplate: String,
    };

    setup() {
        this.rootRef = useRef("root");
        this.employeeSearchRef = useRef("employeeSearch");
        this.direction = localization.direction;
        this.orm = useService("orm");
        // Unprotected orm: dialog callbacks are owned by the dialog service and
        // can run after this controller is destroyed, in which case the
        // protected orm rejects with "Component is destroyed" instead of
        // performing the write the user just confirmed.
        this.rawOrm = this.env.services.orm;
        this.actionService = useService("action");
        this.dialogService = useService("dialog");
        this.notification = useService("notification");
        this.busService = useService("bus_service");
        this.searchBarToggler = useSearchBarToggler();

        const restoredState = this.props.state || {};
        const restoredScale = ["day", "week", "month"].includes(
            restoredState.scale
        )
            ? restoredState.scale
            : "month";
        const restoredDate = DateTime.fromISO(
            restoredState.focusDate || ""
        );
        this.state = useState({
            focusDate: restoredDate.isValid
                ? restoredDate.toISODate()
                : DateTime.now().toISODate(),
            scale: restoredScale,
            zoom: Math.max(
                0.6,
                Math.min(2, restoredState.zoom || 1)
            ),
            employees: [],
            attendanceByEmployee: {},
            workLocationOptions: [],
            permissions: {
                create: false,
                write: false,
                unlink: false,
            },
            loadingEmployees: true,
            contextMenu: null,
            employeeContextMenu: null,
            employeeSearch: "",
            employeeFilters: { ...EMPTY_EMPLOYEE_FILTERS },
            filterOpen: false,
            selectedEmployeeIds:
                restoredState.selectedEmployeeIds || [],
            selectionAnchorId:
                restoredState.selectionAnchorId || false,
            focusedEmployeeId:
                restoredState.focusedEmployeeId || false,
        });

        this.initialScrollTop = restoredState.scrollTop || 0;
        this.scrollTop = this.initialScrollTop;
        this.activeDomain = this.props.domain;
        this.activeContext = this.props.context;
        this.visibleEmployeeIds = [];
        this.loadedEmployeeIds = new Set();
        this.loadingEmployeeIds = new Set();
        this.dataVersion = 0;
        this.liveRefreshTimer = null;
        this.filteredEmployeeCache = null;
        this.onBusNotification = () => this.scheduleLiveRefresh();
        this.rendererCallbacks = {
            onVisibleEmployees: (employeeIds) =>
                this.onVisibleEmployees(employeeIds),
            onOpenAttendance: (attendance) =>
                this.openAttendance(attendance),
            onOpenAttendanceGroup: (attendances) =>
                this.openAttendanceGroup(attendances),
            onCreateAttendance: (employee, dateTime) =>
                this.createAttendance(employee, dateTime),
            onUpdateAttendance: (attendance, values) =>
                this.updateAttendance(attendance, values),
            onContextMenu: (attendance, event) =>
                this.openContextMenu(attendance, event),
            onEmployeeSelect: (employee, event) =>
                this.selectEmployee(employee, event),
            onEmployeeOpen: (employee) =>
                this.openEmployee(employee),
            onEmployeeContextMenu: (employee, event) =>
                this.openEmployeeContextMenu(employee, event),
            onScrollPosition: (scrollTop) => {
                this.scrollTop = scrollTop;
            },
        };

        this.busService.addChannel(BUS_CHANNEL);
        this.busService.subscribe(
            BUS_EVENT,
            this.onBusNotification
        );
        this.pollingTimer = browser.setInterval(
            () => this.safeRefreshDashboard(),
            POLLING_INTERVAL
        );

        useExternalListener(window, "click", () => {
            this.state.contextMenu = null;
            this.state.employeeContextMenu = null;
            this.state.filterOpen = false;
        });
        useExternalListener(window, "keydown", (event) =>
            this.onGlobalKeydown(event)
        );

        onWillStart(() =>
            this.loadEmployees(this.props).catch((error) =>
                this.ignoreDestroyedError(error)
            )
        );
        onWillUpdateProps((nextProps) => {
            const currentKey = JSON.stringify({
                domain: this.activeDomain,
                context: this.activeContext,
            });
            const nextKey = JSON.stringify({
                domain: nextProps.domain,
                context: nextProps.context,
            });
            if (currentKey !== nextKey) {
                return this.loadEmployees(nextProps).catch(
                    (error) => this.ignoreDestroyedError(error)
                );
            }
        });
        // onWillDestroy, not onWillUnmount: a controller destroyed before it
        // was ever mounted (action switched while onWillStart is pending)
        // never unmounts, and would keep polling forever.
        onWillDestroy(() => {
            this.busService.unsubscribe(
                BUS_EVENT,
                this.onBusNotification
            );
            this.busService.deleteChannel(BUS_CHANNEL);
            browser.clearInterval(this.pollingTimer);
            browser.clearTimeout(this.liveRefreshTimer);
        });

        useSetupAction({
            rootRef: this.rootRef,
            getLocalState: () => ({
                focusDate: this.state.focusDate,
                scale: this.state.scale,
                zoom: this.state.zoom,
                scrollTop: this.scrollTop,
                selectedEmployeeIds:
                    this.state.selectedEmployeeIds,
                selectionAnchorId:
                    this.state.selectionAnchorId,
                focusedEmployeeId:
                    this.state.focusedEmployeeId,
            }),
        });
    }

    get range() {
        return getTimelineRange(
            this.state.focusDate,
            this.state.scale
        );
    }

    get hourWidth() {
        return (
            BASE_HOUR_WIDTHS[this.state.scale] * this.state.zoom
        );
    }

    get rangeLabel() {
        const { start, end } = this.range;
        if (this.state.scale === "day") {
            return start.toLocaleString(DateTime.DATE_HUGE);
        }
        if (this.state.scale === "month") {
            return start.toLocaleString({
                month: "long",
                year: "numeric",
            });
        }
        return `${start.toLocaleString(
            DateTime.DATE_MED_WITH_WEEKDAY
        )} – ${end
            .minus({ days: 1 })
            .toLocaleString(DateTime.DATE_MED_WITH_WEEKDAY)}`;
    }

    get canCreate() {
        return (
            this.props.archInfo.activeActions.create &&
            this.state.permissions.create
        );
    }

    get filteredEmployees() {
        if (
            !this.filteredEmployeeCache ||
            this.filteredEmployeeCache.employees !==
                this.state.employees ||
            this.filteredEmployeeCache.query !==
                this.state.employeeSearch ||
            this.filteredEmployeeCache.filters !==
                this.state.employeeFilters
        ) {
            this.filteredEmployeeCache = {
                employees: this.state.employees,
                query: this.state.employeeSearch,
                filters: this.state.employeeFilters,
                value: filterTimelineEmployees(
                    this.state.employees,
                    this.state.employeeSearch,
                    this.state.employeeFilters
                ),
            };
        }
        return this.filteredEmployeeCache.value;
    }

    get activeFilterCount() {
        return Object.values(
            this.state.employeeFilters
        ).filter(Boolean).length;
    }

    get hasEmployeeQuery() {
        return Boolean(
            this.state.employeeSearch.trim() ||
                this.activeFilterCount
        );
    }

    get departmentOptions() {
        return this.getMany2OneOptions("department");
    }

    get workLocationOptions() {
        return this.state.workLocationOptions.length
            ? this.state.workLocationOptions
            : this.getMany2OneOptions("work_location");
    }

    getMany2OneOptions(fieldName) {
        const options = new Map();
        for (const employee of this.state.employees) {
            const value = employee[fieldName];
            if (value) {
                const key = String(value.filter_key || value.id);
                if (!options.has(key)) {
                    options.set(key, {
                        ...value,
                        filter_key: key,
                    });
                }
            }
        }
        return [...options.values()].sort((left, right) =>
            left.name.localeCompare(right.name)
        );
    }

    get rendererProps() {
        const { start, end } = this.range;
        return {
            employees: this.filteredEmployees,
            totalEmployees: this.state.employees.length,
            attendanceByEmployee:
                this.state.attendanceByEmployee,
            groupBy: this.props.groupBy,
            rangeStart: start,
            rangeEnd: end,
            hourWidth: this.hourWidth,
            scale: this.state.scale,
            loading: this.state.loadingEmployees,
            initialScrollTop: this.initialScrollTop,
            selectedEmployeeIds:
                this.state.selectedEmployeeIds,
            focusedEmployeeId:
                this.state.focusedEmployeeId,
            searchQuery: this.state.employeeSearch,
            hasEmployeeQuery: this.hasEmployeeQuery,
            ...this.rendererCallbacks,
        };
    }

    get isDestroyed() {
        return status(this) === "destroyed";
    }

    /**
     * The orm service is protected by `useService`: once the controller is
     * destroyed every call rejects with "Component is destroyed". Deferred
     * refreshes (polling, bus notifications, dialog callbacks) can outlive the
     * controller, so those rejections are expected and must not bubble up as
     * an uncaught promise error.
     */
    ignoreDestroyedError(error) {
        if (
            this.isDestroyed ||
            error?.message === "Component is destroyed"
        ) {
            return;
        }
        throw error;
    }

    async loadEmployees(props, { silent = false } = {}) {
        if (this.isDestroyed) {
            return;
        }
        this.activeDomain = props.domain;
        this.activeContext = props.context;
        if (!silent) {
            this.state.loadingEmployees = true;
        }
        const version = ++this.dataVersion;
        this.loadedEmployeeIds.clear();
        this.loadingEmployeeIds.clear();
        if (!silent) {
            this.state.attendanceByEmployee = {};
        }
        try {
            const result = await this.orm.call(
                "hr.attendance",
                "get_timeline_employees",
                [props.domain, this.state.focusDate],
                { context: props.context }
            );
            if (version !== this.dataVersion || this.isDestroyed) {
                return;
            }
            this.state.employees = result.employees;
            this.state.workLocationOptions = result.work_location_options || [];
            this.state.permissions = result.permissions;
            const employeeIds = new Set(
                result.employees.map((employee) => employee.id)
            );
            this.state.selectedEmployeeIds =
                this.state.selectedEmployeeIds.filter(
                    (employeeId) => employeeIds.has(employeeId)
                );
            if (
                this.state.focusedEmployeeId &&
                !employeeIds.has(this.state.focusedEmployeeId)
            ) {
                this.state.focusedEmployeeId = false;
            }
            await this.fetchAttendances(
                this.visibleEmployeeIds.filter((employeeId) =>
                    employeeIds.has(employeeId)
                )
            );
        } finally {
            if (
                version === this.dataVersion &&
                !silent &&
                !this.isDestroyed
            ) {
                this.state.loadingEmployees = false;
            }
        }
    }

    onVisibleEmployees(employeeIds) {
        this.visibleEmployeeIds = employeeIds;
        this.fetchAttendances(employeeIds).catch((error) =>
            this.ignoreDestroyedError(error)
        );
    }

    async fetchAttendances(employeeIds) {
        if (this.isDestroyed) {
            return;
        }
        const requestedIds = employeeIds
            .filter(
                (employeeId) =>
                    !this.loadedEmployeeIds.has(employeeId) &&
                    !this.loadingEmployeeIds.has(employeeId)
            )
            .slice(0, 200);
        if (!requestedIds.length) {
            return;
        }
        const version = this.dataVersion;
        for (const employeeId of requestedIds) {
            this.loadingEmployeeIds.add(employeeId);
        }
        const { start, end } = this.range;
        try {
            const result = await this.orm.call(
                "hr.attendance",
                "get_timeline_attendances",
                [
                    this.activeDomain,
                    serializeDateTime(start),
                    serializeDateTime(end),
                    requestedIds,
                ],
                { context: this.activeContext }
            );
            if (version !== this.dataVersion || this.isDestroyed) {
                return;
            }
            const attendanceUpdates = {};
            for (const employeeId of requestedIds) {
                const nextAttendances = result[employeeId] || [];
                const currentAttendances =
                    this.state.attendanceByEmployee[
                        employeeId
                    ] || [];
                if (
                    nextAttendances.length ||
                    currentAttendances.length
                ) {
                    attendanceUpdates[employeeId] =
                        nextAttendances;
                }
            }
            if (Object.keys(attendanceUpdates).length) {
                this.state.attendanceByEmployee = {
                    ...this.state.attendanceByEmployee,
                    ...attendanceUpdates,
                };
            }
            for (const employeeId of requestedIds) {
                this.loadedEmployeeIds.add(employeeId);
            }
        } finally {
            for (const employeeId of requestedIds) {
                this.loadingEmployeeIds.delete(employeeId);
            }
        }
    }

    reloadVisibleAttendances() {
        this.dataVersion += 1;
        this.loadedEmployeeIds.clear();
        this.loadingEmployeeIds.clear();
        this.state.attendanceByEmployee = {};
        return this.fetchAttendances(
            this.visibleEmployeeIds
        ).catch((error) => this.ignoreDestroyedError(error));
    }

    scheduleLiveRefresh() {
        if (this.isDestroyed) {
            return;
        }
        browser.clearTimeout(this.liveRefreshTimer);
        this.liveRefreshTimer = browser.setTimeout(
            () => this.safeRefreshDashboard(),
            LIVE_REFRESH_DELAY
        );
    }

    refreshDashboard() {
        if (this.isDestroyed) {
            return Promise.resolve();
        }
        return this.loadEmployees(
            {
                domain: this.activeDomain,
                context: this.activeContext,
            },
            { silent: true }
        );
    }

    reloadTimelineData() {
        return this.loadEmployees({
            domain: this.activeDomain,
            context: this.activeContext,
        }).catch((error) => this.ignoreDestroyedError(error));
    }

    /**
     * Refresh triggered by something that can outlive the controller (timer,
     * bus notification, dialog callback): never let it crash the client.
     */
    safeRefreshDashboard() {
        return this.refreshDashboard().catch((error) =>
            this.ignoreDestroyedError(error)
        );
    }

    changeScale(scale) {
        if (this.state.scale === scale) {
            return;
        }
        this.state.scale = scale;
        this.initialScrollTop = 0;
        this.reloadTimelineData();
    }

    navigate(direction) {
        const date = DateTime.fromISO(this.state.focusDate);
        const delta =
            this.state.scale === "month"
                ? { months: direction }
                : this.state.scale === "week"
                  ? { days: 7 * direction }
                  : { days: direction };
        this.state.focusDate = date.plus(delta).toISODate();
        this.reloadTimelineData();
    }

    goToday() {
        this.state.focusDate = DateTime.now().toISODate();
        this.reloadTimelineData();
    }

    onDateChanged(event) {
        const date = DateTime.fromISO(event.target.value);
        if (date.isValid) {
            this.state.focusDate = date.toISODate();
            this.reloadTimelineData();
        }
    }

    changeZoom(delta) {
        this.state.zoom = Math.max(
            0.6,
            Math.min(2, this.state.zoom + delta)
        );
    }

    onEmployeeSearchInput(event) {
        this.state.employeeSearch = event.target.value;
        this.state.contextMenu = null;
        this.state.employeeContextMenu = null;
    }

    clearEmployeeSearch() {
        this.state.employeeSearch = "";
        this.employeeSearchRef.el?.focus();
    }

    toggleFilterPanel(event) {
        event.stopPropagation();
        this.state.filterOpen = !this.state.filterOpen;
        this.state.contextMenu = null;
        this.state.employeeContextMenu = null;
    }

    setEmployeeFilter(filterName, value) {
        this.state.employeeFilters = {
            ...this.state.employeeFilters,
            [filterName]: value,
        };
    }

    toggleEmployeeFilter(filterName, event) {
        this.setEmployeeFilter(
            filterName,
            event.target.checked
        );
    }

    resetEmployeeFilters() {
        this.state.employeeFilters = {
            ...EMPTY_EMPLOYEE_FILTERS,
        };
    }

    clearEmployeeSelection() {
        this.state.selectedEmployeeIds = [];
        this.state.selectionAnchorId = false;
        this.state.focusedEmployeeId = false;
    }

    selectEmployee(employee, event = {}) {
        const orderedIds = this.filteredEmployees.map(
            (item) => item.id
        );
        const selection = getTimelineSelection(
            orderedIds,
            this.state.selectedEmployeeIds,
            employee.id,
            {
                toggle: Boolean(event.ctrlKey || event.metaKey),
                range: Boolean(event.shiftKey),
                anchorId: this.state.selectionAnchorId,
            }
        );
        this.state.selectedEmployeeIds =
            selection.selectedIds;
        this.state.selectionAnchorId = selection.anchorId;
        this.state.focusedEmployeeId = employee.id;
        this.scrollEmployeeIntoView(employee.id, {
            focus: event.detail === 0,
        });
    }

    scrollEmployeeIntoView(employeeId, { focus = false } = {}) {
        const scrollElement =
            this.rootRef.el?.querySelector(".o_at_scroll");
        if (!scrollElement) {
            return;
        }
        const rows = buildTimelineRows(
            this.filteredEmployees,
            this.props.groupBy
        );
        const rowIndex = rows.findIndex(
            (row) =>
                row.type === "employee" &&
                row.employee.id === employeeId
        );
        if (rowIndex < 0) {
            return;
        }
        const rowTop =
            TIMELINE_HEADER_HEIGHT +
            rowIndex * TIMELINE_ROW_HEIGHT;
        const rowBottom = rowTop + TIMELINE_ROW_HEIGHT;
        const visibleTop =
            scrollElement.scrollTop +
            TIMELINE_HEADER_HEIGHT;
        const visibleBottom =
            scrollElement.scrollTop +
            scrollElement.clientHeight;
        let targetTop = scrollElement.scrollTop;
        if (rowTop < visibleTop) {
            targetTop = Math.max(
                0,
                rowTop - TIMELINE_HEADER_HEIGHT
            );
        } else if (rowBottom > visibleBottom) {
            targetTop =
                rowBottom - scrollElement.clientHeight;
        }
        if (targetTop !== scrollElement.scrollTop) {
            scrollElement.scrollTo({
                top: targetTop,
                behavior: "smooth",
            });
        }
        if (focus) {
            browser.requestAnimationFrame(() =>
                browser.requestAnimationFrame(() =>
                    this.rootRef.el
                        ?.querySelector(
                            `[data-employee-row-id="${employeeId}"]`
                        )
                        ?.focus({ preventScroll: true })
                )
            );
        }
    }

    onGlobalKeydown(event) {
        if (!this.rootRef.el?.isConnected) {
            return;
        }
        if (
            (event.ctrlKey || event.metaKey) &&
            event.key.toLocaleLowerCase() === "f"
        ) {
            event.preventDefault();
            this.employeeSearchRef.el?.focus();
            this.employeeSearchRef.el?.select();
            return;
        }
        if (event.key === "Escape") {
            this.state.contextMenu = null;
            this.state.employeeContextMenu = null;
            this.state.filterOpen = false;
            this.clearEmployeeSelection();
            return;
        }
        const target = event.target;
        if (
            target?.matches?.(
                "input, textarea, select, [contenteditable='true']"
            ) ||
            target?.closest?.(".modal, .o_dialog")
        ) {
            return;
        }
        if (
            event.key === "ArrowDown" ||
            event.key === "ArrowUp"
        ) {
            event.preventDefault();
            this.moveEmployeeSelection(
                event.key === "ArrowDown" ? 1 : -1
            );
        } else if (
            event.key === "Enter" &&
            this.state.focusedEmployeeId
        ) {
            const employee = this.state.employees.find(
                (item) =>
                    item.id === this.state.focusedEmployeeId
            );
            if (employee) {
                event.preventDefault();
                this.openEmployee(employee);
            }
        }
    }

    moveEmployeeSelection(direction) {
        const employees = this.filteredEmployees;
        if (!employees.length) {
            return;
        }
        const currentIndex = employees.findIndex(
            (employee) =>
                employee.id === this.state.focusedEmployeeId
        );
        const nextIndex =
            currentIndex < 0
                ? direction > 0
                    ? 0
                    : employees.length - 1
                : Math.max(
                      0,
                      Math.min(
                          employees.length - 1,
                          currentIndex + direction
                      )
                  );
        const employee = employees[nextIndex];
        this.state.selectedEmployeeIds = [employee.id];
        this.state.selectionAnchorId = employee.id;
        this.state.focusedEmployeeId = employee.id;
        this.scrollEmployeeIntoView(employee.id, {
            focus: true,
        });
    }

    openEmployee(employee) {
        this.state.employeeContextMenu = null;
        if (!employee.can_open) {
            return;
        }
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.employee",
            res_id: employee.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    viewEmployeeAttendanceHistory(employee) {
        this.state.employeeContextMenu = null;
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Attendance History: %s", employee.name),
            res_model: "hr.attendance",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [["employee_id", "=", employee.id]],
            context: this.activeContext,
            target: "current",
        });
    }

    createEmployeeAttendance(employee) {
        this.state.employeeContextMenu = null;
        const now = DateTime.now();
        const focusDate = DateTime.fromISO(
            this.state.focusDate
        );
        const dateTime = focusDate.hasSame(now, "day")
            ? now
            : focusDate.set({
                  hour: now.hour,
                  minute: now.minute,
                  second: 0,
                  millisecond: 0,
              });
        this.createAttendance(employee, dateTime);
    }

    confirmEmployeeAttendanceAction(employee, action) {
        this.state.employeeContextMenu = null;
        const checkingIn = action === "check_in";
        this.dialogService.add(ConfirmationDialog, {
            title: checkingIn ? _t("Check In") : _t("Check Out"),
            body: checkingIn
                ? _t("Check in %s now?", employee.name)
                : _t("Check out %s now?", employee.name),
            confirm: async () => {
                try {
                    await this.rawOrm.call(
                        "hr.attendance",
                        "timeline_toggle_employee_attendance",
                        [employee.id, action],
                        { context: this.activeContext }
                    );
                    this.notification.add(
                        checkingIn
                            ? _t("%s checked in.", employee.name)
                            : _t("%s checked out.", employee.name),
                        { type: "success" }
                    );
                    await this.safeRefreshDashboard();
                } catch (error) {
                    this.notification.add(
                        error.message ||
                            _t(
                                "The attendance status could not be changed."
                            ),
                        {
                            title: _t(
                                "Attendance action failed"
                            ),
                            type: "danger",
                        }
                    );
                    await this.safeRefreshDashboard();
                }
            },
            cancel: () => {},
        });
    }

    openAttendance(attendance) {
        this.state.contextMenu = null;
        const activeIds = Object.values(
            this.state.attendanceByEmployee
        )
            .flat()
            .map((record) => record.id);
        if (this.props.selectRecord) {
            return this.props.selectRecord(attendance.id, {
                activeIds,
            });
        }
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "hr.attendance",
            res_id: attendance.id,
            views: [[false, "form"]],
        });
    }

    openAttendanceGroup(attendances) {
        if (attendances.length === 1) {
            return this.openAttendance(attendances[0]);
        }
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Attendance"),
            res_model: "hr.attendance",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                [
                    "id",
                    "in",
                    attendances.map(
                        (attendance) => attendance.id
                    ),
                ],
            ],
            context: this.activeContext,
            target: "current",
        });
    }

    editAttendance(attendance) {
        this.state.contextMenu = null;
        this.dialogService.add(FormViewDialog, {
            resModel: "hr.attendance",
            resId: attendance.id,
            title: _t("Edit Attendance"),
            size: "lg",
            context: this.activeContext,
            onRecordSaved: () =>
                this.safeRefreshDashboard(),
        });
    }

    createAttendance(employee, dateTime, source = null) {
        this.state.contextMenu = null;
        if (!this.canCreate) {
            return;
        }
        const context = {
            ...this.activeContext,
            default_employee_id: employee.id,
            default_check_in: serializeDateTime(dateTime),
        };
        if (source?.check_out) {
            context.default_check_out = source.check_out;
        } else if (source) {
            delete context.default_check_out;
        } else {
            context.default_check_out = serializeDateTime(
                dateTime.plus({ hours: 1 })
            );
        }
        this.dialogService.add(FormViewDialog, {
            resModel: "hr.attendance",
            resId: false,
            title: source
                ? _t("Duplicate Attendance")
                : _t("New Attendance"),
            size: "lg",
            context,
            onRecordSaved: () =>
                this.safeRefreshDashboard(),
        });
    }

    duplicateAttendance(attendance) {
        const employee = this.state.employees.find(
            (item) => item.id === attendance.employee_id
        );
        if (!employee) {
            return;
        }
        const dateTime = DateTime.fromSQL(attendance.check_in, {
            zone: "utc",
        }).setZone("default");
        this.createAttendance(employee, dateTime, attendance);
    }

    async updateAttendance(attendance, values) {
        if (!attendance.can_write) {
            return false;
        }
        try {
            await this.orm.write(
                "hr.attendance",
                [attendance.id],
                values,
                { context: this.activeContext }
            );
            await this.safeRefreshDashboard();
            return true;
        } catch (error) {
            this.notification.add(
                error.message || _t("The attendance could not be updated."),
                {
                    title: _t("Attendance update failed"),
                    type: "danger",
                }
            );
            await this.safeRefreshDashboard();
            return false;
        }
    }

    deleteAttendance(attendance) {
        this.state.contextMenu = null;
        if (!attendance.can_unlink) {
            return;
        }
        this.dialogService.add(ConfirmationDialog, {
            title: _t("Delete Attendance"),
            body: _t(
                "Are you sure you want to delete this attendance?"
            ),
            confirm: async () => {
                try {
                    await this.rawOrm.unlink(
                        "hr.attendance",
                        [attendance.id],
                        { context: this.activeContext }
                    );
                    await this.safeRefreshDashboard();
                } catch (error) {
                    this.notification.add(
                        error.message ||
                            _t(
                                "The attendance could not be deleted."
                            ),
                        {
                            title: _t(
                                "Attendance deletion failed"
                            ),
                            type: "danger",
                        }
                    );
                    await this.safeRefreshDashboard();
                }
            },
            cancel: () => {},
        });
    }

    openContextMenu(attendance, event) {
        event.preventDefault();
        event.stopPropagation();
        this.state.employeeContextMenu = null;
        const position = this.getContextMenuPosition(
            event,
            190,
            190
        );
        this.state.contextMenu = {
            attendance,
            ...position,
        };
    }

    openEmployeeContextMenu(employee, event) {
        event.preventDefault();
        event.stopPropagation();
        this.state.contextMenu = null;
        if (
            !this.state.selectedEmployeeIds.includes(employee.id)
        ) {
            this.state.selectedEmployeeIds = [employee.id];
            this.state.selectionAnchorId = employee.id;
        }
        this.state.focusedEmployeeId = employee.id;
        const position = this.getContextMenuPosition(
            event,
            250,
            260
        );
        this.state.employeeContextMenu = {
            employee,
            ...position,
        };
    }

    getContextMenuPosition(event, menuWidth, menuHeight) {
        const viewportWidth =
            document.documentElement.clientWidth;
        const viewportHeight =
            document.documentElement.clientHeight;
        return {
            x: Math.max(
                8,
                Math.min(event.clientX, viewportWidth - menuWidth)
            ),
            y: Math.max(
                8,
                Math.min(event.clientY, viewportHeight - menuHeight)
            ),
        };
    }

    onNewButtonClicked() {
        if (this.props.createRecord) {
            this.props.createRecord();
        }
    }
}
