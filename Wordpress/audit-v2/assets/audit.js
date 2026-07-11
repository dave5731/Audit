(function () {
  const { createElement: h, useEffect, useRef, useState } = wp.element;
  const settings = window.NauticalAuditV2Settings || window.NauticalAuditSettings || {};
  const visitorStorageKey = "nauticalAuditV2VisitorId";
  let pageLaunchRecorded = false;

  function createVisitorId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }

    return `visitor-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
  }

  function visitorId() {
    try {
      let stored = window.localStorage.getItem(visitorStorageKey);
      if (!stored) {
        stored = createVisitorId();
        window.localStorage.setItem(visitorStorageKey, stored);
      }
      return stored;
    } catch (error) {
      return createVisitorId();
    }
  }

  function postAuditAction(action, fields = {}) {
    if (!settings.ajaxUrl || !action) {
      return Promise.resolve(null);
    }

    const body = new FormData();
    body.append("action", action);
    body.append("visitorId", visitorId());
    Object.entries(fields).forEach(([key, value]) => {
      body.append(key, value);
    });

    return fetch(settings.ajaxUrl, {
      method: "POST",
      body
    });
  }

  function normalizeDisplayUrl(value) {
    const trimmed = (value || "").trim();
    if (!trimmed) return "";
    return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  }

  function initialUrlFromQuery() {
    return new URLSearchParams(window.location.search).get("url") || "";
  }

  function shouldAutoRunFromQuery() {
    return new URLSearchParams(window.location.search).get("arnw52") === "imd";
  }

  function boolStatus(value) {
    return value ? "pass" : "fail";
  }

  function presentText(value) {
    return value ? "Present" : "Missing";
  }

  function passOrFailDetail(value, passMessage, failMessage) {
    return value ? passMessage : failMessage;
  }

  function normalizeImageProblems(items, pageUrl) {
    return (items || []).map((item) => {
      if (typeof item === "string") {
        return { url: item, page_url: pageUrl || "" };
      }
      return {
        url: item.url || item.image_url || "[image source missing]",
        page_url: item.page_url || item.pageUrl || pageUrl || ""
      };
    });
  }

  function pendingAuditChecks() {
    return [
      { id: "title", label: "Title Tag", status: "checking", result: "Checking", detail: "Checking the page title.", delay: 450 },
      { id: "description", label: "Description", status: "checking", result: "Checking", detail: "Checking the meta description.", delay: 720 },
      { id: "canonical", label: "Canonical URL", status: "checking", result: "Checking", detail: "Checking the canonical URL.", delay: 980 },
      { id: "h1", label: "H1 Tag", status: "checking", result: "Checking", detail: "Checking the primary H1.", delay: 1250 },
      { id: "noindex", label: "Noindex", status: "checking", result: "Checking", detail: "Checking robots directives.", delay: 1510 },
      { id: "phone", label: "Phone Number", status: "checking", result: "Checking", detail: "Checking for a visible phone number.", delay: 1790 },
      { id: "address", label: "Address", status: "checking", result: "Checking", detail: "Checking for a visible street address.", delay: 2070 },
      { id: "privacyPolicy", label: "Privacy Policy", status: "checking", result: "Checking", detail: "Checking for a privacy policy.", delay: 2350 },
      { id: "ssl", label: "SSL", status: "checking", result: "Checking", detail: "Checking HTTPS availability.", delay: 2620 },
      { id: "sitemap", label: "Sitemap", status: "checking", result: "Checking", detail: "Checking for a sitemap.", delay: 2920 },
      { id: "llmsTxt", label: "AI Readiness", status: "checking", result: "Checking", detail: "Checking for llms.txt.", delay: 3210 },
      { id: "analytics", label: "Google Analytics", status: "checking", result: "Checking", detail: "Checking for Google Analytics or Google Tag Manager.", delay: 3500 },
      { id: "images", label: "Image Problems", status: "checking", result: "Checking", detail: "Checking image alt text.", delay: 3780, list: true, listItems: [] }
    ];
  }

  function buildAuditFromResponse(result) {
    const missingImages = normalizeImageProblems(result.images_missing_alt, result.url);
    const llmsTxt = result.llms_txt || result.llmsTxt || {
      exists: false,
      error: "No llms.txt file was found at the site root"
    };
    const contact = result.contact || {};
    const phone = contact.phone || {};
    const address = contact.address || {};
    const privacyPolicy = contact.privacy_policy || contact.privacyPolicy || {};

    return {
      httpStatus: result.status_code || "n/a",
      imagesMissingAlt: missingImages,
      checks: [
        { id: "title", label: "Title Tag", status: boolStatus(result.checks?.title), result: presentText(result.checks?.title), detail: passOrFailDetail(result.checks?.title, "The page has a usable title tag, giving search engines a clear page topic.", "If you don't define one, Google will make one up for you."), delay: 450 },
        { id: "description", label: "Description", status: boolStatus(result.checks?.meta_description_tag), result: presentText(result.checks?.meta_description_tag), detail: passOrFailDetail(result.checks?.meta_description_tag, "The page has a meta description, giving search results and AI systems useful summary context.", "If you don't define one, Google will make one up for you."), delay: 720 },
        { id: "canonical", label: "Canonical URL", status: boolStatus(result.checks?.canonical_url), result: presentText(result.checks?.canonical_url), detail: passOrFailDetail(result.checks?.canonical_url, "A canonical URL was found, helping search engines understand the preferred version of the page.", "Google and AI may disqualify your site."), delay: 980 },
        { id: "h1", label: "H1 Tag", status: boolStatus(result.checks?.h1_tag), result: presentText(result.checks?.h1_tag), detail: passOrFailDetail(result.checks?.h1_tag, "The page has a primary H1, giving visitors and search engines a clear headline.", "Without this signal to Google and AI, you won't rank well."), delay: 1250 },
        { id: "noindex", label: "Noindex", status: result.noindex?.is_noindex ? "fail" : "pass", result: result.noindex?.is_noindex ? "Noindex found" : "Not set", detail: result.noindex?.sources?.map((source) => `${source.source}: ${source.directive}`).join(", ") || "No noindex directive was found.", delay: 1510 },
        { id: "phone", label: "Phone Number", status: boolStatus(phone.exists), result: phone.exists ? "Found" : "Missing", detail: passOrFailDetail(phone.exists, "A phone number was found, giving visitors a direct conversion path.", "Without a phone number you will generally receive 1/2 as many phone calls if your phone number is not on your main page."), delay: 1790 },
        { id: "address", label: "Address", status: boolStatus(address.exists), result: address.exists ? "Found" : "Missing", detail: passOrFailDetail(address.exists, "A street address was found, helping reinforce local trust and business legitimacy.", "Google views this as a trust signal to have this on your website."), delay: 2070 },
        { id: "privacyPolicy", label: "Privacy Policy", status: boolStatus(privacyPolicy.exists), result: privacyPolicy.exists ? "Found" : "Missing", detail: passOrFailDetail(privacyPolicy.exists, "A privacy policy was found, supporting trust and basic site compliance expectations.", "Google may evaluate your site as less trustworthy if you don't have this."), delay: 2350 },
        { id: "ssl", label: "SSL", status: boolStatus(result.ssl?.has_ssl), result: result.ssl?.has_ssl ? "Enabled" : "Not available", detail: passOrFailDetail(result.ssl?.has_ssl, "SSL is enabled, so visitors and search engines can access the site over HTTPS.", result.ssl?.error || "HTTPS endpoint check completed."), delay: 2620 },
        { id: "sitemap", label: "Sitemap", status: boolStatus(result.sitemap?.exists), result: result.sitemap?.exists ? "Found" : "Not found", detail: passOrFailDetail(result.sitemap?.exists, "A sitemap was found, helping search engines discover important pages more reliably.", "If you don't have this, Google and AI services may have trouble discovering everything on your site so it can be shown."), delay: 2920 },
        { id: "llmsTxt", label: "AI Readiness", status: boolStatus(llmsTxt.exists), result: llmsTxt.exists ? "Found" : "Not AI Ready", detail: passOrFailDetail(llmsTxt.exists, "An llms.txt file was found, helping guide AI systems toward important public content.", llmsTxt.error || "No llms.txt file was found at the site root."), delay: 3210 },
        { id: "analytics", label: "Google Analytics", status: boolStatus(result.google_analytics_present), result: result.google_analytics_present ? "Detected" : "Not detected", detail: result.google_analytics_present ? "A Google Analytics or Google Tag Manager tracking pattern was found." : "No Google Analytics or Google Tag Manager tracking pattern was found.", delay: 3500 },
        { id: "images", label: "Image Problems", status: missingImages.length ? "warn" : "pass", result: `${missingImages.length} images`, detail: missingImages.length ? "Without alt text on your images, Google and AI services may rank you lower. Images without usable alt text are listed below." : "No images missing alt text were found.", delay: 3780, list: true, listItems: missingImages }
      ]
    };
  }

  function statusText(status) {
    if (status === "pass") return "Pass";
    if (status === "fail") return "Needs Work";
    if (status === "warn") return "Review";
    return "Checking";
  }

  function calculateScore(checks) {
    if (!checks.length) return 0;
    const weighted = checks.reduce((total, check) => {
      if (check.status === "pass") return total + 1;
      if (check.status === "warn") return total + 0.5;
      return total;
    }, 0);
    return Math.round((weighted / checks.length) * 100);
  }

  function categoryScore(checks, ids) {
    const selected = checks.filter((check) => ids.includes(check.id));
    const resolved = selected.filter((check) => check.status !== "checking");
    if (!selected.length) return { score: 0, passed: 0, total: 0, resolved: 0 };
    const passed = resolved.filter((check) => check.status === "pass").length;
    const partial = resolved.filter((check) => check.status === "warn").length * 0.5;
    return {
      score: Math.round(((passed + partial) / selected.length) * 100),
      passed,
      total: selected.length,
      resolved: resolved.length
    };
  }

  function categoryStatus(score, resolved) {
    if (!resolved) return "checking";
    if (score < 50) return "danger";
    if (score < 70) return "warning";
    return "";
  }

  function healthStatus(score) {
    if (score < 70) return "danger";
    if (score < 90) return "warning";
    return "good";
  }

  function categoryRows(checks) {
    return [
      { icon: "S", label: "Core SEO", detail: "Title, description, H1, canonical", ...categoryScore(checks, ["title", "description", "canonical", "h1", "noindex"]) },
      { icon: "T", label: "Trust Signals", detail: "Address, phone, privacy policy", ...categoryScore(checks, ["phone", "address", "privacyPolicy"]) },
      { icon: "C", label: "Technical", detail: "SSL, sitemap, noindex, analytics", ...categoryScore(checks, ["ssl", "sitemap", "analytics"]) },
      { icon: "AI", label: "AI Readiness", detail: "llms.txt and GEO discovery signals", ...categoryScore(checks, ["llmsTxt", "images"]) }
    ];
  }

  function App() {
    const initialUrl = normalizeDisplayUrl(initialUrlFromQuery());
    const [inputUrl, setInputUrl] = useState(initialUrl);
    const [submittedUrl, setSubmittedUrl] = useState("");
    const [activeAudit, setActiveAudit] = useState({ httpStatus: "n/a", imagesMissingAlt: [], checks: [] });
    const [completed, setCompleted] = useState({});
    const [auditLoading, setAuditLoading] = useState(false);
    const [auditError, setAuditError] = useState("");
    const [auditReady, setAuditReady] = useState(false);
    const [schedulerOpen, setSchedulerOpen] = useState(false);
    const [schedulerPlacement, setSchedulerPlacement] = useState("top");
    const schedulerRef = useRef(null);
    const autoRunStarted = useRef(false);

    useEffect(() => {
      if (pageLaunchRecorded) return;
      pageLaunchRecorded = true;
      postAuditAction(settings.launchAction).catch(() => {});
    }, []);

    useEffect(() => {
      if (!shouldAutoRunFromQuery() || autoRunStarted.current || !initialUrl) return;
      autoRunStarted.current = true;
      runAudit(initialUrl, false);
    }, []);

    useEffect(() => {
      setCompleted({});
      if (!submittedUrl || !auditReady) return undefined;
      const timers = activeAudit.checks.map((check) =>
        window.setTimeout(() => {
          setCompleted((current) => ({ ...current, [check.id]: true }));
        }, check.delay)
      );
      return () => timers.forEach(window.clearTimeout);
    }, [submittedUrl, activeAudit, auditReady]);

    useEffect(() => {
      if (!schedulerOpen) return;
      const scrollTimer = window.setTimeout(() => {
        window.requestAnimationFrame(() => {
          const panel = schedulerRef.current;
          if (!panel) return;

          panel.focus({ preventScroll: true });

          const rect = panel.getBoundingClientRect();
          const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
          const margin = 20;
          const targetTop = rect.height + margin * 2 <= viewportHeight
            ? window.scrollY + rect.top - Math.max((viewportHeight - rect.height) / 2, margin)
            : window.scrollY + rect.top - margin;

          window.scrollTo({
            top: Math.max(targetTop, 0),
            behavior: "smooth"
          });
        });
      }, 0);

      return () => window.clearTimeout(scrollTimer);
    }, [schedulerOpen, schedulerPlacement]);

    const completedChecks = activeAudit.checks.filter((check) => completed[check.id]);
    const passCount = completedChecks.filter((check) => check.status === "pass").length;
    const displayChecks = activeAudit.checks.map((check) =>
      completed[check.id] ? check : { ...check, status: "checking", result: "Checking" }
    );
    const overallScore = calculateScore(displayChecks);

    async function runAudit(url, updateHistory = true) {
      const normalized = normalizeDisplayUrl(url);
      if (!normalized) return;

      setSubmittedUrl(normalized);
      setAuditLoading(true);
      setAuditError("");
      setAuditReady(false);
      setActiveAudit({ httpStatus: "n/a", imagesMissingAlt: [], checks: pendingAuditChecks() });
      setCompleted({});
      if (updateHistory) {
        window.history.replaceState(null, "", `?url=${encodeURIComponent(normalized)}`);
      }

      try {
        const body = new FormData();
        if (settings.ajaxAction) {
          body.append("action", settings.ajaxAction);
        }
        body.append("visitorId", visitorId());
        body.append("siteUrl", normalized);
        body.append("timeout", "30");

        const headers = {};
        if (!settings.ajaxUrl && settings.nonce) {
          headers["X-WP-Nonce"] = settings.nonce;
        }

        const response = await fetch(settings.ajaxUrl || settings.restUrl, {
          method: "POST",
          headers,
          body
        });
        const result = await response.json();
        const auditResult = result.success === true && result.data ? result.data : result;

        if (!response.ok || result.success === false || result.code) {
          throw new Error(result.data?.message || result.message || result.error || `Audit request failed with HTTP ${response.status}`);
        }

        setActiveAudit(buildAuditFromResponse(auditResult));
        setAuditReady(true);
      } catch (error) {
        setAuditError(error.message || "Unable to run audit.");
        setAuditReady(false);
      } finally {
        setAuditLoading(false);
      }
    }

    async function submitUrl(event) {
      event.preventDefault();
      await runAudit(inputUrl);
    }

    function openScheduler(event, placement = "top") {
      event.preventDefault();
      if (schedulerOpen && schedulerPlacement === placement) {
        setSchedulerOpen(false);
        return;
      }
      setSchedulerPlacement(placement);
      setSchedulerOpen(true);
    }

    function renderScheduler() {
      return h(MeetingScheduler, {
        onClose: () => setSchedulerOpen(false),
        panelRef: schedulerRef
      });
    }

    const hasLowerContent = auditLoading || auditError || auditReady || schedulerOpen;

    return h(
      "main",
      { className: `shell${hasLowerContent ? " has-lower-content" : " is-initial"}` },
      h(
        "section",
        { className: "top-band" },
        h(
          "div",
          { className: "top-inner hero" },
          h(
            "div",
            { className: "hero-intro" },
            h("h1", null, "Free SEO Instant Audit"),
            h("p", { className: "subtitle" }, "A visual snapshot of the SEO and AI-readiness signals that help search engines understand, trust, and rank a page."),
            submittedUrl && auditReady ? h("div", { className: "audit-target" }, `Audited URL: ${submittedUrl}`) : null,
            h(
              "form",
              { className: "audit-form", onSubmit: submitUrl },
              h("input", {
                className: "audit-input",
                value: inputUrl,
                onChange: (event) => setInputUrl(event.target.value),
                placeholder: "https://example.com",
                "aria-label": "Audit URL",
                autoFocus: true
              }),
              h("button", { className: "audit-button", type: "submit", disabled: auditLoading }, auditLoading ? "Running..." : "Run Audit")
            )
          ),
          auditReady
            ? h(OverallHealth, { score: overallScore })
            : null
        )
      ),
      hasLowerContent
        ? h(
          "section",
          { className: "content" },
          auditLoading ? h("div", { className: "scheduler-panel" }, "Running the SEO audit...") : null,
          auditError ? h(ErrorPanel, { submittedUrl, inputUrl, auditError }) : null,
          schedulerOpen && schedulerPlacement === "top" ? renderScheduler() : null,
          auditLoading
            ? h(
              "section",
              { className: "dashboard dashboard-loading" },
              h(CategoryPerformance, { checks: displayChecks })
            )
            : null,
          auditReady
            ? h(
              wp.element.Fragment,
              null,
              h(
                "section",
                { className: "dashboard" },
                h(CategoryPerformance, { checks: displayChecks }),
                h(VisualIssueMap, { checks: displayChecks })
              ),
              h(
                "div",
                { className: "result-grid" },
                activeAudit.checks.map((check) =>
                  h(CheckCard, {
                    key: check.id,
                    check,
                    ready: Boolean(completed[check.id])
                  })
                )
              ),
              h(PriorityTimeline, { checks: displayChecks }),
              h(AuditOffer, {
                onSchedule: (event) => openScheduler(event, "bottom"),
                scheduler: schedulerOpen && schedulerPlacement === "bottom" ? renderScheduler() : null
              })
            )
            : auditLoading
              ? null
              : null
        )
        : null
    );
  }

  function ErrorPanel({ submittedUrl, inputUrl, auditError }) {
    return h(
      "div",
      { className: "audit-error-panel", role: "alert" },
      h("div", { className: "audit-error-title" }, "We could not reach that URL"),
      h("div", { className: "audit-error-copy" }, "Check that the address is spelled correctly, the site is online, and the URL starts with http:// or https://."),
      h("div", { className: "audit-error-detail" }, `URL: ${submittedUrl || inputUrl}`),
      h("div", { className: "audit-error-detail" }, `Details: ${auditError}`)
    );
  }

  function OverallHealth({ score }) {
    const status = healthStatus(score);

    return h(
      "aside",
      { className: "hero-side" },
      h(
        "div",
        { className: "hero-card" },
        h("div", { className: "hero-card-label" }, "Overall Health"),
        h(
          "div",
          { className: "hero-score" },
          h(
            "div",
            { className: `score-ring ${status}`, style: { "--score": `${score}%` } },
            h(
              "div",
              null,
              h("strong", null, score),
              h("span", null, "Audit Score")
            )
          )
        )
      )
    );
  }

  function CategoryPerformance({ checks }) {
    const rows = categoryRows(checks);

    return h(
      "div",
      { className: "panel category-panel" },
      h("h2", null, "Category Performance"),
      h(
        "div",
        { className: "category-bars" },
        rows.map((row) => {
          const status = categoryStatus(row.score, row.resolved);
          return h(
            "div",
            { className: "bar-row", key: row.label },
            h("span", null, row.label),
            h("div", { className: "bar-track" }, h("div", { className: `bar-fill ${status}`, style: { width: row.resolved ? `${row.score}%` : "100%" } })),
            h("span", null, row.resolved ? `${row.score}%` : "Checking")
          );
        })
      )
    );
  }

  function VisualIssueMap({ checks }) {
    return h(
      "div",
      { className: "panel" },
      h("h2", null, "Visual Issue Map"),
      h(
        "div",
        { className: "issue-map" },
        checks.map((check) =>
          h(
            "div",
            { className: `issue-cell ${check.status}`, key: check.id },
            h("strong", null, check.label),
            h("span", null, statusText(check.status))
          )
        )
      )
    );
  }

  function PriorityTimeline({ checks }) {
    const failures = checks.filter((check) => check.status === "fail");
    const warnings = checks.filter((check) => check.status === "warn");
    const passes = checks.filter((check) => check.status === "pass");
    const firstFailure = failures[0]?.label || "the highest priority failed checks";
    const firstWarning = warnings[0]?.label || "items that need review";

    return h(
      "section",
      { className: "panel priority-panel" },
      h("h2", null, "Priority Timeline"),
      h(
        "div",
        { className: "timeline" },
        h(
          "div",
          { className: "timeline-row fail" },
          h("div", { className: "dot" }),
          h("div", null, h("strong", null, `Fix ${firstFailure}`), h("span", null, failures.length ? "Start with the issues most likely to weaken rankings or trust." : "No failing checks were found in this scan.")),
          h("div", { className: "timeline-score" }, "1")
        ),
        h(
          "div",
          { className: "timeline-row warn" },
          h("div", { className: "dot" }),
          h("div", null, h("strong", null, `Review ${firstWarning}`), h("span", null, warnings.length ? "These items may need judgment before changing the page." : "No warning items were found.")),
          h("div", { className: "timeline-score" }, "2")
        ),
        h(
          "div",
          { className: "timeline-row pass" },
          h("div", { className: "dot" }),
          h("div", null, h("strong", null, "Preserve working signals"), h("span", null, `${passes.length} checks are already passing and should be kept intact.`)),
          h("div", { className: "timeline-score" }, "3")
        )
      )
    );
  }

  function EmptyState() {
    return h(
      "div",
      { className: "empty-state" },
      h(
        "div",
        { className: "empty-content" },
        h("div", { className: "empty-title" }, "Run a fast SEO and AEO inspection."),
        h(
          "ul",
          { className: "empty-list" },
          h("li", null, "Find technical issues that can block search engines from understanding or indexing the page."),
          h("li", null, "Spot missing on-page signals like titles, descriptions, headings, canonical URLs, and image alt text."),
          h("li", null, "Check visibility foundations for both traditional SEO and GEO discovery before prioritizing next steps."),
          h("li", null, "Use the results to decide whether a 30 minute comprehensive SEO audit is worth scheduling.")
        )
      )
    );
  }

  function MeetingScheduler({
    onClose,
    panelRef
  }) {
    const meetingUrl = "https://localseomeeting.com/";

    return h(
      "section",
      { className: "scheduler-panel meeting-embed-panel", "aria-label": "Schedule detailed audit meeting", ref: panelRef, tabIndex: -1 },
      h(
        "div",
        { className: "scheduler-head" },
        h(
          "div",
          null,
          h("h2", { className: "scheduler-title" }, "Schedule a detailed audit meeting"),
          h("div", { className: "scheduler-copy" }, "Choose a time on the meeting page below.")
        ),
        h("button", { className: "scheduler-close", type: "button", onClick: onClose, "aria-label": "Close scheduler" }, "x")
      ),
      h(
        "div",
        { className: "meeting-embed-container" },
        h("iframe", {
          className: "meeting-embed-frame",
          src: meetingUrl,
          title: "Local SEO meeting scheduler",
          loading: "lazy",
          referrerPolicy: "strict-origin-when-cross-origin",
          sandbox: "allow-forms allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"
        }),
        h("div", { className: "meeting-embed-fallback" },
          "If the meeting page does not load here, ",
          h("a", { href: meetingUrl, target: "_blank", rel: "noopener noreferrer" }, "open it in a new tab"),
          "."
        )
      )
    );
  }

  function AuditOffer({ onSchedule, scheduler }) {
    return h(
      wp.element.Fragment,
      null,
      h(
        "section",
        { className: "detail-report", "aria-label": "Go Deeper audit offer" },
        h(
          "div",
          null,
          h("div", { className: "detail-eyebrow" }, "Go Deeper"),
          h("h2", null, "Schedule my free 30 minute SEO and AI Readiness review"),
          h("p", null, "Get a deeper review of hundreds of site parameters and a prioritized action plan that separates quick technical fixes from bigger content, local, and GEO visibility opportunities."),
          h(
            "div",
            { className: "report-kpis" },
            h("div", { className: "report-kpi" }, h("strong", null, "100+"), h("span", null, "SEO and GEO parameters")),
            h("div", { className: "report-kpi" }, h("strong", null, "30 min"), h("span", null, "Focused review meeting")),
            h("div", { className: "report-kpi" }, h("strong", null, "1 plan"), h("span", null, "Prioritized next steps"))
          ),
          h(
            "div",
            { className: "detail-actions" },
            h("a", { className: "offer-button", href: "#", role: "button", onClick: onSchedule }, "Schedule Zoom Meeting")
          )
        ),
        h(
          "div",
          { className: "insight-graphic", "aria-hidden": true },
          h(
            "div",
            { className: "radar" },
            h("div", { className: "radar-core" }, "100+", h("br"), "Checks"),
            h("div", { className: "radar-node one" }, "SEO"),
            h("div", { className: "radar-node two" }, "Local"),
            h("div", { className: "radar-node three" }, "AI"),
            h("div", { className: "radar-node four" }, "Trust"),
            h("div", { className: "radar-node five" }, "Tech")
          ),
          h("div", { className: "insight-caption" }, "A deeper review maps technical, local, search, trust, and AI-readiness signals into one prioritized plan.")
        )
      ),
      scheduler
    );
  }

  function Metric({ label, value }) {
    return h(
      "div",
      { className: "metric" },
      h("div", { className: "metric-label" }, label),
      h("div", { className: "metric-value" }, value)
    );
  }

  function CheckCard({ check, ready }) {
    const statusClass = ready ? check.status : "waiting";
    const className = `result-card ${statusClass}${check.list ? " image-list" : ""}`;
    return h(
      "article",
      { className },
      h("div", { className: "status-orb" }, ready ? (check.status === "pass" ? "OK" : check.status === "warn" ? "!" : "!") : "..."),
      h(
        "div",
        { className: "card-head" },
        h("h2", { className: "card-title" }, check.label),
        h("span", { className: `badge ${ready ? check.status : "waiting"}` }, ready ? statusText(check.status) : "Checking")
      ),
      h("div", { className: "card-body" }, ready ? h(ResultContent, { check }) : h(LoadingContent))
    );
  }

  function LoadingContent() {
    return h(
      "div",
      { className: "loader" },
      h("div", { className: "spinner" }),
      h(
        "div",
        { className: "pulse-lines" },
        h("div", { className: "pulse-line" }),
        h("div", { className: "pulse-line short" })
      )
    );
  }

  function ResultContent({ check }) {
    const [expandedItems, setExpandedItems] = useState({});

    function toggleExpanded(key) {
      setExpandedItems((current) => ({ ...current, [key]: !current[key] }));
    }

    return h(
      wp.element.Fragment,
      null,
      h("div", { className: "result-line" }, check.result),
      h("div", { className: "detail" }, check.detail),
      check.list
        ? h(
          "ul",
          { className: "links" },
          normalizeImageProblems(check.listItems, "").map((image, index) => {
            const key = `${image.url}-${index}`;
            const expanded = Boolean(expandedItems[key]);
            return h(
              "li",
              { key },
              h(
                "button",
                {
                  className: "image-problem-toggle",
                  type: "button",
                  onClick: () => toggleExpanded(key),
                  "aria-expanded": expanded
                },
                h("span", null, `Image ${index + 1}`),
                h("span", null, expanded ? "Hide" : "Expand")
              ),
              expanded
                ? h(
                  "div",
                  { className: "image-problem-detail" },
                  h(
                    "div",
                    null,
                    h("strong", null, "Image URL: "),
                    image.url
                  ),
                  h(
                    "div",
                    null,
                    h("strong", null, "Found on page: "),
                    image.page_url || "Current audited page"
                  )
                )
                : null
            );
          })
        )
        : null
    );
  }

  function mountAuditDashboards() {
    document.querySelectorAll("[data-nautical-audit-root]").forEach((root) => {
      if (root.dataset.nauticalAuditMounted === "true") return;
      root.dataset.nauticalAuditMounted = "true";
      root.innerHTML = "";

      if (typeof wp.element.createRoot === "function") {
        wp.element.createRoot(root).render(h(App));
        return;
      }

      if (typeof wp.element.render === "function") {
        wp.element.render(h(App), root);
        return;
      }

      root.innerHTML = '<div class="nautical-audit-fallback">Unable to load the SEO audit dashboard.</div>';
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAuditDashboards);
  } else {
    mountAuditDashboards();
  }
})();
