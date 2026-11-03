from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse


NAVIGATION_TIMEOUT_MS = 45_000
CHALLENGE_MARKERS = (
    "checking your browser",
    "just a moment",
    "verify you are human",
    "performing security verification",
    "challenges.cloudflare.com",
)


@dataclass
class Check:
    label: str
    passed: bool
    result: str
    recommendation: str


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("A URL is required.")
    if not re.match(r"^https?://", value, re.IGNORECASE):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid HTTP or HTTPS URL.")
    return value


def site_root(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))


def looks_like_challenge(title: str, content: str, status: int | None, headers: dict[str, str]) -> bool:
    sample = (title + " " + content[:30_000]).lower()
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    if status == 403 and ("cf-ray" in headers or "cloudflare" in headers.get("server", "").lower()):
        return True
    return any(marker in sample for marker in CHALLENGE_MARKERS)


def wait_for_cloudflare(page: Any, response: Any) -> Any:
    headers = response.all_headers() if response else {}
    status = response.status if response else None
    if not looks_like_challenge(page.title(), page.content(), status, headers):
        return response

    print("\nCloudflare has requested browser verification.")
    print("Complete the verification in the browser window, then return here.")
    input("Press Enter after the real website has loaded... ")
    page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
    response = page.reload(wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
    headers = response.all_headers() if response else {}
    status = response.status if response else None
    if looks_like_challenge(page.title(), page.content(), status, headers):
        raise RuntimeError("Cloudflare verification was not completed, so the page could not be audited.")
    return response


def first_phone(text: str) -> str:
    match = re.search(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}", text)
    return match.group(0).strip() if match else ""


def first_address(text: str) -> str:
    pattern = (
        r"\b\d{1,6}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,5}\s+"
        r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|"
        r"Lane|Ln\.?|Court|Ct\.?|Place|Pl\.?|Way|Circle|Highway|Hwy\.?)\b[^\n,;]{0,80}"
    )
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0).strip(" ,.;") if match else ""


def browser_status(context: Any, url: str) -> dict[str, Any]:
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        return {
            "status": response.status if response else None,
            "url": page.url,
            "error": "",
        }
    except Exception as exc:
        return {"status": None, "url": page.url or url, "error": str(exc)}
    finally:
        page.close()


def audit_page(context: Any, url: str) -> dict[str, Any]:
    page = context.new_page()
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        response = wait_for_cloudflare(page, response)
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        status = response.status if response else None
        if status is None or not 200 <= status < 400:
            raise RuntimeError(f"The website returned HTTP {status or 'no response'}.")

        headers = response.all_headers()
        final_url = page.url
        title = page.title().strip()
        meta_description = page.locator('meta[name="description"]').first.get_attribute("content") or "" if page.locator('meta[name="description"]').count() else ""
        canonical = page.locator('link[rel~="canonical"]').first.get_attribute("href") or "" if page.locator('link[rel~="canonical"]').count() else ""
        h1_values = [value.strip() for value in page.locator("h1").all_text_contents() if value.strip()]
        visible_text = page.locator("body").inner_text(timeout=10_000)
        source = page.content()
        robots_values = page.locator('meta[name="robots"], meta[name="googlebot"]').evaluate_all(
            "els => els.map(el => el.content || '')"
        )
        x_robots = headers.get("x-robots-tag", "")
        noindex = any(re.search(r"(?:^|[\s,;])(?:noindex|none)(?:$|[\s,;])", value, re.I) for value in [*robots_values, x_robots])
        phone = first_phone(visible_text)
        address = first_address(visible_text)
        privacy_links = page.locator('a[href*="privacy" i]')
        privacy_url = privacy_links.first.get_attribute("href") or "" if privacy_links.count() else ""
        if privacy_url:
            privacy_url = urljoin(final_url, privacy_url)
        missing_images = page.locator('img:not([alt]), img[alt=""]')
        image_urls = missing_images.evaluate_all(
            "els => els.map(el => el.currentSrc || el.src || el.dataset.src || '[image source missing]')"
        )
        analytics = bool(re.search(
            r"googletagmanager\.com|google-analytics\.com|(?:G|UA)-[A-Z0-9-]{6,}|GoogleAnalyticsObject",
            source,
            re.IGNORECASE,
        ))

        root = site_root(final_url)
        https_url = urlunparse(urlparse(final_url)._replace(scheme="https"))
        ssl = browser_status(context, https_url)
        sitemap_checks = [browser_status(context, urljoin(root, name)) for name in ("sitemap.xml", "sitemap_index.xml")]
        sitemap = next((item for item in sitemap_checks if item["status"] and 200 <= item["status"] < 400), None)
        llms = browser_status(context, urljoin(root, "llms.txt"))
        llms_exists = bool(llms["status"] and 200 <= llms["status"] < 400)

        checks = [
            Check("Title tag", bool(title), title or "Missing", "Add a unique, descriptive page title."),
            Check("Meta description", bool(meta_description.strip()), meta_description.strip() or "Missing", "Add a concise meta description."),
            Check("Canonical URL", bool(canonical.strip()), canonical.strip() or "Missing", "Declare the preferred canonical URL."),
            Check("H1 heading", bool(h1_values), ", ".join(h1_values) or "Missing", "Add one clear primary heading."),
            Check("Indexability", not noindex, "Indexable" if not noindex else "Noindex detected", "Remove noindex if this page should appear in search."),
            Check("Phone number", bool(phone), phone or "Not found", "Show a phone number when relevant to the business."),
            Check("Street address", bool(address), address or "Not found", "Show a consistent business address when relevant."),
            Check("Privacy policy", bool(privacy_url), privacy_url or "Not found", "Link to a privacy policy."),
            Check("HTTPS", bool(ssl["status"] and ssl["url"].startswith("https://")), ssl["url"], "Serve the page successfully over HTTPS."),
            Check("Sitemap", sitemap is not None, sitemap["url"] if sitemap else "Not found", "Publish sitemap.xml or sitemap_index.xml."),
            Check("llms.txt", llms_exists, llms["url"] if llms_exists else "Not found", "Consider publishing an llms.txt file for AI systems."),
            Check("Google Analytics", analytics, "Detected" if analytics else "Not detected", "Install analytics if visitor measurement is required."),
            Check("Image alt text", not image_urls, f"{len(image_urls)} image(s) missing alt text", "Add meaningful alt text to informative images."),
        ]
        return {
            "requested_url": url,
            "final_url": final_url,
            "status": status,
            "captured_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "checks": checks,
            "missing_images": image_urls,
        }
    finally:
        page.close()


