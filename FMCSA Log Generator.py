"""Data models and FMCSA code mappings for ELD output files."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import csv
import argparse
from pathlib import Path
from typing import Optional


# These labels map to the one-character numeric codes used in FMCSA output.
# For event type 1, the duty status itself is carried in the event code.
DUTY_STATUS_CODES = {
    "off_duty": 1,
    "sleeper_berth": 2,
    "driving": 3,
    "on_duty_not_driving": 4,
}

# Appendix A, Table 8: whether each record is active or superseded/rejected.
EVENT_RECORD_STATUS_CODES = {
    "active": 1,
    "inactive_changed": 2,
    "inactive_change_requested": 3,
    "inactive_change_rejected": 4,
}

# Appendix A, Table 7: who or what created the event record.
EVENT_RECORD_ORIGIN_CODES = {
    "automatically_recorded_by_eld": 1,
    "edited_or_entered_by_driver": 2,
    "edit_requested_by_authenticated_non_driver": 3,
    "assumed_from_unidentified_driver_profile": 4,
}

# Appendix A, Table 6: event codes depend on the event type. Keys in this
# dictionary are the numeric event type; nested keys name its event codes.
EVENT_CODES = {
    1: {
        "off_duty": 1,
        "sleeper_berth": 2,
        "driving": 3,
        "on_duty_not_driving": 4,
    },
    2: {
        "intermediate_log_conventional_location_precision": 1,
        "intermediate_log_reduced_location_precision": 2,
    },
    3: {
        "authorized_personal_use_of_cmv": 1,
        "yard_moves": 2,
        "special_driving_category_cleared": 0,
    },
    4: {
        "first_certification": 1,
        "recertification": "n (1-9; use 9 for further recertifications)",
    },
    5: {
        "driver_login": 1,
        "driver_logout": 2,
    },
    6: {
        "engine_power_up_conventional_location_precision": 1,
        "engine_power_up_reduced_location_precision": 2,
        "engine_shutdown_conventional_location_precision": 3,
        "engine_shutdown_reduced_location_precision": 4,
    },
    7: {
        "malfunction_logged": 1,
        "malfunction_cleared": 2,
        "data_diagnostic_event_logged": 3,
        "data_diagnostic_event_cleared": 4,
    },
}

# Appendix A, Table 9: numeric codes identifying the kind of ELD event.
EVENT_TYPE_CODES = {
    "change_in_duty_status": 1,
    "intermediate_log": 2,
    "change_in_special_driving_category": 3,
    "driver_certification": 4,
    "driver_login_logout": 5,
    "engine_power_up_shutdown": 6,
    "malfunction_diagnostic": 7,
}


@dataclass(frozen=True)
class ELDEvent:
    """One row from the FMCSA ``ELD Event List`` output segment.

    Field order follows Appendix A, section 4.8.2.1.4. ``event_date`` and
    ``event_time`` are combined into ``event_datetime``; the raw date/time
    strings are retained by their parsed value only when needed for output.
    The event comment/annotation and driver location description are carried
    in the separate annotations/comments segment (section 4.8.2.1.5).
    """

    event_sequence_id_number: str
    event_record_status: int
    event_record_origin: int
    event_type: int
    event_code: int
    event_datetime: datetime
    accumulated_vehicle_miles: str
    elapsed_engine_hours: str
    event_latitude: str
    event_longitude: str
    distance_since_last_valid_coordinates: str
    corresponding_cmv_order_number: str
    record_originator_user_order_number: str
    eld_malfunction_indicator_status: int
    driver_data_diagnostic_event_indicator_status: int
    event_data_check_value: str
    line_data_check_value: str


@dataclass(frozen=True)
class DutyStatusInterval:
    """A duty-status span within one day's 24-hour timeline."""

    start_hour: float
    end_hour: float
    status: str


@dataclass(frozen=True)
class DailyEventRecord:
    """One timestamped ELD event row for the per-day event ledger."""

    timestamp: datetime
    category: str
    event: str
    sequence_id: str
    record_origin: str
    details: str


@dataclass(frozen=True)
class ELDParseResult:
    """Sections and parsed events found in an FMCSA ELD CSV output file."""

    sections: dict[str, tuple[tuple[str, ...], ...]]  # Raw rows, grouped by segment heading.
    events: list[ELDEvent]  # Parsed records in the order they appear in the file.
    missing_data: tuple[str, ...]  # Line-specific problems for review by the caller.


