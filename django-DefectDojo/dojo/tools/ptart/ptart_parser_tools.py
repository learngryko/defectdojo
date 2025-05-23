import pathlib
from datetime import datetime

import cvss
from django.core.exceptions import ValidationError

from dojo.models import Endpoint

ATTACHMENT_ERROR = "Attachment data not found"
SCREENSHOT_ERROR = "Screenshot data not found"


def parse_ptart_severity(severity):
    severity_mapping = {
        1: "Critical",
        2: "High",
        3: "Medium",
        4: "Low",
    }
    return severity_mapping.get(severity, "Info")  # Default severity


def parse_ptart_fix_effort(effort):
    effort_mapping = {
        1: "High",
        2: "Medium",
        3: "Low",
    }
    return effort_mapping.get(effort)


def parse_title_from_hit(hit):
    hit_title = hit.get("title", None)
    hit_id = hit.get("id", None)

    return f"{hit_id}: {hit_title}" \
        if hit_title and hit_id \
        else (hit_title or hit_id or "Unknown Hit")


def parse_date_added_from_hit(hit):
    PTART_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
    date_added = hit.get("added", None)
    return parse_date(date_added, PTART_DATETIME_FORMAT)


def parse_date(date, date_format):
    try:
        return datetime.strptime(date, date_format) if date else datetime.now()
    except ValueError:
        return datetime.now()


def parse_cvss_vector(hit, cvss_type):
    cvss_vector = hit.get("cvss_vector", None)
    # Defect Dojo Only supports CVSS v3 for now.
    if cvss_vector:
        # Similar application once CVSS v4 is supported
        if cvss_type == 3:
            try:
                c = cvss.CVSS3(cvss_vector)
                return c.clean_vector()
            except cvss.CVSS3Error:
                return None
    return None


def parse_retest_status(status):
    fix_status_mapping = {
        "F": "Fixed",
        "NF": "Not Fixed",
        "PF": "Partially Fixed",
        "NA": "Not Applicable",
        "NT": "Not Tested",
    }
    return fix_status_mapping.get(status)


def parse_screenshots_from_hit(hit):
    if "screenshots" not in hit:
        return []
    screenshots = [parse_screenshot_data(screenshot)
                   for screenshot in hit["screenshots"]]
    return [ss for ss in screenshots if ss is not None]


def parse_screenshot_data(screenshot):
    try:
        title = get_screenshot_title(screenshot)
        data = get_screenshot_data(screenshot)
    except ValueError:
        return None
    return {
        "title": title,
        "data": data,
    }


def get_screenshot_title(screenshot):
    raw_caption = screenshot.get("caption", "screenshot")
    # Screenshot filenames are limited to 100 characters.
    caption = f"{raw_caption[:94]}.." if len(raw_caption) > 96 else raw_caption
    if not caption:
        caption = "screenshot"
    return f"{caption}{get_file_suffix_from_screenshot(screenshot)}"


def get_screenshot_data(screenshot):
    if ("screenshot" not in screenshot
            or "data" not in screenshot["screenshot"]
            or not screenshot["screenshot"]["data"]):
        raise ValueError(SCREENSHOT_ERROR)
    return screenshot["screenshot"]["data"]


def get_file_suffix_from_screenshot(screenshot):
    return pathlib.Path(screenshot["screenshot"]["filename"]).suffix \
        if ("screenshot" in screenshot
            and "filename" in screenshot["screenshot"]) \
        else ""


def parse_attachment_from_hit(hit):
    if "attachments" not in hit:
        return []
    files = [parse_attachment_data(attachment)
             for attachment in hit["attachments"]]
    return [f for f in files if f is not None]


def parse_attachment_data(attachment):
    try:
        title = get_attachement_title(attachment)
        data = get_attachment_data(attachment)
    except ValueError:
        # No data in attachment, let's not import this file.
        return None
    return {
        "title": title,
        "data": data,
    }


def get_attachment_data(attachment):
    if "data" not in attachment or not attachment["data"]:
        raise ValueError(ATTACHMENT_ERROR)
    return attachment["data"]


def get_attachement_title(attachment):
    title = attachment.get("title", "attachment")
    if not title:
        title = "attachment"
    return title


def parse_endpoints_from_hit(hit):
    if "asset" not in hit or not hit["asset"]:
        return []
    try:
        asset = hit.get("asset", None)
        if not asset:
            return []
        # Workaround for Defect Dojo being silly when parsing uris.
        # If there's no protocol, it will assume the hostname is the protocol.
        asset = f"https://{asset}" if "://" not in asset else asset
        endpoint = Endpoint.from_uri(asset)
    except ValidationError:
        endpoint = None
    return [] if not endpoint else [endpoint]


def generate_test_description_from_report(data):
    keys = ["executive_summary", "engagement_overview", "conclusion"]
    clauses = [clause for clause in [data.get(key) for key in keys] if clause]
    description = "\n\n".join(clauses)
    return description or None


def parse_references_from_hit(hit):
    if "references" not in hit:
        return None

    references = hit.get("references", [])
    all_refs = [get_transformed_reference(ref) for ref in references]
    clean_refs = [tref for tref in all_refs if tref]
    if not clean_refs:
        return None
    return "\n".join(clean_refs)


def get_transformed_reference(reference):
    title = reference.get("name", "Reference")
    url = reference.get("url", None)
    if not url:
        if not title:
            return url
        return None
    return f"{title}: {url}"


def parse_cwe_from_hit(hit):
    if "cwes" not in hit or not hit["cwes"]:
        return None
    cwes = hit["cwes"]
    # Grab the last CWE in the list, as it's sorted in numerical order,
    # and the last element is generally the most specific.
    return parse_cwe_id_from_cwe(cwes.pop()) if cwes and isinstance(cwes, list) and len(cwes) > 0 else None


def parse_cwe_id_from_cwe(cwe):
    try:
        if not cwe:
            return None

        cwe_id = cwe.get("cwe_id", None)
        if not cwe_id:
            title = cwe.get("title", None)
            if not title:
                return None
            cwe_id = parse_cwe_id_from_cwe_title(title)
        elif isinstance(cwe_id, str):
            cwe_id = int(cwe_id)
        elif not isinstance(cwe_id, int):
            cwe_id = None
    except (ValueError, IndexError):
        return None
    return cwe_id


def parse_cwe_id_from_cwe_title(title):
    try:
        if not title:
            return None
        return int(title.split("-")[1])
    except (ValueError, IndexError):
        return None
