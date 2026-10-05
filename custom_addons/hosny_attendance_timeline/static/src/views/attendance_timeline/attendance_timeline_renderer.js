import {
    Component,
    onMounted,
    onPatched,
    onWillUnmount,
    useExternalListener,
    useRef,
    useState,
} from "@odoo/owl";

import { browser } from "@web/core/browser/browser";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { _t } from "@web/core/l10n/translation";

import {
    TIMELINE_HEADER_HEIGHT,
    TIMELINE_OVERSCAN,
    TIMELINE_ROW_HEIGHT,
    TIMELINE_SNAP_MINUTES,
    TIMELINE_VIRTUALIZATION_THRESHOLD,
    buildTimelineRows,
    formatTimelineDateTime,
    formatTimelineDuration,
    getFittedHourWidth,
    getBarGeometry,
    getEmployeeColor,
    getEmployeeInitials,
    getMonthlyAttendanceCells,
    getTimelineDateFromPointer,
    getTimelinePrefetchRange,
    getTimelineSlots,
    getTimelineVirtualScrollTop,
    snapTimelineMinutes,
} from "./timeline_utils";

const { DateTime } = luxon;
const EMPTY_ATTENDANCES = Object.freeze([]);

export class AttendanceTimelineRenderer extends Component {
    static template =
        "hosny_attendance_timeline.AttendanceTimelineRenderer";
    static props = {
        employees: Array,
        totalEmployees: Number,
        attendanceByEmployee: Object,
        groupBy: Array,
        rangeStart: Object,
        rangeEnd: Object,
        hourWidth: Number,
        scale: String,
        loading: Boolean,
        initialScrollTop: Number,
        selectedEmployeeIds: Array,
        focusedEmployeeId: {
            type: [Number, Boolean],
        },
        searchQuery: String,
        hasEmployeeQuery: Boolean,
        onVisibleEmployees: Function,
        onOpenAttendance: Function,
        onOpenAttendanceGroup: Function,
        onCreateAttendance: Function,
        onUpdateAttendance: Function,
        onContextMenu: Function,
        onEmployeeSelect: Function,
        onEmployeeOpen: Function,
        onEmployeeContextMenu: Function,
        onScrollPosition: Function,
    };

    setup() {
        this.scrollRef = useRef("scroll");
        this.state = useState({
            scrollTop: getTimelineVirtualScrollTop(
                this.props.initialScrollTop
            ),
            viewportHeight: 640,
            viewportWidth: 0,
            tooltip: null,
            employeePopover: null,
            interaction: null,
            preview: null,
        });
        this.isRTL = localization.direction === "rtl";
        this.lastVisibleKey = null;
        this.rowCache = null;
        this.monthCellCache = new Map();
        this.slotCache = null;
        this.resizeObserver = null;

        this.onPointerMoveBound =
            this.onPointerMove.bind(this);
        this.onPointerUpBound = this.onPointerUp.bind(this);
        this.onPointerCancelBound =
            this.cancelInteraction.bind(this);

        useExternalListener(window, "keydown", (event) => {
            if (event.key !== "Escape") {
                return;
            }
            if (this.state.interaction) {
                this.cancelInteraction();
            } else if (this.state.employeePopover) {
                this.closeEmployeePopover();
            }
        });
        useExternalListener(document, "pointerdown", (event) => {
            if (
                !this.state.employeePopover ||
                event.target.closest(".o_at_employee_popover") ||
                event.target.closest(".o_at_employee_cell")
            ) {
                return;
            }
            this.closeEmployeePopover();
        });

        onMounted(() => {
            const scrollElement = this.scrollRef.el;
            if (!scrollElement) {
                return;
            }
            scrollElement.scrollTop =
                this.props.initialScrollTop;
            this.state.viewportHeight =
                scrollElement.clientHeight || 640;
            this.state.viewportWidth =
                scrollElement.clientWidth;
            if (globalThis.ResizeObserver) {
                this.resizeObserver = new ResizeObserver(
                    ([entry]) => {
                        this.state.viewportHeight =
                            scrollElement.clientHeight ||
                            entry.contentRect.height;
                        this.state.viewportWidth =
                            scrollElement.clientWidth ||
                            entry.contentRect.width;
                    }
                );
                this.resizeObserver.observe(scrollElement);
            }
            this.notifyVisibleEmployees();
        });
        onPatched(() => this.notifyVisibleEmployees());
        onWillUnmount(() => {
            this.resizeObserver?.disconnect();
            this.removePointerListeners();
            document.body.classList.remove("o_at_dragging");
        });
    }