def report_html(result: dict[str, Any]) -> str:
    checks: list[Check] = result["checks"]
    passed = sum(check.passed for check in checks)
    score = round(passed / len(checks) * 100) if checks else 0
    logo_path = resource_path("assets/nautical-logo.png")
    logo_data = base64.b64encode(logo_path.read_bytes()).decode("ascii")

    category_labels = {
        "Technical foundations": {"Title tag", "Meta description", "Canonical URL", "H1 heading", "Indexability", "HTTPS", "Sitemap"},
        "Trust and local signals": {"Phone number", "Street address", "Privacy policy"},
        "AI and measurement": {"llms.txt", "Google Analytics", "Image alt text"},
    }
    category_cards = []
    for category, labels in category_labels.items():
        category_checks = [check for check in checks if check.label in labels]
        category_passed = sum(check.passed for check in category_checks)
        category_score = round(category_passed / len(category_checks) * 100) if category_checks else 0
        category_cards.append(
            f"<div class='category-card'><div class='category-score'>{category_score}%</div>"
            f"<strong>{html.escape(category)}</strong><span>{category_passed}/{len(category_checks)} checks passed</span>"
            f"<div class='bar'><i style='width:{category_score}%'></i></div></div>"
        )

    issue_nodes = "".join(
        f"<div class='issue-node {'ok' if check.passed else 'problem'}'>"
        f"<b>{'✓' if check.passed else '!'}</b><span>{html.escape(check.label)}</span></div>"
        for check in checks
    )
    result_cards = "".join(
        f"<article class='result-card {'ok' if check.passed else 'problem'}'>"
        f"<div class='card-top'><h3>{html.escape(check.label)}</h3>"
        f"<span class='status'>{'PASS' if check.passed else 'NEEDS WORK'}</span></div>"
        f"<div class='finding'>{html.escape(check.result)}</div>"
        f"<p>{html.escape(check.recommendation)}</p></article>"
        for check in checks
    )
    failed_checks = [check for check in checks if not check.passed]
    priorities = "".join(
        f"<div class='priority'><span>{index}</span><div><strong>{html.escape(check.label)}</strong>"
        f"<p>{html.escape(check.recommendation)}</p></div><em>{'HIGH' if index <= 3 else 'MEDIUM'}</em></div>"
        for index, check in enumerate(failed_checks, 1)
    ) or "<div class='all-clear'>All checks passed. Continue monitoring the page as it changes.</div>"
    image_section = ""
    if result["missing_images"]:
        items = "".join(f"<li>{html.escape(value)}</li>" for value in result["missing_images"])
        image_section = f"<section class='section'><h2>Images missing alt text</h2><ul class='image-list'>{items}</ul></section>"
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
      @page {{ size: Letter; margin: .38in; }}
      * {{ box-sizing: border-box; }}
      body {{ margin:0; font-family: Arial, sans-serif; color:#17202a; background:#f4f8fb; font-size:10px; }}
      .brand {{ height:58px; padding:8px 16px; background:white; border-bottom:1px solid #d9e4eb; display:flex; align-items:center; justify-content:space-between; }}
      .brand img {{ width:166px; height:auto; }} .brand span {{ color:#667085; font-weight:700; letter-spacing:.08em; }}
      .hero {{ padding:24px; color:white; background:linear-gradient(120deg,#126b73,#106068 62%,#0b2545); display:flex; justify-content:space-between; align-items:center; }}
      .hero h1 {{ margin:0 0 7px; font-size:27px; }} .hero p {{ margin:3px 0; color:#d8f3f5; max-width:490px; overflow-wrap:anywhere; }}
      .score-ring {{ width:116px; height:116px; border-radius:50%; padding:10px; background:conic-gradient(#2bb8c5 0 {score}%,#cfdae5 {score}% 100%); }}
      .score-inner {{ width:100%; height:100%; border-radius:50%; background:white; color:#0b2545; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
      .score-inner strong {{ font-size:28px; }} .score-inner span {{ color:#667085; font-size:8px; font-weight:700; letter-spacing:.07em; }}
      .content {{ padding:18px; }} .section {{ margin-bottom:18px; }}
      .section-title {{ margin:0 0 9px; color:#0b2545; font-size:17px; }} .section-kicker {{ color:#667085; margin:-5px 0 10px; }}
      .categories {{ display:grid; grid-template-columns:repeat(3,1fr); gap:9px; }}
      .category-card {{ background:white; border:1px solid #d9e4eb; border-radius:10px; padding:12px; min-height:98px; }}
      .category-card strong,.category-card span {{ display:block; }} .category-card strong {{ font-size:11px; color:#0b2545; margin:4px 0; }}
      .category-card span {{ color:#667085; font-size:9px; }} .category-score {{ float:right; color:#0f8b6f; font-size:19px; font-weight:800; }}
      .bar {{ clear:both; height:6px; border-radius:6px; background:#e5edf3; margin-top:11px; overflow:hidden; }} .bar i {{ display:block; height:100%; background:linear-gradient(90deg,#0f8b6f,#2bb8c5); }}
      .issue-map {{ background:white; border:1px solid #d9e4eb; border-radius:12px; padding:12px; display:grid; grid-template-columns:repeat(5,1fr); gap:7px; }}
      .issue-node {{ border-radius:8px; padding:8px 5px; text-align:center; min-height:55px; }} .issue-node b {{ display:block; margin:auto auto 5px; width:20px; height:20px; line-height:20px; border-radius:50%; color:white; }}
      .issue-node span {{ font-size:8px; font-weight:700; }} .issue-node.ok {{ background:#dff7ef; color:#08765e; }} .issue-node.ok b {{ background:#0f8b6f; }}
      .issue-node.problem {{ background:#ffe7e3; color:#912018; }} .issue-node.problem b {{ background:#b42318; }}
      .results {{ display:grid; grid-template-columns:repeat(2,1fr); gap:9px; }}
      .result-card {{ background:white; border:1px solid #d9e4eb; border-left:5px solid #0f8b6f; border-radius:9px; padding:11px; break-inside:avoid; min-height:105px; }}
      .result-card.problem {{ border-left-color:#b42318; }} .card-top {{ display:flex; justify-content:space-between; gap:8px; align-items:center; }}
      .card-top h3 {{ margin:0; color:#0b2545; font-size:12px; }} .status {{ font-size:7px; font-weight:800; padding:4px 6px; border-radius:10px; color:#08765e; background:#dff7ef; white-space:nowrap; }}
      .problem .status {{ color:#912018; background:#ffe1dd; }} .finding {{ margin:9px 0 5px; font-weight:700; overflow-wrap:anywhere; }} .result-card p {{ margin:0; color:#667085; line-height:1.35; }}
      .priority-panel {{ background:white; border:1px solid #d9e4eb; border-radius:12px; padding:13px; }}
      .priority {{ display:grid; grid-template-columns:28px 1fr 50px; gap:9px; align-items:center; padding:9px 0; border-bottom:1px solid #e7edf2; break-inside:avoid; }}
      .priority:last-child {{ border-bottom:0; }} .priority>span {{ width:24px; height:24px; line-height:24px; border-radius:50%; text-align:center; color:white; background:#0b2545; font-weight:800; }}
      .priority strong {{ color:#0b2545; }} .priority p {{ margin:2px 0 0; color:#667085; }} .priority em {{ font-style:normal; font-size:7px; color:#912018; background:#ffe1dd; border-radius:10px; padding:4px; text-align:center; font-weight:800; }}
      .all-clear {{ padding:14px; color:#08765e; background:#dff7ef; border-radius:8px; }}
      .image-list {{ background:white; border:1px solid #d9e4eb; border-radius:9px; padding:14px 25px; }} li {{ margin-bottom:5px; overflow-wrap:anywhere; }}
      .footer {{ margin-top:18px; padding:13px 18px; color:white; background:linear-gradient(135deg,#0b2545,#106068); border-radius:10px; display:flex; justify-content:space-between; }}
      .footer strong {{ font-size:13px; }} .footer span {{ color:#d8f3f5; }}
    </style></head><body>
      <header class='brand'><img src='data:image/png;base64,{logo_data}' alt='Nautical Agency'><span>AI &amp; SEO AUDIT REPORT</span></header>
      <section class='hero'><div><h1>AI &amp; SEO Website Audit</h1><p>{html.escape(result['final_url'])}</p>
      <p>HTTP {result['status']} &middot; Captured {html.escape(result['captured_at'])}</p></div>
      <div class='score-ring'><div class='score-inner'><strong>{score}%</strong><span>OVERALL HEALTH</span></div></div></section>
      <main class='content'>
        <section class='section'><h2 class='section-title'>Category performance</h2><p class='section-kicker'>{passed} of {len(checks)} audit checks passed.</p><div class='categories'>{''.join(category_cards)}</div></section>
        <section class='section'><h2 class='section-title'>Visual issue map</h2><p class='section-kicker'>A quick view of healthy signals and areas that need attention.</p><div class='issue-map'>{issue_nodes}</div></section>
        <section class='section'><h2 class='section-title'>Detailed results</h2><div class='results'>{result_cards}</div></section>
        <section class='section'><h2 class='section-title'>Priority improvement plan</h2><div class='priority-panel'>{priorities}</div></section>
        {image_section}
        <footer class='footer'><strong>Nautical Agency</strong><span>Clear direction for stronger search and AI visibility.</span></footer>
      </main>
    </body></html>"""


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / relative_path


def output_path(url: str) -> Path:
    host = re.sub(r"[^A-Za-z0-9.-]+", "-", urlparse(url).netloc).strip("-.") or "website"
    output_dir = Path.cwd() / "audit-results"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{host}-seo-audit-{datetime.now():%Y%m%d-%H%M%S}.pdf"


def launch_context(playwright: Any, profile_dir: Path) -> Any:
    common = {
        "user_data_dir": profile_dir,
        "headless": False,
        "viewport": {"width": 1365, "height": 900},
        "locale": "en-US",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    for channel in ("msedge", "chrome"):
        try:
            return playwright.chromium.launch_persistent_context(channel=channel, **common)
        except Exception:
            continue
    return playwright.chromium.launch_persistent_context(**common)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit an external website and create a PDF report.")
    parser.add_argument("url", nargs="?", help="Website URL; prompts when omitted.")
    args = parser.parse_args()
    print("Standalone External Website SEO Audit")
    print("A browser window will open while the audit runs.\n")
    try:
        url = normalize_url(args.url or input("Website URL: "))
        from playwright.sync_api import sync_playwright

        profile_dir = Path.cwd() / ".standaloneaudit-browser-profile"
        with sync_playwright() as playwright:
            context = launch_context(playwright, profile_dir)
            try:
                result = audit_page(context, url)
                pdf_path = output_path(result["final_url"])
                report_page = context.new_page()
                try:
                    report_page.set_content(report_html(result), wait_until="load")
                    report_page.pdf(path=pdf_path, format="Letter", print_background=True)
                finally:
                    report_page.close()
            finally:
                context.close()
        print(f"\nAudit complete. PDF saved to:\n{pdf_path}")
        return 0
    except KeyboardInterrupt:
        print("\nAudit cancelled.")
        return 130
    except Exception as exc:
        print(f"\nAudit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
