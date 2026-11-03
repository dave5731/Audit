# Standalone External Website SEO Audit

This Windows command-line application prompts for a URL, opens a real visible
Edge or Chrome browser, audits the rendered page, and writes a PDF into
`audit-results` under the current directory.

The PDF bundles the official Nautical Agency logo and follows the WordPress
plugin's navy, teal, green, and red results design. Reports include overall
health, category performance, a visual issue map, detailed result cards, and a
priority improvement plan.

## Cloudflare support

The app uses the locally installed Microsoft Edge or Google Chrome rather than
a basic HTTP scraper. If Cloudflare presents an interactive verification page,
complete it in the opened browser and then press Enter in the console. The
persistent local profile retains the resulting first-party cookies for later
audits. No software can guarantee access when a site owner explicitly blocks
automation, but this flow supports legitimate interactive Cloudflare checks.

## Run from Python

```powershell
py -m pip install -r standaloneaudit/requirements.txt
py -m playwright install chromium
py standaloneaudit/standalone_audit.py
```

The Playwright Chromium download is only a fallback. If Edge or Chrome is
installed, the application uses that browser first.

## Build the executable

```powershell
.\standaloneaudit\build.ps1
```

The executable is written to:

```text
standaloneaudit/dist/standaloneaudit.exe
```

The target computer needs Microsoft Edge, Google Chrome, or Playwright's
Chromium installed. The executable does not silently bypass access controls;
interactive verification must be completed by the user when requested.
