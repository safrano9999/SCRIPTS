#!/usr/bin/env python3
"""
calendar_fetch.py - Nextcloud/public iCal fetcher + Telegram formatter

Exit codes:
  0 = at least one event found and printed
  2 = no events in window (dispatcher sends on_empty message)
  1 = error (network, parse, etc.) → stderr
"""

from python_header import env

import argparse
import os
import re
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlparse, urlunparse
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests
import recurring_ical_events
from icalendar import Calendar


# ─── helpers ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalendarEntry:
    key: str
    url: str
    user: str = ""
    password: str = ""
    host_header: str = ""


def collect_calendar_values(
    path: str, account_prefix: str = "CALENDAR"
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    direct_urls: dict[str, str] = {}
    grouped: dict[str, dict[str, str]] = {}

    def add_pair(key: str, value: str) -> None:
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return
        if "_" not in key:
            direct_urls[key] = value
            return
        upper_key = key.upper()
        if upper_key.endswith("_HOST_HEADER"):
            prefix = key[: -len("_HOST_HEADER")]
            field = "host_header"
        elif upper_key.endswith("_HOSTHEADER"):
            prefix = key[: -len("_HOSTHEADER")]
            field = "host_header"
        else:
            prefix, _, field = key.rpartition("_")
        field = field.lower()
        if field in {"url", "user", "password", "host_header", "hostheader"}:
            if field == "hostheader":
                field = "host_header"
            grouped.setdefault(prefix, {})[field] = value

    values: dict[str, str] = {}
    file_path = Path(path)
    if file_path.exists():
        with file_path.open(encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()

    values.update(env)
    if account_prefix == "NEXTCLOUD":
        pattern = re.compile(r"^NEXTCLOUD_(URL|USER|PW|CALENDAR)(?:_(\d+))?$")
        enabled: dict[str, bool] = {}
        for key, raw_value in values.items():
            match = pattern.match(key)
            value = raw_value.strip()
            if not match or not value:
                continue
            field, index = match.groups()
            prefix = "NEXTCLOUD" if not index or int(index) == 1 else f"NEXTCLOUD_{int(index):02d}"
            if field == "CALENDAR":
                enabled[prefix] = value.lower() in {"1", "true", "yes", "on"}
                continue
            mapped = {"URL": "url", "USER": "user", "PW": "password"}[field]
            if mapped == "url":
                value = f"{value.rstrip('/')}/remote.php/dav"
            grouped.setdefault(prefix, {})[mapped] = value
        grouped = {prefix: fields for prefix, fields in grouped.items() if enabled.get(prefix, True)}
        return direct_urls, grouped

    for key, value in values.items():
        if key.startswith("CALENDAR_") or key[:1].isdigit():
            add_pair(key, value)

    return direct_urls, grouped


def parse_calenv(path: str, account_prefix: str = "CALENDAR") -> list[CalendarEntry]:
    """Parse calendar entries from .env-style file and injected env.

    Supported formats:
      1=https://host/calendar.ics
      1_URL=https://host/calendar.ics
      1_USER=username
      1_PASSWORD=password
      CALENDAR_1_URL=https://host/calendar.ics
      CALENDAR_1_USER=username
      CALENDAR_1_PASSWORD=password
      CALENDAR_1_HOST_HEADER=127.0.0.1:440
    """
    direct_urls, grouped = collect_calendar_values(path, account_prefix)

    ordered_keys = []
    for key in direct_urls:
        if key not in ordered_keys:
            ordered_keys.append(key)
    for key in grouped:
        if key not in ordered_keys:
            ordered_keys.append(key)

    entries = []
    for key in ordered_keys:
        values = grouped.get(key, {})
        url = values.get("url") or direct_urls.get(key, "")
        if not url:
            continue
        entries.append(
            CalendarEntry(
                key=key,
                url=url,
                user=values.get("user", ""),
                password=values.get("password", ""),
                host_header=values.get("host_header", ""),
            )
        )
    return entries


def dt_to_aware(dt, tz: ZoneInfo) -> datetime:
    """Normalize a date or datetime to timezone-aware datetime."""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt
    # date object → treat as all-day, midnight local time
    return datetime(dt.year, dt.month, dt.day, tzinfo=tz)


def is_allday(dtstart) -> bool:
    """True if the event has a DATE (not DATETIME) start."""
    return isinstance(dtstart, date) and not isinstance(dtstart, datetime)


def format_event(evt, tz: ZoneInfo) -> str:
    """Format a single event as one output line."""
    dtstart_raw = evt.get("DTSTART").dt
    dtend_raw   = evt.get("DTEND")
    summary     = str(evt.get("SUMMARY", "(kein Titel)")).strip()

    allday = is_allday(dtstart_raw)

    start = dt_to_aware(dtstart_raw, tz)

    WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    wd   = WEEKDAYS[start.weekday()]
    date_str = f"{wd} {start.strftime('%d.%m.')}"

    if allday:
        time_str = "ganztag    "
    else:
        end = dt_to_aware(dtend_raw.dt, tz) if dtend_raw else None
        if end:
            time_str = f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
        else:
            time_str = start.strftime("%H:%M")
        # pad to fixed width for alignment
        time_str = f"{time_str:<11}"

    return f"{date_str} {time_str} -> {summary}"


def fetch_calendar(entry: CalendarEntry, verify) -> bytes:
    """Fetch iCal data from URL."""
    auth = (entry.user, entry.password) if entry.user or entry.password else None
    resp = requests.get(entry.url, auth=auth, headers=request_headers(entry), verify=verify, timeout=15)
    resp.raise_for_status()
    ct = resp.headers.get("Content-Type", "")
    if "text/html" in ct or resp.content.lstrip().startswith(b"<!DOCTYPE"):
        raise ValueError(
            f"Server returned HTML instead of iCal — wrong URL? "
            f"Use /remote.php/dav/public-calendars/TOKEN/?export"
        )
    return resp.content


DAV_NS = "DAV:"
CALDAV_NS = "urn:ietf:params:xml:ns:caldav"
CALSERVER_NS = "http://calendarserver.org/ns/"


def auth_for(entry: CalendarEntry):
    return (entry.user, entry.password) if entry.user or entry.password else None


def request_headers(entry: CalendarEntry, extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra or {})
    if entry.host_header:
        headers["Host"] = entry.host_header
    return headers


def absolute_url(base_url: str, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    parsed = urlparse(base_url)
    if href.startswith("/"):
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return urljoin(base_url, href)


def with_export_query(url: str) -> str:
    parsed = urlparse(url)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if not any(key == "export" for key, _ in query_items):
        query_items.append(("export", ""))
    return urlunparse(parsed._replace(query=urlencode(query_items, doseq=True)))


def propfind(entry: CalendarEntry, url: str, body: str, depth: str, verify) -> ET.Element:
    resp = requests.request(
        "PROPFIND",
        url,
        auth=auth_for(entry),
        headers=request_headers(entry, {"Depth": depth, "Content-Type": "application/xml; charset=utf-8"}),
        data=body.encode("utf-8"),
        verify=verify,
        timeout=15,
    )
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def ok_propstats(response: ET.Element) -> list[ET.Element]:
    props = []
    for propstat in response.findall(f"{{{DAV_NS}}}propstat"):
        status = propstat.findtext(f"{{{DAV_NS}}}status") or ""
        if " 200 " not in status:
            continue
        prop = propstat.find(f"{{{DAV_NS}}}prop")
        if prop is not None:
            props.append(prop)
    return props


def first_href(prop: ET.Element, tag: str) -> str:
    container = prop.find(tag)
    if container is None:
        return ""
    return container.findtext(f"{{{DAV_NS}}}href") or ""


def calendar_home_url(entry: CalendarEntry, verify) -> str:
    parsed = urlparse(entry.url)
    path = parsed.path.rstrip("/")
    if "/remote.php/dav/calendars/" in path:
        parts = path.split("/remote.php/dav/calendars/", 1)
        segments = [item for item in parts[1].split("/") if item]
        if len(segments) >= 2:
            home_path = f"{parts[0]}/remote.php/dav/calendars/{segments[0]}/"
            return urlunparse(parsed._replace(path=home_path, params="", query="", fragment=""))
        return urlunparse(parsed._replace(path=f"{path}/", params="", query="", fragment=""))
    if path.endswith("/remote.php/dav") and entry.user:
        home_path = f"{path}/calendars/{quote(entry.user)}/"
        return urlunparse(parsed._replace(path=home_path, params="", query="", fragment=""))

    body = """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav" xmlns:cs="http://calendarserver.org/ns/">
  <d:prop>
    <cal:calendar-home-set/>
    <cs:calendar-home-set/>
  </d:prop>
</d:propfind>"""
    root = propfind(entry, entry.url, body, "0", verify)
    for response in root.findall(f"{{{DAV_NS}}}response"):
        for prop in ok_propstats(response):
            href = first_href(prop, f"{{{CALDAV_NS}}}calendar-home-set") or first_href(
                prop, f"{{{CALSERVER_NS}}}calendar-home-set"
            )
            if href:
                return absolute_url(entry.url, href)
    raise ValueError("CalDAV calendar-home-set not found")


def is_calendar_collection(prop: ET.Element) -> bool:
    resourcetype = prop.find(f"{{{DAV_NS}}}resourcetype")
    if resourcetype is None:
        return False
    return resourcetype.find(f"{{{CALDAV_NS}}}calendar") is not None


def discover_caldav_sources(entry: CalendarEntry, verify) -> list[tuple[str, bytes]]:
    home_url = calendar_home_url(entry, verify)
    body = """<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:displayname/>
    <d:resourcetype/>
    <cal:supported-calendar-component-set/>
  </d:prop>
</d:propfind>"""
    root = propfind(entry, home_url, body, "1", verify)
    sources: list[tuple[str, bytes]] = []
    errors: list[str] = []
    for response in root.findall(f"{{{DAV_NS}}}response"):
        href = response.findtext(f"{{{DAV_NS}}}href") or ""
        if not href:
            continue
        collection_url = absolute_url(home_url, href)
        if collection_url.rstrip("/") == home_url.rstrip("/"):
            continue
        for prop in ok_propstats(response):
            if not is_calendar_collection(prop):
                continue
            display_name = (prop.findtext(f"{{{DAV_NS}}}displayname") or "").strip()
            export_url = with_export_query(collection_url)
            try:
                payload = fetch_calendar(
                    CalendarEntry(entry.key, export_url, entry.user, entry.password, entry.host_header),
                    verify,
                )
            except Exception as exc:
                errors.append(f"{display_name or collection_url}: {exc}")
                continue
            sources.append((display_name or f"Kalender {entry.key}", payload))
            break
    if sources:
        return sources
    if errors:
        raise ValueError("; ".join(errors))
    raise ValueError(f"No CalDAV calendars found below {home_url}")


def looks_like_caldav_url(url: str) -> bool:
    parsed = urlparse(url)
    if "export" in parsed.query:
        return False
    return "/remote.php/dav" in parsed.path and not parsed.path.endswith(".ics")


def fetch_calendar_sources(entry: CalendarEntry, verify) -> list[tuple[str, bytes]]:
    if looks_like_caldav_url(entry.url):
        return discover_caldav_sources(entry, verify)
    return [(f"Kalender {entry.key}", fetch_calendar(entry, verify))]


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch and format Nextcloud calendar events")
    parser.add_argument("--calenv",  required=True, help="Path to .calenv file")
    parser.add_argument("--logdir",  required=True, help="Directory for log files")
    parser.add_argument("--cert",    default="",    help="Path to CA cert .pem (or empty for verify=False)")
    parser.add_argument("--timezone", default="Europe/Vienna", help="IANA timezone for display and window bounds")
    parser.add_argument("--past-hours", type=float, default=1.0, help="Include events that started this many hours ago")
    parser.add_argument("--days", type=float, default=7.0, help="Look ahead this many days")
    parser.add_argument("--account-prefix", choices=("CALENDAR", "NEXTCLOUD"), default="CALENDAR")
    args = parser.parse_args()

    tz = ZoneInfo(args.timezone)
    now = datetime.now(tz=tz)
    window_start = now - timedelta(hours=max(args.past_hours, 0))
    window_end   = now + timedelta(days=max(args.days, 0))

    log_lines = [
        f"# calendar run {now.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"- calenv: {args.calenv}",
    ]

    # SSL verification
    if args.cert and Path(args.cert).is_file():
        verify = args.cert
    else:
        if args.cert:
            print(f"WARNING: cert not found at '{args.cert}' — using verify=False", file=sys.stderr)
        verify = False
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    # Parse .calenv
    try:
        entries = parse_calenv(args.calenv, args.account_prefix)
    except Exception as e:
        print(f"ERROR reading calenv '{args.calenv}': {e}", file=sys.stderr)
        log_lines.append(f"- calenv_error: {e}")
        _write_log(args.logdir, log_lines + ["- exit: 1"])
        sys.exit(1)

    log_lines.append(f"- calendars: {len(entries)}")

    if not entries:
        if args.account_prefix == "NEXTCLOUD":
            _write_log(args.logdir, log_lines + ["- exit: 2", "- calendar: disabled"])
            sys.exit(2)
        print(f"ERROR: no calendar URLs found in '{args.calenv}'", file=sys.stderr)
        _write_log(args.logdir, log_lines + ["- exit: 1"])
        sys.exit(1)

    # Fetch + parse each calendar
    sections = []
    total_events = 0
    fetch_errors = []
    fetched_entries = 0

    for entry in entries:
        try:
            sources = fetch_calendar_sources(entry, verify)
        except Exception as e:
            fetch_errors.append(f"{entry.key}: {e}")
            print(f"ERROR fetching calendar {entry.key}: {e}", file=sys.stderr)
            sections.append((f"Kalender {entry.key} [FEHLER]", []))
            continue

        fetched_entries += 1
        for source_name, ical_data in sources:
            cal_name = source_name or f"Kalender {entry.key}"
            try:
                cal = Calendar.from_ical(ical_data)

                # Try to get calendar name
                for component in cal.walk():
                    if component.name == "VCALENDAR":
                        raw_name = component.get("X-WR-CALNAME")
                        if raw_name:
                            cal_name = str(raw_name)
                        break

                # Expand recurring events within window
                events_raw = recurring_ical_events.of(cal).between(window_start, window_end)

                # Sort by start time
                def sort_key(e):
                    dt = e.get("DTSTART").dt
                    return dt_to_aware(dt, tz)

                events_sorted = sorted(events_raw, key=sort_key)

                lines = [format_event(e, tz) for e in events_sorted]
                sections.append((cal_name, lines))
                total_events += len(lines)

            except Exception as e:
                fetch_errors.append(f"{entry.key}/{cal_name}: {e}")
                print(f"ERROR parsing calendar {entry.key}/{cal_name}: {e}", file=sys.stderr)
                sections.append((f"{cal_name} [FEHLER]", []))

    log_lines.append(f"- fetched: {fetched_entries} ok" +
                     (f", errors: {'; '.join(fetch_errors)}" if fetch_errors else ""))
    log_lines.append(f"- events_in_window: {total_events}")

    # If all failed with errors and no events → exit 1
    if fetch_errors and total_events == 0:
        _write_log(args.logdir, log_lines + ["- exit: 1"])
        sys.exit(1)

    # No events in window → exit 2
    if total_events == 0:
        _write_log(args.logdir, log_lines + ["- exit: 2"])
        sys.exit(2)

    # Build output
    output_parts = []
    for cal_name, lines in sections:
        if not lines:
            continue
        header = f"📅 {cal_name} ({len(lines)} Termin{'e' if len(lines) != 1 else ''})"
        divider = "-" * 25
        output_parts.append(header)
        output_parts.append(divider)
        output_parts.extend(lines)

    print("\n".join(output_parts))

    log_lines.append("- exit: 0")
    _write_log(args.logdir, log_lines)
    sys.exit(0)


def _write_log(logdir: str, lines: list[str]):
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = Path(logdir) / f"{ts}.md"
    try:
        Path(logdir).mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(lines) + "\n")
    except Exception as e:
        print(f"WARNING: could not write log: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
