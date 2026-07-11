# Nautical SEO Audit WordPress Plugin

Install the `audit` folder in `wp-content/plugins/`, activate **Nautical SEO Audit**, then add this shortcode to a WordPress page:

```text
[nautical_seo_audit]
```

The shortcode renders the interactive audit dashboard. The dashboard calls this public WordPress REST endpoint:

```text
/wp-json/nautical-audit/v1/page-seo-checker
```

The endpoint accepts a `POST` request with `siteUrl` and optional `timeout` form fields.

Submitted audit URLs and anonymous launch counters are recorded in custom WordPress tables. View them in WordPress admin under:

```text
SEO Audit
```

The same admin page is also available under `Tools > SEO Audit URLs` for compatibility with older installs.

The admin page includes counters for people launching the page, URLs entered, and average URLs entered per person. It also includes a nonce-protected **Export CSV** button to download the log and a nonce-protected **Reset Log** button to clear all recorded audit URLs and counters.
