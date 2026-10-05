import {
    deserializeDateTime,
    formatDateTime,
    getStartOfLocalWeek,
} from "@web/core/l10n/dates";

const { DateTime } = luxon;

export const TIMELINE_ROW_HEIGHT = 36;
export const TIMELINE_HEADER_HEIGHT = 54;
export const TIMELINE_OVERSCAN = 4;
export const TIMELINE_SCROLL_BATCH_ROWS = 4;
export const TIMELINE_VIRTUALIZATION_THRESHOLD = 200;
export const TIMELINE_PREFETCH_SIZE = 200;
export const TIMELINE_PREFETCH_STEP = 100;
export const TIMELINE_SNAP_MINUTES = 15;

export const BASE_HOUR_WIDTHS = Object.freeze({
    day: 46,
    week: 28,
    month: 42,
});

export function normalizeTimelineSearch(value) {
    return String(value || "")
        .normalize("NFKD")
        .replace(/\p{M}/gu, "")
        .toLocaleLowerCase()
        .trim();
}

export function employeeMatchesTimelineSearch(employee, query) {
    const normalizedQuery = normalizeTimelineSearch(query);
    if (!normalizedQuery) {
        return true;
    }
    return [
        employee.name,
        employee.barcode,
        employee.employee_code,
        employee.department?.name,
        employee.work_location?.name,
        employee.job?.name,
        employee.company?.name,
    ].some((value) =>
        normalizeTimelineSearch(value).includes(normalizedQuery)
    );
}

export function filterTimelineEmployees(
    employees,
    query,
    filters
) {
    return employees.filter(
        (employee) =>
            employeeMatchesTimelineSearch(employee, query) &&
            (!filters.departmentId ||
                String(employee.department?.id || "") ===
                    filters.departmentId) &&
            (!filters.workLocationId ||
                String(
                    employee.work_location?.filter_key ||
                        employee.work_location?.id ||
                        ""
                ) ===
                    filters.workLocationId) &&
            (!filters.checkedIn || employee.is_checked_in) &&
            (!filters.late || employee.is_late) &&
            (!filters.missingCheckout ||
                employee.has_missing_checkout) &&
            (!filters.overtime || employee.has_overtime) &&
            (!filters.attendanceToday ||
                employee.has_attendance_today)
    );
}

export function getTimelineSelection(
    orderedIds,
    selectedIds,
    clickedId,
    { toggle = false, range = false, anchorId = false } = {}
) {
    const selected = new Set(selectedIds);
    if (range && anchorId && orderedIds.includes(anchorId)) {
        const start = orderedIds.indexOf(anchorId);
        const end = orderedIds.indexOf(clickedId);
        const rangeIds = orderedIds.slice(
            Math.min(start, end),
            Math.max(start, end) + 1
        );
        return {
            selectedIds: toggle
                ? [...new Set([...selected, ...rangeIds])]
                : rangeIds,
            anchorId,
        };
    }
    if (toggle) {
        if (selected.has(clickedId)) {
            selected.delete(clickedId);
        } else {
            selected.add(clickedId);
        }
        return {
            selectedIds: [...selected],
            anchorId: clickedId,
        };
    }
    return {
        selectedIds: [clickedId],
        anchorId: clickedId,
    };
}

export function getFittedHourWidth(
    rangeHours,
    minimumHourWidth,
    viewportWidth,
    employeeWidth
) {
    if (
        !Number.isFinite(rangeHours) ||
        rangeHours <= 0 ||
        !Number.isFinite(viewportWidth) ||
        viewportWidth <= 0
    ) {
        return minimumHourWidth;
    }
    const availableTimelineWidth = Math.max(
        0,
        viewportWidth - employeeWidth
    );
    return Math.max(
        minimumHourWidth,
        availableTimelineWidth / rangeHours
    );
}