# 4.8.2.1.4 has 18 comma-separated fields; date and time become one datetime
# value in ELDEvent, leaving 17 dataclass attributes for those fields.
ELD_EVENT_FIELD_COUNT = 18


def read_eld_csv(csv_path: str | Path) -> ELDParseResult:
    """Read an FMCSA ELD output CSV, identify its sections, and parse its events.

    Empty rows are ignored. The raw non-empty rows are retained under their
    section names, while rows in ``ELD Event List`` are converted to immutable
    :class:`ELDEvent` objects. Missing values and malformed event rows are
    reported in the returned ``missing_data`` tuple.
    """
    # The current segment heading determines how each following row is handled.
    sections: dict[str, list[tuple[str, ...]]] = {}
    missing_data: list[str] = []
    events: list[ELDEvent] = []
    current_section: Optional[str] = None

    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.reader(csv_file)
        for line_number, row in enumerate(reader, start=1):
            # Ignore fully empty rows, including rows containing only whitespace.
            if not row or all(not cell.strip() for cell in row):
                continue

            # FMCSA output marks segment boundaries with a single title ending in ":".
            if len(row) == 1 and row[0].strip().endswith(":"):
                current_section = row[0].strip().removesuffix(":")
                sections.setdefault(current_section, [])
                continue

            if current_section is None:
                missing_data.append(
                    f"Line {line_number}: data row appears before a section heading."
                )
                continue

            # Trim padding around CSV values, but keep values as strings so IDs,
            # hexadecimal checksums, and decimal precision are preserved.
            cleaned = tuple(cell.strip() for cell in row)
            sections[current_section].append(cleaned)

            if current_section != "ELD Event List":
                continue

            if len(cleaned) != ELD_EVENT_FIELD_COUNT:
                missing_data.append(
                    f"Line {line_number}: expected {ELD_EVENT_FIELD_COUNT} event fields, "
                    f"found {len(cleaned)}; row was not parsed."
                )
                continue

            # Keep this order aligned with the 18 fields in section 4.8.2.1.4.
            field_names = (
                "event sequence ID", "event record status", "event record origin",
                "event type", "event code", "event date", "event time",
                "accumulated vehicle miles", "elapsed engine hours", "latitude",
                "longitude", "distance since last valid coordinates",
                "CMV order number", "record originator user order number",
                "ELD malfunction indicator status",
                "driver data diagnostic event indicator status",
                "event data check value", "line data check value",
            )
            for name, value in zip(field_names, cleaned):
                if not value:
                    missing_data.append(f"Line {line_number}: missing {name}.")

            try:
                # FMCSA output uses MMDDYY and HHMMSS in the driver's home-terminal zone.
                event_datetime = datetime.strptime(
                    cleaned[5] + cleaned[6], "%m%d%y%H%M%S"
                )
                events.append(
                    ELDEvent(
                        event_sequence_id_number=cleaned[0],
                        event_record_status=int(cleaned[1]),
                        event_record_origin=int(cleaned[2]),
                        event_type=int(cleaned[3]),
                        event_code=int(cleaned[4]),
                        event_datetime=event_datetime,
                        accumulated_vehicle_miles=cleaned[7],
                        elapsed_engine_hours=cleaned[8],
                        event_latitude=cleaned[9],
                        event_longitude=cleaned[10],
                        distance_since_last_valid_coordinates=cleaned[11],
                        corresponding_cmv_order_number=cleaned[12],
                        record_originator_user_order_number=cleaned[13],
                        eld_malfunction_indicator_status=int(cleaned[14]),
                        driver_data_diagnostic_event_indicator_status=int(cleaned[15]),
                        event_data_check_value=cleaned[16],
                        line_data_check_value=cleaned[17],
                    )
                )
            except ValueError as exc:
                missing_data.append(
                    f"Line {line_number}: event could not be parsed ({exc}); "
                    "check its date, time, and numeric code fields."
                )

    if "ELD Event List" not in sections:
        missing_data.append("The CSV is missing the ELD Event List section.")

    return ELDParseResult(
        sections={name: tuple(rows) for name, rows in sections.items()},
        events=events,
        missing_data=tuple(missing_data),
    )


def get_active_duty_status_events(events: list[ELDEvent]) -> list[ELDEvent]:
    """Return active duty-status change records for use in ELD charts.

    FMCSA event type 1 represents a duty-status change, and record status 1
    means the event is active. The input order is preserved.
    """
    return [
        event
        for event in events
        if event.event_type == 1 and event.event_record_status == 1
    ]


