import { describe, expect, test } from "@odoo/hoot";
import { mockTimeZone } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { localization } from "@web/core/l10n/localization";

import {
    TIMELINE_HEADER_HEIGHT,
    TIMELINE_OVERSCAN,
    TIMELINE_VIRTUALIZATION_THRESHOLD,
    TIMELINE_ROW_HEIGHT,
    buildTimelineRows,
    employeeMatchesTimelineSearch,
    filterTimelineEmployees,
    formatTimelineDuration,
    getFittedHourWidth,
    getBarGeometry,
    getMonthlyAttendanceCells,
    getTimelinePrefetchRange,
    getTimelineSelection,
    getTimelineRange,
    getTimelineSlots,
    getTimelineVirtualScrollTop,
    snapTimelineMinutes,
} from "@hosny_attendance_timeline/views/attendance_timeline/timeline_utils";

const { DateTime } = luxon;

describe.current.tags("desktop");

test("grid uses compact fixed row geometry", () => {
    expect(TIMELINE_ROW_HEIGHT).toBe(36);
    expect(TIMELINE_HEADER_HEIGHT).toBe(54);
    expect(TIMELINE_OVERSCAN).toBe(4);
    expect(TIMELINE_VIRTUALIZATION_THRESHOLD).toBe(200);
});

test("virtual scrolling batches rows and attendance prefetch", () => {
    expect(getTimelineVirtualScrollTop(0)).toBe(0);
    expect(getTimelineVirtualScrollTop(54)).toBe(0);
    expect(getTimelineVirtualScrollTop(89)).toBe(0);
    expect(getTimelineVirtualScrollTop(90)).toBe(0);
    expect(getTimelineVirtualScrollTop(197)).toBe(0);
    expect(getTimelineVirtualScrollTop(198)).toBe(198);
    expect(getTimelineVirtualScrollTop(341)).toBe(198);
    expect(getTimelineVirtualScrollTop(342)).toBe(342);
    expect(getTimelinePrefetchRange(0, 1000)).toEqual({
        start: 0,
        end: 200,
    });
    expect(getTimelinePrefetchRange(99, 1000)).toEqual({
        start: 0,
        end: 200,
    });
    expect(getTimelinePrefetchRange(100, 1000)).toEqual({
        start: 100,
        end: 300,
    });
    expect(getTimelinePrefetchRange(980, 1000)).toEqual({
        start: 900,
        end: 1000,
    });
});

test("day, week, and month ranges are exclusive and stable", () => {
    mockTimeZone("Etc/UTC");
    patchWithCleanup(localization, { weekStart: 1 });
    const day = getTimelineRange("2026-07-08", "day");
    const week = getTimelineRange("2026-07-08", "week");
    const month = getTimelineRange("2026-07-08", "month");

    expect(day.start.toISODate()).toBe("2026-07-08");
    expect(day.end.toISODate()).toBe("2026-07-09");
    expect(week.end.diff(week.start, "days").days).toBe(7);
    expect(month.start.toISODate()).toBe("2026-07-01");
    expect(month.end.toISODate()).toBe("2026-08-01");
});

test("hour columns use compact twelve-hour labels", () => {
    mockTimeZone("Etc/UTC");
    const rangeStart = DateTime.fromISO(
        "2026-07-08T00:00:00"
    );
    const slots = getTimelineSlots(
        rangeStart,
        rangeStart.plus({ days: 1 }),
        46,
        "day"
    );

    expect(slots.hours[0].label).toBe("12am");
    expect(slots.hours[1].label).toBe("1am");
    expect(slots.hours[12].label).toBe("12pm");
    expect(slots.hours[13].label).toBe("1pm");
    expect(slots.hours[23].label).toBe("11pm");
});

test("month scale renders one column for every calendar day", () => {
    mockTimeZone("Etc/UTC");
    const rangeStart = DateTime.fromISO(
        "2026-08-01T00:00:00"
    );
    const slots = getTimelineSlots(
        rangeStart,
        rangeStart.plus({ months: 1 }),
        44,
        "month"
    );

    expect(slots.days).toHaveLength(1);
    expect(slots.bands).toHaveLength(31);
    expect(slots.hours).toHaveLength(31);
    expect(slots.hours[0].label).toBe("1");
    expect(slots.hours[30].label).toBe("31");
    expect(slots.days[0].width).toBe(1364);
    expect(slots.highlightBands.length).toBeLessThan(31);
});

