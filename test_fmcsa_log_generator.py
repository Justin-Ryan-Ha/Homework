"""Unit tests for daily ELD duty-status timeline construction."""

from datetime import date, datetime
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).with_name("FMCSA Log Generator.py")
MODULE_SPEC = importlib.util.spec_from_file_location("fmcsa_log_generator", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise ImportError(f"Could not load {MODULE_PATH}")
fmcsa = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = fmcsa
MODULE_SPEC.loader.exec_module(fmcsa)


class BuildDailyTimelinesTests(unittest.TestCase):
    def make_event(
        self,
        event_date: date,
        hour: int,
        minute: int,
        status_code: int,
        *,
        event_type: int = 1,
        record_status: int = 1,
        sequence_id: str = "0001",
    ):
        """Build a minimal event object with the fields used by the timeline code."""
        return fmcsa.ELDEvent(
            event_sequence_id_number=sequence_id,
            event_record_status=record_status,
            event_record_origin=1,
            event_type=event_type,
            event_code=status_code,
            event_datetime=datetime(
                event_date.year, event_date.month, event_date.day, hour, minute
            ),
            accumulated_vehicle_miles="0",
            elapsed_engine_hours="0.0",
            event_latitude="",
            event_longitude="",
            distance_since_last_valid_coordinates="0",
            corresponding_cmv_order_number="1",
            record_originator_user_order_number="1",
            eld_malfunction_indicator_status=0,
            driver_data_diagnostic_event_indicator_status=0,
            event_data_check_value="00",
            line_data_check_value="00",
        )

    def test_full_offline_day_with_no_events(self):
        """An explicitly requested day without events becomes off duty all day."""
        offline_day = date(2026, 10, 12)

        timelines = fmcsa.build_daily_timelines(
            [], start_date=offline_day, end_date=offline_day
        )

        # True: the requested offline date is included even without any events.
        self.assertTrue(offline_day in timelines)
        # False: an offline day must not contain a non-off-duty interval.
        self.assertFalse(any(
            interval.status != "off_duty" for interval in timelines[offline_day]
        ))
        self.assertEqual(
            timelines[offline_day],
            [fmcsa.DutyStatusInterval(0.0, 24.0, "off_duty")],
        )

    def test_sleeper_berth_for_ten_hours(self):
        """Events out of file order are sorted into intervals with a 10-hour SB span."""
        day = date(2026, 10, 12)
        events = [
            self.make_event(day, 17, 0, 1),  # Off duty at 17:00.
            self.make_event(day, 7, 0, 2),   # Sleeper berth begins at 07:00.
        ]

        timeline = fmcsa.build_daily_timelines(events)[day]

        # True: sleeper berth spans exactly 10 hours, from 07:00 through 17:00.
        self.assertTrue(any(
            interval.status == "sleeper_berth"
            and interval.end_hour - interval.start_hour == 10.0
            for interval in timeline
        ))
        # False: no zero-length or backwards intervals should be produced.
        self.assertFalse(any(
            interval.start_hour >= interval.end_hour for interval in timeline
        ))
        self.assertEqual(
            timeline,
            [
                fmcsa.DutyStatusInterval(0.0, 7.0, "off_duty"),
                fmcsa.DutyStatusInterval(7.0, 17.0, "sleeper_berth"),
                fmcsa.DutyStatusInterval(17.0, 24.0, "off_duty"),
            ],
        )

    def test_next_day_begins_with_previous_day_final_status(self):
        """The last status on one day carries across midnight to the next day."""
        first_day = date(2026, 10, 12)
        second_day = date(2026, 10, 13)
        events = [
            self.make_event(first_day, 20, 0, 2),  # Sleeper berth before midnight.
            self.make_event(second_day, 6, 0, 3),  # Driving starts at 06:00.
        ]

        timelines = fmcsa.build_daily_timelines(events)

        # True: the second day begins in the prior day's last status.
        self.assertTrue(timelines[second_day][0].status == "sleeper_berth")
        # False: it must not incorrectly reset to off duty at midnight.
        self.assertFalse(timelines[second_day][0].status == "off_duty")
        self.assertEqual(
            timelines[second_day],
            [
                fmcsa.DutyStatusInterval(0.0, 6.0, "sleeper_berth"),
                fmcsa.DutyStatusInterval(6.0, 24.0, "driving"),
            ],
        )

    def test_event_at_midnight_starts_day_at_new_status_without_zero_span(self):
        """A status change at 00:00 applies immediately without an empty interval."""
        day = date(2026, 10, 12)
        events = [self.make_event(day, 0, 0, 4)]

        timeline = fmcsa.build_daily_timelines(events)[day]

        # True: a midnight event sets the status for the full day immediately.
        self.assertTrue(len(timeline) == 1 and timeline[0].start_hour == 0.0)
        # False: the midnight transition must not create a zero-length span.
        self.assertFalse(any(
            interval.start_hour == interval.end_hour for interval in timeline
        ))
        self.assertEqual(
            timeline,
            [fmcsa.DutyStatusInterval(0.0, 24.0, "on_duty_not_driving")],
        )

    def test_inactive_and_non_duty_events_do_not_change_timeline(self):
        """Only active event-type-1 records affect the duty-status timeline."""
        day = date(2026, 10, 12)
        events = [
            self.make_event(day, 8, 0, 3, record_status=2),
            self.make_event(day, 9, 0, 3, event_type=2),
        ]

        timelines = fmcsa.build_daily_timelines(events, start_date=day, end_date=day)

        # True: ignored events leave the default off-duty interval intact.
        self.assertTrue(all(
            interval.status == "off_duty" for interval in timelines[day]
        ))
        # False: inactive or non-duty events must not create a driving span.
        self.assertFalse(any(
            interval.status == "driving" for interval in timelines[day]
        ))
        self.assertEqual(
            timelines[day],
            [fmcsa.DutyStatusInterval(0.0, 24.0, "off_duty")],
        )

    def test_unknown_duty_status_event_code_raises_clear_error(self):
        """An unknown duty-status code fails clearly instead of being mischarted."""
        day = date(2026, 10, 12)
        event = self.make_event(day, 8, 0, 9, sequence_id="ABCD")

        with self.assertRaisesRegex(ValueError, "ABCD.*unknown duty-status.*9"):
            fmcsa.build_daily_timelines([event])

    def test_start_date_after_end_date_is_rejected(self):
        """Invalid requested date ranges are rejected with a helpful error."""
        with self.assertRaisesRegex(ValueError, "start_date must be on or before end_date"):
            fmcsa.build_daily_timelines(
                [], start_date=date(2026, 10, 13), end_date=date(2026, 10, 12)
            )


class ReadEldCsvTests(unittest.TestCase):
    VALID_EVENT_ROW = (
        "00AB,1,2,1,3,101226,081530,3709,47.8,50.91,-114.10,0,1,2,0,1,05,02"
    )

    def read_csv_text(self, csv_text: str):
        """Write test CSV contents to a temporary file and parse that file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "eld_output.csv"
            csv_path.write_text(csv_text, encoding="utf-8")
            return fmcsa.read_eld_csv(csv_path)

    def test_reads_section_headings_and_parses_eld_event_fields(self):
        """Section titles are identified and the ELD event columns are parsed."""
        result = self.read_csv_text(
            "ELD File Header Segment:\nheader,value\n"
            "User List:\n1,D,Driver,Test,00\n"
            f"ELD Event List:\n{self.VALID_EVENT_ROW}\n"
        )

        self.assertEqual(
            set(result.sections),
            {"ELD File Header Segment", "User List", "ELD Event List"},
        )
        self.assertEqual(len(result.events), 1)
        event = result.events[0]
        self.assertEqual(event.event_sequence_id_number, "00AB")
        self.assertEqual(event.event_code, 3)
        self.assertEqual(event.event_datetime, datetime(2026, 10, 12, 8, 15, 30))
        self.assertEqual(event.event_latitude, "50.91")
        self.assertFalse(result.missing_data)

    def test_ignores_empty_and_whitespace_only_rows(self):
        """Empty CSV rows are skipped rather than stored or reported as errors."""
        result = self.read_csv_text(
            "ELD Event List:\n\n   ,   \n"
            f"{self.VALID_EVENT_ROW}\n\n"
        )

        # Only the event row is retained; blank rows do not become records/issues.
        self.assertEqual(len(result.sections["ELD Event List"]), 1)
        self.assertEqual(len(result.events), 1)
        self.assertFalse(result.missing_data)

    def test_reports_blank_field_but_keeps_parseable_event(self):
        """A blank data field is reported even when the rest of the event parses."""
        row_with_missing_latitude = self.VALID_EVENT_ROW.replace(
            "50.91,-114.10", ",-114.10"
        )
        result = self.read_csv_text(f"ELD Event List:\n{row_with_missing_latitude}\n")

        # The row is still usable for other fields, and the missing value is reported.
        self.assertEqual(len(result.events), 1)
        self.assertTrue(any("missing latitude" in issue for issue in result.missing_data))

    def test_reports_wrong_field_count_and_skips_that_event(self):
        """Rows that do not have all 18 event fields are reported and skipped."""
        short_row = ",".join(self.VALID_EVENT_ROW.split(",")[:-1])
        result = self.read_csv_text(f"ELD Event List:\n{short_row}\n")

        self.assertFalse(result.events)
        self.assertTrue(any("expected 18 event fields" in issue for issue in result.missing_data))

    def test_reports_invalid_numeric_event_field(self):
        """A non-numeric code in an integer field is reported and not parsed."""
        invalid_row = self.VALID_EVENT_ROW.replace(",1,2,1,3,", ",x,2,1,3,")
        result = self.read_csv_text(f"ELD Event List:\n{invalid_row}\n")

        self.assertFalse(result.events)
        self.assertTrue(any("could not be parsed" in issue for issue in result.missing_data))

    def test_reports_missing_eld_event_section(self):
        """A file without an ELD Event List section reports that missing section."""
        result = self.read_csv_text("User List:\n1,D,Driver,Test,00\n")

        self.assertFalse(result.events)
        self.assertTrue(any("missing the ELD Event List section" in issue
                            for issue in result.missing_data))


if __name__ == "__main__":
    unittest.main()