def build_daily_event_records(
    parse_result: ELDParseResult,
) -> dict[date, list[DailyEventRecord]]:
    """Collect every event record by date and sort each day's rows by time.

    The source ELD file stores event types 1–3, certifications, malfunctions
    and diagnostics, logins/logouts, engine power events, and unidentified
    profile events in separate sections. Annotation rows are supplementary
    details, so they are attached to their matching event instead of counted
    as separate events.
    """
    records_by_day: dict[date, list[DailyEventRecord]] = {}

    def parse_timestamp(
        row: tuple[str, ...], date_index: int, time_index: int
    ) -> datetime | None:
        try:
            return datetime.strptime(
                row[date_index] + row[time_index], "%m%d%y%H%M%S"
            )
        except (IndexError, ValueError):
            return None

    def append_record(
        timestamp: datetime | None,
        category: str,
        event: str,
        sequence_id: str,
        record_origin: str = "",
        details: str = "",
    ) -> None:
        if timestamp is None:
            return
        records_by_day.setdefault(timestamp.date(), []).append(
            DailyEventRecord(
                timestamp=timestamp,
                category=category,
                event=event,
                sequence_id=sequence_id,
                record_origin=record_origin,
                details=details,
            )
        )

    event_type_names = {
        1: "Duty Status Change",
        2: "Intermediate Log",
        3: "Special Driving Category",
    }
    code_to_duty_status = {
        code: status.replace("_", " ").title()
        for status, code in DUTY_STATUS_CODES.items()
    }
    event_code_descriptions = {
        2: {
            1: "Intermediate log (conventional location precision)",
            2: "Intermediate log (reduced location precision)",
        },
        3: {
            0: "Special driving category cleared",
            1: "Authorized personal use of CMV",
            2: "Yard moves",
        },
        7: {
            1: "ELD malfunction logged",
            2: "ELD malfunction cleared",
            3: "Data diagnostic event logged",
            4: "Data diagnostic event cleared",
        },
    }
    status_labels = {
        1: "Active",
        2: "Inactive - Changed",
        3: "Inactive - Change Requested",
        4: "Inactive - Change Rejected",
    }
    origin_labels = {
        code: label.replace("_", " ").title()
        for label, code in EVENT_RECORD_ORIGIN_CODES.items()
    }

    # Attach comments and manual location descriptions to their source event ID.
    annotations: dict[str, str] = {}
    for row in parse_result.sections.get("ELD Event Annotations or Comments", ()):
        if not row:
            continue
        details = []
        if len(row) > 2 and row[2]:
            details.append(row[2])
        if len(row) > 5 and row[5]:
            details.append(f"Location: {row[5]}")
        if details:
            annotations[row[0]] = "; ".join(details)

    # Main event list: event sequence, status, origin, type, code, date, time...
    for event in parse_result.events:
        if event.event_type == 1:
            description = code_to_duty_status.get(
                event.event_code, f"Unknown duty status code {event.event_code}"
            )
        else:
            description = event_code_descriptions.get(event.event_type, {}).get(
                event.event_code,
                f"{event_type_names.get(event.event_type, 'ELD event')} code "
                f"{event.event_code}",
            )
        details = annotations.get(event.event_sequence_id_number, "")
        try:
            origin = origin_labels.get(event.event_record_origin, "")
            record_status = status_labels.get(event.event_record_status, "")
            if record_status:
                details = "; ".join(
                    part for part in (f"Record: {record_status}", details) if part
                )
        except (TypeError, ValueError):
            origin = ""
        append_record(
            event.event_datetime,
            "ELD Event",
            description,
            event.event_sequence_id_number,
            origin,
            details,
        )

    # Certification section: sequence, code, event date, event time, certified date...
    for row in parse_result.sections.get(
        "Driver's Certification/Recertification Actions", ()
    ):
        timestamp = parse_timestamp(row, 2, 3)
        if timestamp is None or len(row) < 2:
            continue
        try:
            code = int(row[1])
        except ValueError:
            continue
        description = (
            "First daily record certification" if code == 1
            else f"Daily record recertification ({code})"
        )
        certified_date = row[4] if len(row) > 4 else ""
        append_record(
            timestamp, "Certification", description, row[0],
            details=f"Certified record date: {certified_date}" if certified_date else "",
        )

    # Malfunctions and diagnostics: sequence, event code, diagnostic code, date, time...
    for row in parse_result.sections.get("Malfunctions and Data Diagnostic Events", ()):
        timestamp = parse_timestamp(row, 3, 4)
        if timestamp is None or len(row) < 3:
            continue
        try:
            code = int(row[1])
        except ValueError:
            continue
        description = event_code_descriptions[7].get(
            code, f"Malfunction/diagnostic event code {code}"
        )
        append_record(
            timestamp, "Malfunction / Diagnostic", description, row[0],
            details=f"Diagnostic code: {row[2]}" if row[2] else "",
        )

    # Login/logout: sequence, event code, username, event date, event time...
    for row in parse_result.sections.get("ELD Login/Logout Report", ()):
        timestamp = parse_timestamp(row, 3, 4)
        if timestamp is None or len(row) < 3:
            continue
        try:
            code = int(row[1])
        except ValueError:
            continue
        description = {1: "Driver Login", 2: "Driver Logout"}.get(
            code, f"Login/logout event code {code}"
        )
        append_record(
            timestamp, "Login / Logout", description, row[0],
            details=f"ELD username: {row[2]}" if row[2] else "",
        )

    # Engine section: sequence, event code, event date, event time...
    engine_event_names = {
        1: "Engine power-up (conventional location precision)",
        2: "Engine power-up (reduced location precision)",
        3: "Engine shut-down (conventional location precision)",
        4: "Engine shut-down (reduced location precision)",
    }
    for row in parse_result.sections.get("CMV Engine Power-Up and Shut Down Activity", ()):
        timestamp = parse_timestamp(row, 2, 3)
        if timestamp is None or len(row) < 2:
            continue
        try:
            code = int(row[1])
        except ValueError:
            continue
        append_record(
            timestamp, "Engine", engine_event_names.get(code, f"Engine event code {code}"),
            row[0],
        )

    # The unidentified-profile event rows use the same 18-field layout as the main list.
    for row in parse_result.sections.get("Unidentified Driver Profile Records", ()):
        timestamp = parse_timestamp(row, 5, 6)
        if timestamp is None or len(row) < ELD_EVENT_FIELD_COUNT:
            continue
        try:
            event_status = int(row[1])
            event_origin = int(row[2])
            event_type = int(row[3])
            event_code = int(row[4])
        except ValueError:
            continue
        if event_type == 1:
            description = code_to_duty_status.get(
                event_code, f"Unknown duty status code {event_code}"
            )
        else:
            description = event_code_descriptions.get(event_type, {}).get(
                event_code,
                f"{event_type_names.get(event_type, 'ELD event')} code {event_code}",
            )
        status_text = status_labels.get(event_status, f"Record status {event_status}")
        origin_text = origin_labels.get(event_origin, f"Record origin {event_origin}")
        details = f"Record: {status_text}; {annotations.get(row[0], '')}".rstrip("; ")
        append_record(
            timestamp, "Unidentified Driver", description, row[0], origin_text, details
        )

    if not records_by_day:
        return {}

    first_day, last_day = min(records_by_day), max(records_by_day)
    current_day = first_day
    while current_day <= last_day:
        records_by_day.setdefault(current_day, [])
        current_day += timedelta(days=1)

    for daily_records in records_by_day.values():
        daily_records.sort(key=lambda record: record.timestamp)
    return dict(sorted(records_by_day.items()))


