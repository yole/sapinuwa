#!/usr/bin/env python3
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

START_URL = (
    "https://script.googleusercontent.com/macros/echo?"
    "user_content_key=AUkAhnT7w4z1Z1kxt2_bDoDNY9IfbyQgpFWKk8Zu75xU9fguaFgsyhyk85ZHaX2lN0JpEmEFxltY_AtzsLe5pYOQ1ov5PnCC9dbhCPzodHyquL04gkkTZCpAzkdTE0czBfjnQmhEueWceI4tgXTgYy58QHU0cSgS_sqNGWwEGFtPgCS5xklTMEIA2NEevtvDzzzOVTrwE0_HbWY8lLarEzwRjYkTHO2mshmBOmZnug4f3g1QPWXV-mHe2-SRHRKwSnzf_3MPGXqNwH8qUy45E6etr8-ORaUEV5wipfrwNGD_K6mm4N5R6iS5853SaBI_wa-vYGjEVQS5029RP_FZPtw"
    "&lib=MK8gsunwYC-x_OwKC6TJtHZQk4sMhn0Q9"
)
PAGE_SIZE = 50
USER_AGENT = "Mozilla/5.0 (compatible; pdf-batch-downloader/1.0)"
TIMEOUT_SECONDS = 60


def request_text(url: str) -> tuple[str, str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        text = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
    return text, final_url


def extract_html_redirect_url(text: str) -> str | None:
    match = re.search(r'href="([^"]+)"', text, flags=re.IGNORECASE)
    if not match:
        return None
    return html.unescape(match.group(1))


def parse_json_or_jsonp(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)

    match = re.match(r"^[\w.$]+\((.*)\);?\s*$", stripped, flags=re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("Response is neither JSON nor JSONP.")


def canonical_exec_endpoint(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc != "script.google.com" or not parsed.path.endswith("/exec"):
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def discover_exec_endpoint(start_url: str) -> str | None:
    opener = build_opener(NoRedirect())
    current_url = start_url

    for _ in range(10):
        req = Request(current_url, headers={"User-Agent": USER_AGENT})
        try:
            with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8", errors="replace")
                moved_url = extract_html_redirect_url(body)
                if not moved_url:
                    return canonical_exec_endpoint(response.geturl())
                endpoint = canonical_exec_endpoint(moved_url)
                if endpoint:
                    return endpoint
                current_url = moved_url
        except Exception as exc:
            code = getattr(exc, "code", None)
            headers = getattr(exc, "headers", None)
            if code in {301, 302, 303, 307, 308} and headers:
                location = headers.get("Location")
                if not location:
                    return None
                endpoint = canonical_exec_endpoint(location)
                if endpoint:
                    return endpoint
                current_url = location
                continue
            raise
    return None


def fetch_page(url: str) -> tuple[dict, str | None]:
    current_url = url
    endpoint = None

    for _ in range(10):
        text, final_url = request_text(current_url)
        endpoint = endpoint or canonical_exec_endpoint(final_url)

        if text.lstrip().startswith("<"):
            moved_url = extract_html_redirect_url(text)
            if not moved_url:
                raise RuntimeError("Got HTML response without redirect target.")
            endpoint = endpoint or canonical_exec_endpoint(moved_url)
            current_url = moved_url
            continue

        payload = parse_json_or_jsonp(text)
        return payload, endpoint

    raise RuntimeError("Too many redirect-like hops while fetching page.")


def make_page_url(endpoint: str, page_token: str | None) -> str:
    query = {"pageSize": str(PAGE_SIZE)}
    if page_token:
        query["pageToken"] = page_token
    return f"{endpoint}?{urlencode(query)}"


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    if not cleaned:
        cleaned = "unnamed.pdf"
    if not cleaned.lower().endswith(".pdf"):
        cleaned += ".pdf"
    return cleaned


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def download_pdf(file_id: str, target_path: Path) -> None:
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    req = Request(download_url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=TIMEOUT_SECONDS) as response, target_path.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def initial_page_url(start_url: str) -> str:
    parsed = urlparse(start_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["pageSize"] = [str(PAGE_SIZE)]
    flat_query = urlencode({k: v[-1] for k, v in query.items()})
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", flat_query, ""))


def main() -> int:
    start_url = START_URL
    endpoint = discover_exec_endpoint(start_url)
    page_url = make_page_url(endpoint, None) if endpoint else initial_page_url(start_url)
    page_token = None
    seen_file_ids: set[str] = set()
    total_downloaded = 0
    page_number = 0

    os.makedirs("pdfs", exist_ok=True)

    while True:
        if endpoint:
            page_url = make_page_url(endpoint, page_token)

        page_number += 1
        payload, discovered_endpoint = fetch_page(page_url)
        if discovered_endpoint and not endpoint:
            endpoint = discovered_endpoint

        files = payload.get("files", [])
        if not isinstance(files, list):
            raise RuntimeError("Unexpected payload: 'files' field is not a list.")

        if not files:
            print(f"Page {page_number}: no files returned, stopping.")
            break

        print(f"Page {page_number}: {len(files)} files")

        for item in files:
            if not isinstance(item, dict):
                continue
            file_id = item.get("id")
            if not isinstance(file_id, str) or not file_id:
                continue
            if file_id in seen_file_ids:
                continue
            seen_file_ids.add(file_id)

            filename = safe_filename(str(item.get("name") or f"{file_id}.pdf"))
            target = unique_path(Path.cwd() / "pdfs" / filename)
            print(f"  Downloading {filename}")
            download_pdf(file_id, target)
            total_downloaded += 1

        next_page_token = payload.get("nextPageToken")
        if not isinstance(next_page_token, str) or not next_page_token:
            print("No nextPageToken found; finished.")
            break
        if next_page_token == page_token:
            print("nextPageToken repeated; stopping to avoid infinite loop.")
            break
        page_token = next_page_token

    print(f"Downloaded {total_downloaded} PDF files.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        raise SystemExit(130)