export function getTimelineVirtualScrollTop(scrollTop) {
    const normalizedScrollTop = Math.max(
        0,
        Number(scrollTop) || 0
    );
    if (normalizedScrollTop <= TIMELINE_HEADER_HEIGHT) {
        return 0;
    }
    const rowIndex = Math.floor(
        (normalizedScrollTop - TIMELINE_HEADER_HEIGHT) /
            TIMELINE_ROW_HEIGHT
    );
    const batchedRowIndex =
        Math.floor(rowIndex / TIMELINE_SCROLL_BATCH_ROWS) *
        TIMELINE_SCROLL_BATCH_ROWS;
    return batchedRowIndex
        ? TIMELINE_HEADER_HEIGHT +
              batchedRowIndex * TIMELINE_ROW_HEIGHT
        : 0;
}

export function getTimelinePrefetchRange(
    viewportFirstIndex,
    rowCount
) {
    const start = Math.max(
        0,
        Math.floor(
            Math.max(0, viewportFirstIndex) /
                TIMELINE_PREFETCH_STEP
        ) * TIMELINE_PREFETCH_STEP
    );
    return {
        start,
        end: Math.min(rowCount, start + TIMELINE_PREFETCH_SIZE),
    };
}

export function getTimelineRange(focusDate, scale) {
    const date = DateTime.fromISO(focusDate).startOf("day");
    if (scale === "week") {
        const start = getStartOfLocalWeek(date);
        return { start, end: start.plus({ days: 7 }) };
    }
    if (scale === "month") {
        const start = date.startOf("month");
        return { start, end: start.plus({ months: 1 }) };
    }
    return { start: date, end: date.plus({ days: 1 }) };
}

function getTimelineDateFormatter(date, options) {
    return new Intl.DateTimeFormat(date.locale || undefined, {
        timeZone: date.zoneName,
        numberingSystem: date.numberingSystem || undefined,
        ...options,
    });
}

function cleanTimelineDateLabel(value) {
    return value
        .replace(/[\s\u200e\u200f\u061c]+/g, "")
        .toLocaleLowerCase();
}

export function getTimelineSlots(
    rangeStart,
    rangeEnd,
    unitWidth,
    scale
) {
    if (scale === "month") {
        const bands = [];
        const hours = [];
        const dayNumberFormatter = getTimelineDateFormatter(
            rangeStart,
            { day: "numeric" }
        );
        const fullDateFormatter = getTimelineDateFormatter(
            rangeStart,
            { dateStyle: "full" }
        );
        let dayCursor = rangeStart.startOf("day");
        let index = 0;
        while (dayCursor < rangeEnd) {
            const isWeekend = dayCursor.weekday >= 6;
            const isToday = dayCursor.hasSame(
                DateTime.now(),
                "day"
            );
            const day = {
                key: dayCursor.toISODate(),
                date: dayCursor,
                offset: index * unitWidth,
                width: unitWidth,
                isWeekend,
                isToday,
            };
            bands.push(day);
            hours.push({
                ...day,
                label: dayNumberFormatter.format(
                    dayCursor.toJSDate()
                ),
                title: fullDateFormatter.format(
                    dayCursor.toJSDate()
                ),
            });
            dayCursor = dayCursor.plus({ days: 1 });
            index += 1;
        }
        return {
            days: [
                {
                    key: rangeStart.toFormat("yyyy-MM"),
                    date: rangeStart,
                    offset: 0,
                    width: bands.length * unitWidth,
                    isWeekend: false,
                    isToday: false,
                },
            ],
            hours,
            bands,
            highlightBands: bands.filter(
                (day) => day.isWeekend || day.isToday
            ),
        };
    }

    const days = [];
    let dayCursor = rangeStart.startOf("day");
    while (dayCursor < rangeEnd) {
        const dayEnd = DateTime.min(
            dayCursor.plus({ days: 1 }),
            rangeEnd
        );
        const visibleStart = DateTime.max(dayCursor, rangeStart);
        days.push({
            key: dayCursor.toISODate(),
            date: dayCursor,
            offset:
                visibleStart.diff(rangeStart, "hours").hours * unitWidth,
            width: dayEnd.diff(visibleStart, "hours").hours * unitWidth,
            isWeekend: dayCursor.weekday >= 6,
            isToday: dayCursor.hasSame(DateTime.now(), "day"),
        });
        dayCursor = dayCursor.plus({ days: 1 }).startOf("day");
    }

    const hours = [];
    const hourLabelFormatter = getTimelineDateFormatter(
        rangeStart,
        { hour: "numeric", hour12: true }
    );
    const hourTitleFormatter = getTimelineDateFormatter(
        rangeStart,
        {
            hour: "2-digit",
            minute: "2-digit",
            hourCycle: "h23",
        }
    );
    let hourCursor = rangeStart;
    let index = 0;
    while (hourCursor < rangeEnd) {
        const showLabel =
            scale === "day" ||
            (scale === "week" &&
                (unitWidth >= 24 || hourCursor.hour % 2 === 0));
        hours.push({
            key: `${hourCursor.toISO()}-${index}`,
            label: showLabel
                ? cleanTimelineDateLabel(
                      hourLabelFormatter.format(
                          hourCursor.toJSDate()
                      )
                  )
                : "",
            title: cleanTimelineDateLabel(
                hourTitleFormatter.format(
                    hourCursor.toJSDate()
                )
            ),
            width: unitWidth,
            isWeekend: hourCursor.weekday >= 6,
            isToday: hourCursor.hasSame(DateTime.now(), "day"),
        });
        hourCursor = hourCursor.plus({ hours: 1 });
        index += 1;
    }
    return {
        days,
        hours,
        bands: days,
        highlightBands: days,
    };
}