def draw_daily_event_table(axis, events: list[DailyEventRecord]) -> None:
    """Draw each event for a day in timestamp order on a Matplotlib axis."""
    axis.axis("off")
    axis.set_title("Events for the Day (timestamp order)", loc="left", fontsize=10, pad=4)
    if not events:
        axis.text(0.01, 0.5, "No event records for this day.", transform=axis.transAxes)
        return

    rows = [
        [
            event.timestamp.strftime("%H:%M:%S"),
            event.category,
            event.event,
            event.sequence_id,
            event.record_origin,
            event.details,
        ]
        for event in events
    ]
    axis.table(
        cellText=rows,
        colLabels=["Time", "Category", "Event", "Sequence ID", "Record Origin", "Details"],
        cellLoc="left",
        colLoc="left",
        loc="center",
        colWidths=[0.09, 0.15, 0.25, 0.12, 0.17, 0.22],
        bbox=[0, 0, 1, 1],
    )


def build_daily_timelines(
    events: list[ELDEvent],
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[date, list[DutyStatusInterval]]:
    """Build 24-hour duty-status intervals for dates represented by events.

    A day's starting status carries forward from the latest active duty-status
    event on the previous day. The earliest date defaults to off duty because
    this input contains no prior-day context. A date with no active
    duty-status events carries the latest known status for the full 0–24 hour
    day. Optional date bounds let callers request days with no events,
    including when the input event list is empty.
    """
    active_events = get_active_duty_status_events(events)
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    if not active_events and start_date is None and end_date is None:
        return {}

    # Convert FMCSA event codes (1–4) to readable duty-status labels.
    code_to_status = {code: status for status, code in DUTY_STATUS_CODES.items()}
    events_by_date: dict[date, list[ELDEvent]] = {}
    for event in active_events:
        events_by_date.setdefault(event.event_datetime.date(), []).append(event)

    event_days = list(events_by_date)
    # A lone bound describes one day; two bounds request the inclusive range.
    requested_start = start_date or end_date
    requested_end = end_date or start_date
    first_day = min([*event_days, *([requested_start] if requested_start else [])])
    last_day = max([*event_days, *([requested_end] if requested_end else [])])
    daily_timelines: dict[date, list[DutyStatusInterval]] = {}
    carried_status = "off_duty"
    current_day = first_day

    while current_day <= last_day:
        day_events = sorted(
            events_by_date.get(current_day, []),
            key=lambda event: event.event_datetime,
        )

        # With no change recorded, the last known duty status remains in effect.
        if not day_events:
            daily_timelines[current_day] = [
                DutyStatusInterval(
                    start_hour=0.0,
                    end_hour=24.0,
                    status=carried_status,
                )
            ]
            current_day += timedelta(days=1)
            continue

        intervals: list[DutyStatusInterval] = []
        interval_start = 0.0
        status = carried_status

        for event in day_events:
            try:
                next_status = code_to_status[event.event_code]
            except KeyError as exc:
                raise ValueError(
                    f"Event {event.event_sequence_id_number} has unknown duty-status "
                    f"event code {event.event_code}."
                ) from exc

            event_hour = (
                event.event_datetime.hour
                + event.event_datetime.minute / 60
                + event.event_datetime.second / 3600
            )

            # Close the preceding interval at this event's time; skip zero-length spans.
            if event_hour > interval_start:
                intervals.append(
                    DutyStatusInterval(interval_start, event_hour, status)
                )
            status = next_status
            interval_start = event_hour

        # The last status of the day extends to midnight and becomes tomorrow's start.
        if interval_start < 24.0:
            intervals.append(DutyStatusInterval(interval_start, 24.0, status))
        daily_timelines[current_day] = intervals
        carried_status = status
        current_day += timedelta(days=1)

    return daily_timelines


def generate_daily_eld_charts(
    csv_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[date, Path]:
    """Draw and save one 24-hour duty-status chart for each date in an ELD CSV.

    Active duty-status changes are drawn on the four FMCSA status rows. The
    chart uses the parsed sections and event dataclasses above; it does not
    attempt to draw a full roadside inspection report.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Matplotlib is required to draw charts. Install project dependencies "
            "with `python -m pip install -r requirements.txt`."
        ) from exc

    parse_result = read_eld_csv(csv_path)
    daily_event_records = build_daily_event_records(parse_result)
    if not parse_result.events and not daily_event_records:
        return {}

    # Dates include records stored in every output-file event segment.
    event_dates = list(daily_event_records)
    if not event_dates:
        event_dates = [event.event_datetime.date() for event in parse_result.events]
    first_date, last_date = min(event_dates), max(event_dates)
    timelines = build_daily_timelines(
        parse_result.events, start_date=first_date, end_date=last_date
    )
    chart_events = get_active_duty_status_events(parse_result.events)

    destination = Path(output_dir) if output_dir else Path(csv_path).parent / "eld_charts"
    destination.mkdir(parents=True, exist_ok=True)

    # Place the chart rows in conventional order, with Off Duty at the top.
    row_for_status = {
        "off_duty": 3,
        "sleeper_berth": 2,
        "driving": 1,
        "on_duty_not_driving": 0,
    }
    label_for_status = {
        "off_duty": "Off Duty",
        "sleeper_berth": "Sleeper Berth",
        "driving": "Driving",
        "on_duty_not_driving": "On Duty Not Driving",
    }
    color_for_status = {
        "off_duty": "#2563eb",
        "sleeper_berth": "#7c3aed",
        "driving": "#dc2626",
        "on_duty_not_driving": "#d97706",
    }

    chart_paths: dict[date, Path] = {}
    for chart_date, intervals in timelines.items():
        daily_events = daily_event_records.get(chart_date, [])
        table_height = max(1.0, (len(daily_events) + 1) * 0.24)
        fig = plt.figure(figsize=(12, 5.0 + table_height))
        grid = fig.add_gridspec(
            2, 1, height_ratios=[4.5, table_height], hspace=0.38
        )
        ax = fig.add_subplot(grid[0])
        event_table_axis = fig.add_subplot(grid[1])
        ax.set_xlim(0, 24)
        ax.set_ylim(-0.5, 3.5)
        ax.set_yticks([3, 2, 1, 0], [
            label_for_status["off_duty"],
            label_for_status["sleeper_berth"],
            label_for_status["driving"],
            label_for_status["on_duty_not_driving"],
        ])
        ax.set_xticks(range(25))
        # Quarter-hour minor lines make it easier to read short duty intervals.
        ax.set_xticks([quarter / 4 for quarter in range(97)], minor=True)
        ax.grid(which="major", axis="x", color="#64748b", linewidth=0.7)
        ax.grid(which="minor", axis="x", color="#cbd5e1", linewidth=0.35)
        ax.grid(which="major", axis="y", color="#94a3b8", linewidth=0.7)
        ax.set_axisbelow(True)

        prior_interval = None
        for interval in intervals:
            y = row_for_status[interval.status]
            ax.hlines(
                y,
                interval.start_hour,
                interval.end_hour,
                color=color_for_status[interval.status],
                linewidth=7,
                zorder=3,
            )
            if prior_interval is not None and prior_interval.status != interval.status:
                ax.vlines(
                    interval.start_hour,
                    row_for_status[prior_interval.status],
                    y,
                    color="#1f2937",
                    linewidth=1.5,
                    zorder=4,
                )
            prior_interval = interval

        # Dot each active type-1 event on the row for its resulting duty status.
        day_events = [
            event for event in chart_events
            if event.event_datetime.date() == chart_date
        ]
        code_to_status = {code: status for status, code in DUTY_STATUS_CODES.items()}
        for event in day_events:
            resulting_status = code_to_status.get(event.event_code)
            if resulting_status is None:
                continue
            event_hour = (
                event.event_datetime.hour
                + event.event_datetime.minute / 60
                + event.event_datetime.second / 3600
            )
            ax.plot(
                event_hour,
                row_for_status[resulting_status],
                marker="o",
                markersize=4,
                markerfacecolor="white",
                markeredgecolor="#111827",
                linestyle="none",
                zorder=5,
            )

        ax.set_title(f"ELD Duty Status — {chart_date:%Y-%m-%d}")
        ax.set_xlabel("Hour of 24-hour period")
        ax.set_ylabel("Duty Status")
        ax.set_xticklabels([f"{hour:02d}:00" for hour in range(25)], rotation=45, ha="right")
        draw_daily_event_table(event_table_axis, daily_events)
        fig.tight_layout()

        chart_path = destination / f"eld_chart_{chart_date.isoformat()}.png"
        fig.savefig(chart_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        chart_paths[chart_date] = chart_path

    return chart_paths


def main() -> int:
    """Parse an FMCSA ELD CSV selected by the user on the command line."""
    parser = argparse.ArgumentParser(
        description="Read and parse an FMCSA-structured ELD output CSV."
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to the ELD output CSV file to parse.",
    )
    parser.add_argument(
        "--charts",
        action="store_true",
        help="Draw a daily duty-status chart for each date in the CSV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Folder for chart images (default: ./eld_charts beside the CSV).",
    )
    args = parser.parse_args()

    try:
        result = read_eld_csv(args.csv_file)
    except OSError as exc:
        parser.error(f"could not open '{args.csv_file}': {exc}")

    print(f"Parsed {len(result.events)} ELD event(s).")
    print("Sections found:")
    for section_name, rows in result.sections.items():
        print(f"  {section_name}: {len(rows)} row(s)")

    if result.missing_data:
        print("Data issues to review:")
        for issue in result.missing_data:
            print(f"  - {issue}")
    else:
        print("No missing data or malformed event rows were found.")

    if args.charts:
        try:
            chart_paths = generate_daily_eld_charts(args.csv_file, args.output_dir)
        except RuntimeError as exc:
            parser.error(str(exc))
        if chart_paths:
            print("Charts saved:")
            for chart_path in chart_paths.values():
                print(f"  {chart_path}")
        else:
            print("No parsed ELD events were available to chart.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