test("month attendance cells aggregate Odoo worked hours by day", () => {
    mockTimeZone("Etc/UTC");
    const rangeStart = DateTime.fromISO(
        "2026-08-01T00:00:00"
    );
    const cells = getMonthlyAttendanceCells(
        [
            {
                id: 1,
                check_in: "2026-08-01 08:00:00",
                worked_hours: 8,
                overtime_hours: 1,
                status: "completed",
            },
            {
                id: 2,
                check_in: "2026-08-01 18:00:00",
                worked_hours: 2,
                overtime_hours: 0.5,
                status: "partial",
            },
            {
                id: 3,
                check_in: "2026-08-03 09:00:00",
                worked_hours: 7.5,
                overtime_hours: 0,
                status: "completed",
            },
        ],
        rangeStart,
        rangeStart.plus({ months: 1 }),
        44
    );

    expect(cells).toHaveLength(2);
    expect(cells[0].attendances.map(({ id }) => id)).toEqual([
        1, 2,
    ]);
    expect(cells[0].workedHours).toBe(10);
    expect(cells[0].overtimeHours).toBe(1.5);
    expect(cells[0].status).toBe("partial");
    expect(cells[1].offset).toBe(88);
});

test("attendance geometry is clipped to the visible range", () => {
    mockTimeZone("Etc/UTC");
    const rangeStart = DateTime.fromISO(
        "2026-07-08T00:00:00"
    );
    const rangeEnd = rangeStart.plus({ days: 1 });
    const geometry = getBarGeometry(
        {
            check_in: "2026-07-07 22:00:00",
            check_out: "2026-07-08 03:30:00",
        },
        rangeStart,
        rangeEnd,
        40
    );

    expect(geometry.visible).toBe(true);
    expect(geometry.offset).toBe(0);
    expect(geometry.width).toBe(140);
});

test("drag deltas snap to fifteen minutes", () => {
    expect(snapTimelineMinutes(20, 40)).toBe(30);
    expect(snapTimelineMinutes(-9, 40)).toBe(-15);
});

test("timeline fills spare width without shrinking below its readable scale", () => {
    expect(getFittedHourWidth(24, 46, 1833, 236)).toBeCloseTo(
        66.54,
        { margin: 0.01 }
    );
    expect(getFittedHourWidth(168, 28, 1833, 236)).toBe(28);
    expect(getFittedHourWidth(24, 46, 0, 236)).toBe(46);
});

test("employee search and dashboard filters combine", () => {
    const employees = [
        {
            id: 1,
            name: "Ahmed Ali",
            barcode: "EMP-001",
            department: { id: 10, name: "Operations" },
            company: { id: 20, name: "Hosny" },
            work_location: {
                id: 30,
                name: "Jeddah",
                filter_key: "branch:jeddah",
            },
            job: { id: 40, name: "Supervisor" },
            is_checked_in: true,
            has_overtime: true,
        },
        {
            id: 2,
            name: "Mona",
            department: { id: 11, name: "Finance" },
            company: { id: 20, name: "Hosny" },
            is_checked_in: false,
            has_overtime: false,
        },
    ];
    expect(
        employeeMatchesTimelineSearch(employees[0], "emp-001")
    ).toBe(true);
    expect(
        filterTimelineEmployees(employees, "jeddah", {
            departmentId: "",
            workLocationId: "branch:jeddah",
            checkedIn: true,
            late: false,
            missingCheckout: false,
            overtime: true,
            attendanceToday: false,
        }).map((employee) => employee.id)
    ).toEqual([1]);
});

test("employee selection supports control and shift ranges", () => {
    const orderedIds = [1, 2, 3, 4];
    const toggled = getTimelineSelection(
        orderedIds,
        [1],
        3,
        { toggle: true, anchorId: 1 }
    );
    expect(toggled.selectedIds).toEqual([1, 3]);
    const ranged = getTimelineSelection(
        orderedIds,
        toggled.selectedIds,
        4,
        { range: true, anchorId: 1 }
    );
    expect(ranged.selectedIds).toEqual([1, 2, 3, 4]);
});

test("duration formatting uses hours and minutes", () => {
    expect(formatTimelineDuration(8.5)).toBe("08:30");
    expect(formatTimelineDuration(false)).toBe("—");
});

test("employee grouping adds fixed-height group rows", () => {
    const rows = buildTimelineRows(
        [
            {
                id: 1,
                name: "A",
                department: { id: 10, name: "Sales" },
            },
            {
                id: 2,
                name: "B",
                department: { id: 10, name: "Sales" },
            },
        ],
        ["department_id"]
    );
    expect(rows.map((row) => row.type)).toEqual([
        "group",
        "employee",
        "employee",
    ]);
});