    get rows() {
        const groupByKey = (this.props.groupBy || []).join(
            "|"
        );
        if (
            !this.rowCache ||
            this.rowCache.employees !== this.props.employees ||
            this.rowCache.groupByKey !== groupByKey
        ) {
            this.rowCache = {
                employees: this.props.employees,
                groupByKey,
                value: buildTimelineRows(
                    this.props.employees,
                    this.props.groupBy
                ),
            };
        }
        return this.rowCache.value;
    }

    get timelineWidth() {
        return this.unitCount * this.gridWidth;
    }

    get employeeWidth() {
        return this.env.isSmall ? 180 : 268;
    }

    get rangeHours() {
        return this.props.rangeEnd.diff(
            this.props.rangeStart,
            "hours"
        ).hours;
    }

    get unitCount() {
        return this.props.scale === "month"
            ? this.props.rangeEnd.diff(
                  this.props.rangeStart,
                  "days"
              ).days
            : this.rangeHours;
    }

    get gridWidth() {
        return getFittedHourWidth(
            this.unitCount,
            this.props.hourWidth,
            this.state.viewportWidth,
            this.employeeWidth
        );
    }

    get hourWidth() {
        return this.props.scale === "month"
            ? this.gridWidth / 24
            : this.gridWidth;
    }

    get timelineVariables() {
        return `--o-at-employee-width:${this.employeeWidth}px;--o-at-timeline-width:${this.timelineWidth}px;--o-at-hour-width:${this.gridWidth}px;`;
    }

    get slots() {
        const key = [
            this.props.rangeStart.toMillis(),
            this.props.rangeEnd.toMillis(),
            this.gridWidth,
            this.props.scale,
        ].join("-");
        if (!this.slotCache || this.slotCache.key !== key) {
            this.slotCache = {
                key,
                value: getTimelineSlots(
                    this.props.rangeStart,
                    this.props.rangeEnd,
                    this.gridWidth,
                    this.props.scale
                ),
            };
        }
        return this.slotCache.value;
    }

    get viewportFirstIndex() {
        if (!this.isVirtualized) {
            return 0;
        }
        return Math.floor(
            Math.max(
                0,
                this.state.scrollTop - TIMELINE_HEADER_HEIGHT
            ) / TIMELINE_ROW_HEIGHT
        );
    }

    get firstVisibleIndex() {
        if (!this.isVirtualized) {
            return 0;
        }
        return Math.max(
            0,
            this.viewportFirstIndex - TIMELINE_OVERSCAN
        );
    }

    get lastVisibleIndex() {
        if (!this.isVirtualized) {
            return this.rows.length;
        }
        return Math.min(
            this.rows.length,
            this.firstVisibleIndex +
                Math.ceil(
                    this.state.viewportHeight /
                        TIMELINE_ROW_HEIGHT
                ) +
                TIMELINE_OVERSCAN * 2
        );
    }

    get visibleRows() {
        return this.rows.slice(
            this.firstVisibleIndex,
            this.lastVisibleIndex
        );
    }

    get isVirtualized() {
        return (
            this.rows.length >
            TIMELINE_VIRTUALIZATION_THRESHOLD
        );
    }

    get topSpacerHeight() {
        return this.firstVisibleIndex * TIMELINE_ROW_HEIGHT;
    }

    get bottomSpacerHeight() {
        return (
            (this.rows.length - this.lastVisibleIndex) *
            TIMELINE_ROW_HEIGHT
        );
    }

