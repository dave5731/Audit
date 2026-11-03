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

The endpoint accepts a `POST` request with required `userName`, `phoneNumber`, and `siteUrl` form fields, plus an optional `timeout` field.

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

From the repository's `Wordpress` directory, run:

```powershell
.\build-audit-v2.ps1
```

The build script preserves the stable `audit-v2/nautical-seo-audit.php` plugin path and writes ZIP entry names with forward slashes so WordPress recognizes each release as an upgrade of the installed plugin.
