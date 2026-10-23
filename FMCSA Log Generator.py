"""Data models and FMCSA code mappings for ELD output files."""

from dataclasses import dataclass
from datetime import datetime
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