    get currentTimeStyle() {
        if (this.props.scale === "month") {
            return "display:none;";
        }
        const now = DateTime.now();
        if (
            now < this.props.rangeStart ||
            now >= this.props.rangeEnd
        ) {
            return "display:none;";
        }
        const offset =
            now.diff(this.props.rangeStart, "hours").hours *
            this.hourWidth;
        return `inset-inline-start:${offset}px;`;
    }

    onScroll(event) {
        const scrollElement = event.currentTarget;
        const virtualScrollTop =
            getTimelineVirtualScrollTop(
                scrollElement.scrollTop
            );
        if (
            this.isVirtualized &&
            virtualScrollTop !== this.state.scrollTop
        ) {
            this.state.scrollTop = virtualScrollTop;
        }
        if (
            scrollElement.clientHeight !==
            this.state.viewportHeight
        ) {
            this.state.viewportHeight =
                scrollElement.clientHeight;
        }
        this.props.onScrollPosition(scrollElement.scrollTop);
        if (this.state.tooltip) {
            this.state.tooltip = null;
        }
        if (this.state.employeePopover) {
            this.closeEmployeePopover();
        }
    }

    notifyVisibleEmployees() {
        const rows = this.rows;
        const { start, end } = getTimelinePrefetchRange(
            this.viewportFirstIndex,
            rows.length
        );
        const employeeIds = rows
            .slice(start, end)
            .filter((row) => row.type === "employee")
            .map((row) => row.employee.id);
        const key = employeeIds.join(",");
        if (key !== this.lastVisibleKey) {
            this.lastVisibleKey = key;
            this.props.onVisibleEmployees(employeeIds);
        }
    }

    attendancesFor(employeeId) {
        return (
            this.props.attendanceByEmployee[
                String(employeeId)
            ] || EMPTY_ATTENDANCES
        );
    }

    monthlyCellsFor(employeeId) {
        const attendances = this.attendancesFor(employeeId);
        const key = [
            this.props.rangeStart.toMillis(),
            this.props.rangeEnd.toMillis(),
            this.gridWidth,
        ].join("-");
        const cached = this.monthCellCache.get(employeeId);
        if (
            cached?.attendances === attendances &&
            cached.key === key
        ) {
            return cached.value;
        }
        const value = getMonthlyAttendanceCells(
            attendances,
            this.props.rangeStart,
            this.props.rangeEnd,
            this.gridWidth
        );
        this.monthCellCache.set(employeeId, {
            attendances,
            key,
            value,
        });
        return value;
    }

    dayBandStyle(day) {
        return `inset-inline-start:${day.offset}px;width:${day.width}px;`;
    }

    employeeAvatarStyle(employee) {
        return `background-color:${getEmployeeColor(employee)};`;
    }

    employeeInitials(employee) {
        return getEmployeeInitials(employee.name);
    }

    isEmployeeSelected(employee) {
        return this.props.selectedEmployeeIds.includes(
            employee.id
        );
    }

    rowClass(employee) {
        const classes = ["o_at_row"];
        if (this.isEmployeeSelected(employee)) {
            classes.push("o_at_row_selected");
        }
        if (this.props.focusedEmployeeId === employee.id) {
            classes.push("o_at_row_focused");
        }
        return classes.join(" ");
    }

    employeeStatusLabel(employee) {
        return {
            working: _t("Currently Checked In"),
            not_working: _t("Not Working"),
            incomplete: _t("Incomplete Attendance"),
            problem: _t("Attendance Problem"),
        }[employee.status] || _t("Not Working");
    }

    employeeNameParts(employee) {
        const name = employee.name || "";
        const query = this.props.searchQuery.trim();
        if (!query) {
            return [
                {
                    key: "name",
                    text: name,
                    match: false,
                },
            ];
        }
        const index = name
            .toLocaleLowerCase()
            .indexOf(query.toLocaleLowerCase());
        if (index < 0) {
            return [
                {
                    key: "name",
                    text: name,
                    match: false,
                },
            ];
        }
        return [
            {
                key: "before",
                text: name.slice(0, index),
                match: false,
            },
            {
                key: "match",
                text: name.slice(index, index + query.length),
                match: true,
            },
            {
                key: "after",
                text: name.slice(index + query.length),
                match: false,
            },
        ].filter((part) => part.text);
    }

