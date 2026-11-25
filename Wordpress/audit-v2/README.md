# Nautical AI & SEO Audit V2 WordPress Plugin

Install the `audit-v2` folder in `wp-content/plugins/`, activate **Nautical AI & SEO Audit V2**, then add this shortcode to a WordPress page:

```text
[nautical_seo_audit]
```

You can also use the V2-specific shortcode:

```text
[nautical_seo_audit_v2]
```

The shortcode renders the interactive audit dashboard. The dashboard calls this public WordPress REST endpoint:

```text
/wp-json/nautical-audit-v2/v1/page-seo-checker
```

The endpoint accepts a `POST` request with a required `siteUrl` and optional `timeout`. The audit runs before contact details are requested. Completed reports are cached on the server for one hour; the response contains an unlock token. The dashboard shows an obscured report preview behind a contact form. Both name and phone number are required to unlock the full report through the `nautical_audit_v2_unlock` AJAX action. Unlocking updates the existing audit log entry without rerunning the audit.

Submitting `aa` as the name (ignoring case and surrounding spaces) unlocks the report while removing its preliminary audit log entry and the current page launch from the People Launching Page count. Earlier page launches remain counted. Neither the name nor phone number is saved for that audit.

As of 2.0.64, People Launching Page counts visitors only after a successful contact submission with a name other than `aa`. Opening the page or starting an audit does not increment the count. The legacy page-launch endpoint also defers counting, including requests from cached pages. Existing historical launch counts remain unchanged.

## Query Parameters

Add a `url` query parameter to prefill the audit input field without running the audit automatically:

```text
https://example.com/audit-page/?url=https%3A%2F%2Fwww.example-site.com
```

Add `arnw52=imd` with the `url` parameter to automatically run the audit when the plugin page loads:

```text
https://example.com/audit-page/?arnw52=imd&url=https%3A%2F%2Fwww.example-site.com
```

Every submitted audit input, including invalid and unreachable URLs, and anonymous launch counters are recorded in custom WordPress tables. View them in WordPress admin under:

```text
Tools > AI & SEO Audit V2 Inputs
```

The admin page shows the user's name and phone number, the original submitted input, and the normalized requested URL. It includes counters for people launching the page, inputs entered, and average inputs entered per person. It also includes a nonce-protected **Export CSV** button to download the log and a nonce-protected **Reset Log** button to clear all recorded audit inputs and counters.

## Building the installable ZIP

The stylesheet URL includes the plugin version and a hash of the CSS contents. Returning visitors fetch the updated stylesheet on the next page load after an update. Purge any WordPress page cache or CDN HTML cache after installing an update so cached pages reference the new stylesheet URL.

From the repository's `Wordpress` directory, run:

```powershell
.\build-audit-v2.ps1
```

The build script preserves the stable `audit-v2/nautical-seo-audit.php` plugin path and writes ZIP entry names with forward slashes so WordPress recognizes each release as an upgrade of the installed plugin.