const MONTH_STATUS_PRIORITY = Object.freeze({
    completed: 1,
    partial: 2,
    active: 3,
    error: 4,
});

export function getMonthlyAttendanceCells(
    attendances,
    rangeStart,
    rangeEnd,
    dayWidth
) {
    const cellsByDate = new Map();
    for (const attendance of attendances || []) {
        const checkIn = deserializeDateTime(
            attendance.check_in
        );
        if (
            !checkIn.isValid ||
            checkIn < rangeStart ||
            checkIn >= rangeEnd
        ) {
            continue;
        }
        const day = checkIn.startOf("day");
        const key = day.toISODate();
        if (!cellsByDate.has(key)) {
            cellsByDate.set(key, {
                key,
                date: day,
                attendances: [],
                workedHours: 0,
                overtimeHours: 0,
                status: "completed",
            });
        }
        const cell = cellsByDate.get(key);
        cell.attendances.push(attendance);
        const workedHours = Number(attendance.worked_hours);
        const overtimeHours = Number(
            attendance.overtime_hours
        );
        if (Number.isFinite(workedHours)) {
            cell.workedHours += workedHours;
        }
        if (Number.isFinite(overtimeHours)) {
            cell.overtimeHours += overtimeHours;
        }
        if (
            (MONTH_STATUS_PRIORITY[attendance.status] || 0) >
            MONTH_STATUS_PRIORITY[cell.status]
        ) {
            cell.status = attendance.status;
        }
    }
    return [...cellsByDate.values()]
        .sort((left, right) => left.date - right.date)
        .map((cell) => ({
            ...cell,
            offset:
                cell.date.diff(rangeStart, "days").days *
                dayWidth,
            width: dayWidth,
        }));
}

export function getBarGeometry(
    attendance,
    rangeStart,
    rangeEnd,
    hourWidth,
    now = DateTime.now(),
    preview = null
) {
    const rawStart = preview
        ? DateTime.fromMillis(preview.startMs)
        : deserializeDateTime(attendance.check_in);
    const rawEnd = preview
        ? DateTime.fromMillis(preview.endMs)
        : attendance.check_out
          ? deserializeDateTime(attendance.check_out)
          : now;
    const visibleStart = DateTime.max(rawStart, rangeStart);
    const visibleEnd = DateTime.min(rawEnd, rangeEnd);
    if (
        !rawStart.isValid ||
        !rawEnd.isValid ||
        visibleEnd <= visibleStart
    ) {
        return {
            visible: false,
            offset: 0,
            width: 0,
            rawStart,
            rawEnd,
        };
    }
    return {
        visible: true,
        offset:
            visibleStart.diff(rangeStart, "hours").hours * hourWidth,
        width: Math.max(
            4,
            visibleEnd.diff(visibleStart, "hours").hours * hourWidth
        ),
        rawStart,
        rawEnd,
    };
}