    employeeAriaLabel(employee) {
        return [
            employee.name,
            employee.department?.name,
            employee.work_location?.name,
            this.employeeStatusLabel(employee),
        ]
            .filter(Boolean)
            .join(", ");
    }

    onEmployeeClick(employee, event) {
        this.props.onEmployeeSelect(employee, event);
    }

    onEmployeeCellClick(employee, event) {
        event.stopPropagation();
        this.props.onEmployeeSelect(employee, event);
        this.openEmployeePopover(
            employee,
            event.currentTarget
        );
    }

    onEmployeeDoubleClick(employee, event) {
        event.preventDefault();
        if (employee.can_open) {
            this.props.onEmployeeOpen(employee);
        }
    }

    onEmployeeKeydown(employee, event) {
        if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            this.props.onEmployeeSelect(employee, event);
            this.openEmployeePopover(
                employee,
                event.currentTarget.querySelector(
                    ".o_at_employee_cell"
                )
            );
        }
    }

    onEmployeeContextMenu(employee, event) {
        this.closeEmployeePopover();
        this.props.onEmployeeContextMenu(employee, event);
    }

    unassignedLabel() {
        return _t("Unassigned");
    }

    previewFor(attendance) {
        return this.state.preview?.id === attendance.id
            ? this.state.preview
            : null;
    }

    geometryFor(attendance) {
        return getBarGeometry(
            attendance,
            this.props.rangeStart,
            this.props.rangeEnd,
            this.hourWidth,
            DateTime.now(),
            this.previewFor(attendance)
        );
    }

    barStyle(attendance) {
        const geometry = this.geometryFor(attendance);
        if (!geometry.visible) {
            return "display:none;";
        }
        return `inset-inline-start:${geometry.offset}px;width:${geometry.width}px;`;
    }

    barClass(attendance) {
        const classes = [
            "o_at_block",
            `o_at_status_${attendance.status}`,
        ];
        if (!attendance.can_write) {
            classes.push("o_at_readonly");
        }
        if (this.state.preview?.id === attendance.id) {
            classes.push("o_at_block_preview");
        }
        return classes.join(" ");
    }

    monthCellClass(cell) {
        return [
            "o_at_month_cell",
            `o_at_status_${cell.status}`,
        ].join(" ");
    }

    monthCellStyle(cell) {
        return `inset-inline-start:${cell.offset + 2}px;width:${Math.max(4, cell.width - 4)}px;`;
    }

    monthCellLabel(cell) {
        return formatTimelineDuration(cell.workedHours);
    }

    monthCellTitle(cell) {
        return [
            cell.attendances[0]?.employee_name,
            cell.date.toLocaleString(DateTime.DATE_FULL),
            `${_t("Worked Time")}: ${formatTimelineDuration(
                cell.workedHours
            )}`,
            `${_t("Overtime")}: ${formatTimelineDuration(
                cell.overtimeHours
            )}`,
            `${_t("Attendance")}: ${cell.attendances.length}`,
        ]
            .filter(Boolean)
            .join("\n");
    }

    openMonthCell(cell, event) {
        event.preventDefault();
        event.stopPropagation();
        this.props.onOpenAttendanceGroup(cell.attendances);
    }

    onMonthCellKeydown(cell, event) {
        if (event.key === "Enter" || event.key === " ") {
            this.openMonthCell(cell, event);
        }
    }

    onMonthCellContextMenu(cell, event) {
        event.preventDefault();
        event.stopPropagation();
        if (cell.attendances.length === 1) {
            this.props.onContextMenu(
                cell.attendances[0],
                event
            );
        } else {
            this.props.onOpenAttendanceGroup(
                cell.attendances
            );
        }
    }

    attendanceTime(value) {
        return value
            ? deserializeDateTime(value).toLocaleString(
                  DateTime.TIME_24_SIMPLE
              )
            : _t("Currently working");
    }

    attendanceLabel(attendance) {
        const geometry = this.geometryFor(attendance);
        const checkIn = this.attendanceTime(
            attendance.check_in
        );
        if (geometry.width < 66) {
            return checkIn;
        }
        const checkOut = this.attendanceTime(
            attendance.check_out
        );
        if (geometry.width < 142) {
            return `${checkIn}–${checkOut}`;
        }
        return `${checkIn}–${checkOut} · ${formatTimelineDuration(
            attendance.worked_hours
        )}`;
    }

    attendanceTitle(attendance) {
        return [
            attendance.employee_name,
            `${_t("Check In")}: ${formatTimelineDateTime(
                attendance.check_in
            )}`,
            `${_t("Check Out")}: ${
                attendance.check_out
                    ? formatTimelineDateTime(
                          attendance.check_out
                      )
                    : _t("Currently working")
            }`,
            `${_t("Worked Time")}: ${formatTimelineDuration(
                attendance.worked_hours
            )}`,
        ].join("\n");
    }

    formatDateTime(value) {
        return formatTimelineDateTime(value);
    }

    formatDuration(value) {
        return formatTimelineDuration(value);
    }

    showTooltip(attendance, event) {
        if (this.state.interaction) {
            return;
        }
        const viewportWidth =
            document.documentElement.clientWidth;
        const viewportHeight =
            document.documentElement.clientHeight;
        const width = 292;
        const height = 242;
        const x = Math.max(
            8,
            Math.min(event.clientX + 14, viewportWidth - width)
        );
        const y =
            event.clientY + height + 16 < viewportHeight
                ? event.clientY + 12
                : Math.max(8, event.clientY - height);
        this.state.tooltip = {
            attendance,
            x,
            y,
        };
        this.closeEmployeePopover();
    }

    showKeyboardTooltip(attendance, event) {
        const rect =
            event.currentTarget.getBoundingClientRect();
        this.showTooltip(attendance, {
            clientX: rect.left + rect.width / 2,
            clientY: rect.top + rect.height,
        });
    }

    hideTooltip() {
        this.state.tooltip = null;
    }

    openEmployeePopover(employee, anchorElement) {
        if (this.state.interaction) {
            return;
        }
        const viewportWidth =
            document.documentElement.clientWidth;
        const viewportHeight =
            document.documentElement.clientHeight;
        const width = 310;
        const height = 286;
        const rect = anchorElement.getBoundingClientRect();
        const preferredX = this.isRTL
            ? rect.left - width - 12
            : rect.right + 12;
        const x = Math.max(
            8,
            Math.min(preferredX, viewportWidth - width)
        );
        const y = Math.max(
            8,
            Math.min(rect.top, viewportHeight - height)
        );
        this.state.employeePopover = {
            employee,
            x,
            y,
        };
        this.state.tooltip = null;
    }

    closeEmployeePopover() {
        this.state.employeePopover = null;
    }

    formatOptionalDateTime(value) {
        return value ? formatTimelineDateTime(value) : "—";
    }

    onBarKeydown(attendance, event) {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.props.onOpenAttendance(attendance);
        }
    }

    onBlockContextMenu(attendance, event) {
        this.hideTooltip();
        this.props.onContextMenu(attendance, event);
    }

    onTrackDoubleClick(employee, event) {
        event.stopPropagation();
        if (event.target.closest(".o_at_block")) {
            return;
        }
        const dateTime = getTimelineDateFromPointer(
            event.clientX,
            event.currentTarget.getBoundingClientRect(),
            this.props.rangeStart,
            this.hourWidth,
            this.isRTL
        );
        this.props.onCreateAttendance(employee, dateTime);
    }

    startInteraction(event, attendance, mode) {
        if (event.button !== 0) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        this.hideTooltip();
        if (
            this.env.isSmall ||
            !attendance.can_write
        ) {
            if (mode === "move") {
                this.props.onOpenAttendance(attendance);
            }
            return;
        }

        const start = deserializeDateTime(
            attendance.check_in
        );
        const end = attendance.check_out
            ? deserializeDateTime(attendance.check_out)
            : DateTime.now();
        this.state.interaction = {
            attendance,
            mode,
            originX: event.clientX,
            originStartMs: start.toMillis(),
            originEndMs: end.toMillis(),
            hadCheckOut: Boolean(attendance.check_out),
            moved: false,
        };
        this.state.preview = {
            id: attendance.id,
            startMs: start.toMillis(),
            endMs: end.toMillis(),
        };
        document.body.classList.add("o_at_dragging");
        browser.addEventListener(
            "pointermove",
            this.onPointerMoveBound,
            { capture: true }
        );
        browser.addEventListener(
            "pointerup",
            this.onPointerUpBound,
            { capture: true, once: true }
        );
        browser.addEventListener(
            "pointercancel",
            this.onPointerCancelBound,
            { capture: true, once: true }
        );
    }

    onPointerMove(event) {
        const interaction = this.state.interaction;
        if (!interaction) {
            return;
        }
        const physicalDelta =
            event.clientX - interaction.originX;
        if (
            !interaction.moved &&
            Math.abs(physicalDelta) < 4
        ) {
            return;
        }
        event.preventDefault();
        interaction.moved = true;
        const timelineDelta = this.isRTL
            ? -physicalDelta
            : physicalDelta;
        const minutes = snapTimelineMinutes(
            timelineDelta,
            this.hourWidth
        );
        const deltaMs = minutes * 60000;
        const rangeStartMs =
            this.props.rangeStart.toMillis();
        const rangeEndMs = this.props.rangeEnd.toMillis();
        const minimumDurationMs =
            TIMELINE_SNAP_MINUTES * 60000;
        let startMs = interaction.originStartMs;
        let endMs = interaction.originEndMs;

        if (interaction.mode === "move") {
            startMs += deltaMs;
            if (interaction.hadCheckOut) {
                endMs += deltaMs;
                if (startMs < rangeStartMs) {
                    endMs += rangeStartMs - startMs;
                    startMs = rangeStartMs;
                }
                if (endMs > rangeEndMs) {
                    startMs -= endMs - rangeEndMs;
                    endMs = rangeEndMs;
                }
            } else {
                startMs = Math.max(
                    rangeStartMs,
                    Math.min(
                        endMs - minimumDurationMs,
                        startMs
                    )
                );
            }
        } else if (interaction.mode === "resize-start") {
            startMs = Math.max(
                rangeStartMs,
                Math.min(
                    endMs - minimumDurationMs,
                    startMs + deltaMs
                )
            );
        } else {
            endMs = Math.max(
                startMs + minimumDurationMs,
                Math.min(
                    rangeEndMs,
                    endMs + deltaMs
                )
            );
        }
        this.state.preview = {
            id: interaction.attendance.id,
            startMs,
            endMs,
        };
    }

    async onPointerUp() {
        const interaction = this.state.interaction;
        if (!interaction) {
            return;
        }
        const preview = this.state.preview;
        this.removePointerListeners();
        document.body.classList.remove("o_at_dragging");
        this.state.interaction = null;
        if (!interaction.moved) {
            this.state.preview = null;
            if (interaction.mode === "move") {
                this.props.onOpenAttendance(
                    interaction.attendance
                );
            }
            return;
        }

        const values = {};
        if (
            interaction.mode === "move" ||
            interaction.mode === "resize-start"
        ) {
            values.check_in = serializeDateTime(
                DateTime.fromMillis(preview.startMs)
            );
        }
        if (
            interaction.mode === "resize-end" ||
            (interaction.mode === "move" &&
                interaction.hadCheckOut)
        ) {
            values.check_out = serializeDateTime(
                DateTime.fromMillis(preview.endMs)
            );
        }
        await this.props.onUpdateAttendance(
            interaction.attendance,
            values
        );
        this.state.preview = null;
    }

    cancelInteraction() {
        if (!this.state.interaction) {
            return;
        }
        this.removePointerListeners();
        document.body.classList.remove("o_at_dragging");
        this.state.interaction = null;
        this.state.preview = null;
    }

    removePointerListeners() {
        browser.removeEventListener(
            "pointermove",
            this.onPointerMoveBound,
            { capture: true }
        );
        browser.removeEventListener(
            "pointerup",
            this.onPointerUpBound,
            { capture: true }
        );
        browser.removeEventListener(
            "pointercancel",
            this.onPointerCancelBound,
            { capture: true }
        );
    }
}