export function getTimelineDateFromPointer(
    clientX,
    trackRect,
    rangeStart,
    hourWidth,
    isRTL
) {
    const offset = isRTL
        ? trackRect.right - clientX
        : clientX - trackRect.left;
    const clampedOffset = Math.max(
        0,
        Math.min(trackRect.width, offset)
    );
    const minutes = Math.round(
        (clampedOffset / hourWidth / TIMELINE_SNAP_MINUTES) * 60
    ) * TIMELINE_SNAP_MINUTES;
    return rangeStart.plus({ minutes });
}

export function snapTimelineMinutes(pixelDelta, hourWidth) {
    const rawMinutes = (pixelDelta / hourWidth) * 60;
    return (
        Math.round(rawMinutes / TIMELINE_SNAP_MINUTES) *
        TIMELINE_SNAP_MINUTES
    );
}

export function formatTimelineDuration(hours) {
    if (hours === false || hours === null || hours === undefined) {
        return "—";
    }
    const totalMinutes = Math.max(0, Math.round(hours * 60));
    const wholeHours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return `${String(wholeHours).padStart(2, "0")}:${String(
        minutes
    ).padStart(2, "0")}`;
}

export function formatTimelineDateTime(value) {
    return value
        ? formatDateTime(deserializeDateTime(value), {
              showSeconds: false,
          })
        : "—";
}

export function getEmployeeInitials(name) {
    const words = (name || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean);
    if (!words.length) {
        return "?";
    }
    return words
        .slice(0, 2)
        .map((word) => word[0])
        .join("")
        .toLocaleUpperCase();
}

export function getEmployeeColor(employee) {
    const palette = [
        "#3b82f6",
        "#16a34a",
        "#9333ea",
        "#db2777",
        "#0891b2",
        "#ca8a04",
        "#4f46e5",
        "#dc2626",
    ];
    const index = Number.isInteger(employee.color)
        ? employee.color
        : employee.id;
    return palette[Math.abs(index) % palette.length];
}

export function buildTimelineRows(employees, groupBy) {
    const requestedGroup = (groupBy || [])
        .map((item) => item.split(":")[0])
        .find((item) =>
            [
                "department_id",
                "company_id",
                "work_location_id",
                "attendance_manager_id",
                "manager_id",
            ].includes(item)
        );
    if (!requestedGroup) {
        return employees.map((employee) => ({
            key: `employee-${employee.id}`,
            type: "employee",
            employee,
        }));
    }
    const employeeField = {
        department_id: "department",
        company_id: "company",
        work_location_id: "work_location",
        attendance_manager_id: "attendance_manager",
        manager_id: "attendance_manager",
    }[requestedGroup];
    const groups = new Map();
    for (const employee of employees) {
        const value = employee[employeeField] || {
            id: false,
            name: "",
        };
        const key = value.id || "unassigned";
        if (!groups.has(key)) {
            groups.set(key, {
                name: value.name,
                employees: [],
            });
        }
        groups.get(key).employees.push(employee);
    }
    const rows = [];
    for (const [key, group] of groups) {
        rows.push({
            key: `group-${requestedGroup}-${key}`,
            type: "group",
            name: group.name,
            count: group.employees.length,
        });
        rows.push(
            ...group.employees.map((employee) => ({
                key: `employee-${employee.id}`,
                type: "employee",
                employee,
            }))
        );
    }
    return rows;
}
