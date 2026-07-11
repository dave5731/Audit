<?php
/**
 * Plugin Name: Nautical SEO Audit
 * Description: Displays an interactive SEO audit dashboard and provides a WordPress REST endpoint for page checks.
 * Version: 1.0.42
 * Author: Nautical Agency
 */

if (!defined('ABSPATH')) {
    exit;
}

final class Nautical_SEO_Audit_Plugin
{
    private const REST_NAMESPACE = 'nautical-audit/v1';
    private const REST_ROUTE = '/page-seo-checker';
    private const AJAX_ACTION = 'nautical_audit_page_seo_checker';
    private const LAUNCH_ACTION = 'nautical_audit_page_launch';
    private const VERSION = '1.0.42';
    private const DB_VERSION = '1.1.0';
    private const DB_OPTION = 'nautical_seo_audit_db_version';

    public function __construct()
    {
        add_action('rest_api_init', [$this, 'registerRestRoutes']);
        add_shortcode('nautical_seo_audit', [$this, 'renderShortcode']);
        add_action('wp_enqueue_scripts', [$this, 'registerAssets']);
        add_action('admin_menu', [$this, 'registerAdminMenu']);
        add_action('admin_init', [$this, 'maybeCreateTable']);
        add_action('admin_post_nautical_audit_export_log', [$this, 'exportLogCsv']);
        add_action('wp_ajax_' . self::AJAX_ACTION, [$this, 'handleAjaxAuditRequest']);
        add_action('wp_ajax_nopriv_' . self::AJAX_ACTION, [$this, 'handleAjaxAuditRequest']);
        add_action('wp_ajax_' . self::LAUNCH_ACTION, [$this, 'handlePageLaunchRequest']);
        add_action('wp_ajax_nopriv_' . self::LAUNCH_ACTION, [$this, 'handlePageLaunchRequest']);
    }

    public static function activate(): void
    {
        $plugin = new self();
        $plugin->createTable();
    }

    public function registerAssets(): void
    {
        $baseUrl = plugin_dir_url(__FILE__);

        wp_register_style(
            'nautical-seo-audit',
            $baseUrl . 'assets/audit.css',
            [],
            self::VERSION
        );

        wp_register_script(
            'nautical-seo-audit',
            $baseUrl . 'assets/audit.js',
            ['wp-element'],
            self::VERSION,
            true
        );

        wp_localize_script(
            'nautical-seo-audit',
            'NauticalAuditSettings',
            [
                'restUrl' => esc_url_raw(rest_url(self::REST_NAMESPACE . self::REST_ROUTE)),
                'ajaxUrl' => esc_url_raw(admin_url('admin-ajax.php')),
                'ajaxAction' => self::AJAX_ACTION,
                'launchAction' => self::LAUNCH_ACTION,
                'nonce' => is_user_logged_in() ? wp_create_nonce('wp_rest') : '',
            ]
        );

        wp_enqueue_style('nautical-seo-audit');
        wp_enqueue_script('nautical-seo-audit');
    }

    public function renderShortcode(): string
    {
        wp_enqueue_style('nautical-seo-audit');
        wp_enqueue_script('nautical-seo-audit');

        return '<div class="nautical-audit" data-nautical-audit-root><div class="nautical-audit-fallback">Loading SEO audit dashboard...</div></div>';
    }

    public function registerRestRoutes(): void
    {
        register_rest_route(
            self::REST_NAMESPACE,
            self::REST_ROUTE,
            [
                'methods' => WP_REST_Server::CREATABLE,
                'callback' => [$this, 'handleAuditRequest'],
                'permission_callback' => '__return_true',
                'args' => [
                    'siteUrl' => [
                        'required' => true,
                        'sanitize_callback' => 'esc_url_raw',
                    ],
                    'timeout' => [
                        'required' => false,
                        'sanitize_callback' => 'absint',
                        'default' => 15,
                    ],
                    'visitorId' => [
                        'required' => false,
                        'sanitize_callback' => 'sanitize_text_field',
                        'default' => '',
                    ],
                ],
            ]
        );
    }

    public function handleAuditRequest(WP_REST_Request $request)
    {
        return rest_ensure_response(
            $this->runAudit(
                (string) $request->get_param('siteUrl'),
                (int) $request->get_param('timeout'),
                (string) $request->get_param('visitorId')
            )
        );
    }

    public function handleAjaxAuditRequest(): void
    {
        $siteUrl = isset($_POST['siteUrl']) ? wp_unslash($_POST['siteUrl']) : '';
        $timeout = isset($_POST['timeout']) ? absint($_POST['timeout']) : 15;
        $visitorId = isset($_POST['visitorId']) ? wp_unslash($_POST['visitorId']) : '';
        $result = $this->runAudit((string) $siteUrl, $timeout, (string) $visitorId);

        if (is_wp_error($result)) {
            $errorData = $result->get_error_data();
            $status = is_array($errorData) ? (int) ($errorData['status'] ?? 500) : 500;
            wp_send_json_error(
                [
                    'code' => $result->get_error_code(),
                    'message' => $result->get_error_message(),
                ],
                $status
            );
        }

        wp_send_json_success($result);
    }

    public function handlePageLaunchRequest(): void
    {
        $visitorId = isset($_POST['visitorId']) ? wp_unslash($_POST['visitorId']) : '';
        $this->recordPageLaunch((string) $visitorId);

        wp_send_json_success(['recorded' => true]);
    }

    private function runAudit(string $siteUrl, int $timeout, string $visitorId = '')
    {
        $url = $this->normalizeUrl($siteUrl);
        $timeout = max(1, min(60, $timeout));
        $visitorId = $this->sanitizeVisitorId($visitorId);

        if (!$url) {
            return new WP_Error(
                'nautical_audit_invalid_url',
                'URL must be an http or https URL.',
                ['status' => 400]
            );
        }

        $fetch = $this->fetchUrl($url, $timeout);
        if (is_wp_error($fetch)) {
            $this->recordAuditUrl($url, '', null, $fetch->get_error_message(), $visitorId);
            return $fetch;
        }

        $this->recordAuditUrl($url, $fetch['final_url'], $fetch['status_code'], '', $visitorId);

        $result = $this->analyzeHtml(
            $fetch['body'],
            $fetch['headers'],
            $fetch['final_url'],
            $fetch['status_code']
        );

        $result['ssl'] = $this->checkSsl($url, $timeout);
        $result['sitemap'] = $this->checkSitemap($url, $timeout);
        $result['llms_txt'] = $this->checkLlmsTxt($url, $timeout);

        return $result;
    }

    public function registerAdminMenu(): void
    {
        add_management_page(
            'Nautical SEO Audit URLs',
            'SEO Audit URLs',
            'manage_options',
            'nautical-seo-audit-urls',
            [$this, 'renderAdminPage']
        );
    }

    public function renderAdminPage(): void
    {
        if (!current_user_can('manage_options')) {
            wp_die(esc_html__('You do not have permission to view this page.', 'nautical-seo-audit'));
        }

        global $wpdb;
        $table = $this->tableName();
        $launchTable = $this->launchTableName();

        if (
            isset($_POST['nautical_audit_reset_log'])
            && check_admin_referer('nautical_audit_reset_log', 'nautical_audit_reset_nonce')
        ) {
            $wpdb->query("DELETE FROM {$table}");
            $wpdb->query("DELETE FROM {$launchTable}");
            ?>
            <div class="notice notice-success is-dismissible">
                <p><?php echo esc_html__('The SEO audit URL log and counters have been reset.', 'nautical-seo-audit'); ?></p>
            </div>
            <?php
        }

        $stats = $this->auditStats();
        $rows = $wpdb->get_results(
            "SELECT requested_url, final_url, status_code, error_message, user_ip, created_at FROM {$table} ORDER BY created_at DESC, id DESC",
            ARRAY_A
        );

        ?>
        <div class="wrap">
            <h1><?php echo esc_html__('Nautical SEO Audit URLs', 'nautical-seo-audit'); ?></h1>
            <p style="color:#646970; margin-top:-6px;">
                <?php echo esc_html(sprintf(__('Plugin admin version: %s', 'nautical-seo-audit'), self::VERSION)); ?>
            </p>
            <p><?php echo esc_html__('URLs submitted through the audit dashboard are recorded here.', 'nautical-seo-audit'); ?></p>
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:12px; margin: 16px 0;">
                <div style="background:#fff; border:1px solid #dcdcde; padding:16px;">
                    <div style="color:#646970; font-size:13px;"><?php echo esc_html__('People Launching Page', 'nautical-seo-audit'); ?></div>
                    <div style="font-size:28px; font-weight:600; margin-top:6px;"><?php echo esc_html(number_format_i18n($stats['people'])); ?></div>
                </div>
                <div style="background:#fff; border:1px solid #dcdcde; padding:16px;">
                    <div style="color:#646970; font-size:13px;"><?php echo esc_html__('URLs Entered', 'nautical-seo-audit'); ?></div>
                    <div style="font-size:28px; font-weight:600; margin-top:6px;"><?php echo esc_html(number_format_i18n($stats['urls'])); ?></div>
                </div>
                <div style="background:#fff; border:1px solid #dcdcde; padding:16px;">
                    <div style="color:#646970; font-size:13px;"><?php echo esc_html__('Average URLs Per Person', 'nautical-seo-audit'); ?></div>
                    <div style="font-size:28px; font-weight:600; margin-top:6px;"><?php echo esc_html(number_format_i18n($stats['average_urls_per_person'], 2)); ?></div>
                </div>
            </div>
            <div style="display:flex; gap:8px; align-items:center; margin: 16px 0;">
                <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                    <input type="hidden" name="action" value="nautical_audit_export_log">
                    <?php wp_nonce_field('nautical_audit_export_log', 'nautical_audit_export_nonce'); ?>
                    <button type="submit" class="button button-primary">
                        <?php echo esc_html__('Export CSV', 'nautical-seo-audit'); ?>
                    </button>
                </form>
                <form method="post" onsubmit="return confirm('<?php echo esc_js(__('Reset the entire SEO audit URL log and counters?', 'nautical-seo-audit')); ?>');">
                    <?php wp_nonce_field('nautical_audit_reset_log', 'nautical_audit_reset_nonce'); ?>
                    <button type="submit" name="nautical_audit_reset_log" value="1" class="button button-secondary">
                        <?php echo esc_html__('Reset Log', 'nautical-seo-audit'); ?>
                    </button>
                </form>
            </div>
            <table class="widefat striped">
                <thead>
                    <tr>
                        <th><?php echo esc_html__('Date', 'nautical-seo-audit'); ?></th>
                        <th><?php echo esc_html__('Requested URL', 'nautical-seo-audit'); ?></th>
                        <th><?php echo esc_html__('Final URL', 'nautical-seo-audit'); ?></th>
                        <th><?php echo esc_html__('Status', 'nautical-seo-audit'); ?></th>
                        <th><?php echo esc_html__('IP Address', 'nautical-seo-audit'); ?></th>
                        <th><?php echo esc_html__('Error', 'nautical-seo-audit'); ?></th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (!$rows) : ?>
                        <tr>
                            <td colspan="6"><?php echo esc_html__('No audit URLs have been recorded yet.', 'nautical-seo-audit'); ?></td>
                        </tr>
                    <?php else : ?>
                        <?php foreach ($rows as $row) : ?>
                            <tr>
                                <td><?php echo esc_html($row['created_at']); ?></td>
                                <td>
                                    <a href="<?php echo esc_url($row['requested_url']); ?>" target="_blank" rel="noopener noreferrer">
                                        <?php echo esc_html($row['requested_url']); ?>
                                    </a>
                                </td>
                                <td>
                                    <?php if (!empty($row['final_url'])) : ?>
                                        <a href="<?php echo esc_url($row['final_url']); ?>" target="_blank" rel="noopener noreferrer">
                                            <?php echo esc_html($row['final_url']); ?>
                                        </a>
                                    <?php else : ?>
                                        <?php echo esc_html__('Not reached', 'nautical-seo-audit'); ?>
                                    <?php endif; ?>
                                </td>
                                <td><?php echo esc_html($row['status_code'] ?: ''); ?></td>
                                <td><?php echo esc_html($row['user_ip']); ?></td>
                                <td><?php echo esc_html($row['error_message']); ?></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
        <?php
    }

    public function exportLogCsv(): void
    {
        if (!current_user_can('manage_options')) {
            wp_die(esc_html__('You do not have permission to export this log.', 'nautical-seo-audit'));
        }

        check_admin_referer('nautical_audit_export_log', 'nautical_audit_export_nonce');

        global $wpdb;
        $table = $this->tableName();
        $rows = $wpdb->get_results(
            "SELECT created_at, requested_url, final_url, status_code, user_ip, user_agent, error_message FROM {$table} ORDER BY created_at DESC, id DESC",
            ARRAY_A
        );

        $filename = 'nautical-seo-audit-urls-' . gmdate('Y-m-d-His') . '.csv';

        nocache_headers();
        header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename="' . $filename . '"');

        $output = fopen('php://output', 'w');
        if (!$output) {
            exit;
        }

        fputcsv(
            $output,
            [
                'Date',
                'Requested URL',
                'Final URL',
                'Status Code',
                'IP Address',
                'User Agent',
                'Error',
            ]
        );

        foreach ($rows as $row) {
            fputcsv(
                $output,
                [
                    $row['created_at'],
                    $row['requested_url'],
                    $row['final_url'],
                    $row['status_code'],
                    $row['user_ip'],
                    $row['user_agent'],
                    $row['error_message'],
                ]
            );
        }

        fclose($output);
        exit;
    }

    public function maybeCreateTable(): void
    {
        if (get_option(self::DB_OPTION) === self::DB_VERSION) {
            return;
        }

        $this->createTable();
    }

    private function createTable(): void
    {
        global $wpdb;

        require_once ABSPATH . 'wp-admin/includes/upgrade.php';

        $table = $this->tableName();
        $charsetCollate = $wpdb->get_charset_collate();

        $sql = "CREATE TABLE {$table} (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            visitor_id varchar(64) NOT NULL DEFAULT '',
            requested_url text NOT NULL,
            final_url text NOT NULL,
            status_code int(11) DEFAULT NULL,
            error_message text NOT NULL,
            user_ip varchar(45) NOT NULL DEFAULT '',
            user_agent text NOT NULL,
            created_at datetime NOT NULL,
            PRIMARY KEY  (id),
            KEY visitor_id (visitor_id),
            KEY created_at (created_at)
        ) {$charsetCollate};";

        dbDelta($sql);

        $launchTable = $this->launchTableName();
        $launchSql = "CREATE TABLE {$launchTable} (
            id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
            visitor_id varchar(64) NOT NULL DEFAULT '',
            user_ip varchar(45) NOT NULL DEFAULT '',
            user_agent text NOT NULL,
            created_at datetime NOT NULL,
            PRIMARY KEY  (id),
            KEY visitor_id (visitor_id),
            KEY created_at (created_at)
        ) {$charsetCollate};";

        dbDelta($launchSql);
        update_option(self::DB_OPTION, self::DB_VERSION);
    }

    private function recordAuditUrl(string $requestedUrl, string $finalUrl, ?int $statusCode, string $errorMessage, string $visitorId = ''): void
    {
        global $wpdb;

        if (get_option(self::DB_OPTION) !== self::DB_VERSION) {
            $this->createTable();
        }

        $wpdb->insert(
            $this->tableName(),
            [
                'visitor_id' => $this->sanitizeVisitorId($visitorId),
                'requested_url' => $requestedUrl,
                'final_url' => $finalUrl,
                'status_code' => $statusCode,
                'error_message' => $errorMessage,
                'user_ip' => $this->requestIpAddress(),
                'user_agent' => isset($_SERVER['HTTP_USER_AGENT']) ? sanitize_text_field(wp_unslash($_SERVER['HTTP_USER_AGENT'])) : '',
                'created_at' => current_time('mysql'),
            ],
            ['%s', '%s', '%s', '%d', '%s', '%s', '%s', '%s']
        );
    }

    private function recordPageLaunch(string $visitorId): void
    {
        global $wpdb;

        if (get_option(self::DB_OPTION) !== self::DB_VERSION) {
            $this->createTable();
        }

        $wpdb->insert(
            $this->launchTableName(),
            [
                'visitor_id' => $this->sanitizeVisitorId($visitorId),
                'user_ip' => $this->requestIpAddress(),
                'user_agent' => isset($_SERVER['HTTP_USER_AGENT']) ? sanitize_text_field(wp_unslash($_SERVER['HTTP_USER_AGENT'])) : '',
                'created_at' => current_time('mysql'),
            ],
            ['%s', '%s', '%s', '%s']
        );
    }

    private function auditStats(): array
    {
        global $wpdb;

        if (get_option(self::DB_OPTION) !== self::DB_VERSION) {
            $this->createTable();
        }

        $urlTable = $this->tableName();
        $launchTable = $this->launchTableName();
        $people = (int) $wpdb->get_var("SELECT COUNT(DISTINCT visitor_id) FROM {$launchTable} WHERE visitor_id <> ''");
        $urls = (int) $wpdb->get_var("SELECT COUNT(*) FROM {$urlTable}");
        $trackedUrls = (int) $wpdb->get_var("SELECT COUNT(*) FROM {$urlTable} WHERE visitor_id <> ''");

        return [
            'people' => $people,
            'urls' => $urls,
            'average_urls_per_person' => $people > 0 ? $trackedUrls / $people : 0,
        ];
    }

    private function tableName(): string
    {
        global $wpdb;
        return $wpdb->prefix . 'nautical_audit_urls';
    }

    private function launchTableName(): string
    {
        global $wpdb;
        return $wpdb->prefix . 'nautical_audit_launches';
    }

    private function requestIpAddress(): string
    {
        $ip = isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field(wp_unslash($_SERVER['REMOTE_ADDR'])) : '';
        return substr($ip, 0, 45);
    }

    private function sanitizeVisitorId(string $visitorId): string
    {
        $visitorId = sanitize_text_field($visitorId);
        $visitorId = preg_replace('/[^a-zA-Z0-9_-]/', '', $visitorId);

        return substr((string) $visitorId, 0, 64);
    }

    private function normalizeUrl(string $url): string
    {
        $url = trim($url);
        if ($url === '') {
            return '';
        }

        if (!preg_match('/^https?:\/\//i', $url)) {
            $url = 'https://' . $url;
        }

        $parts = wp_parse_url($url);
        if (!$parts || empty($parts['scheme']) || empty($parts['host'])) {
            return '';
        }

        $scheme = strtolower((string) $parts['scheme']);
        if (!in_array($scheme, ['http', 'https'], true)) {
            return '';
        }

        return esc_url_raw($url);
    }

    private function fetchUrl(string $url, int $timeout)
    {
        $response = wp_remote_get(
            $url,
            [
                'timeout' => $timeout,
                'redirection' => 5,
                'user-agent' => 'Mozilla/5.0 NauticalSEOAudit/1.0',
            ]
        );

        if (is_wp_error($response)) {
            return new WP_Error(
                'nautical_audit_fetch_failed',
                $response->get_error_message(),
                ['status' => 502]
            );
        }

        $statusCode = (int) wp_remote_retrieve_response_code($response);
        if ($statusCode < 200 || $statusCode >= 400) {
            return new WP_Error(
                'nautical_audit_unreachable',
                'The URL returned HTTP ' . $statusCode . '.',
                ['status' => 502]
            );
        }

        return [
            'body' => (string) wp_remote_retrieve_body($response),
            'headers' => wp_remote_retrieve_headers($response),
            'status_code' => $statusCode,
            'final_url' => $this->responseFinalUrl($response, $url),
        ];
    }

    private function fetchStatus(string $url, int $timeout): array
    {
        $response = wp_remote_get(
            $url,
            [
                'timeout' => $timeout,
                'redirection' => 5,
                'user-agent' => 'Mozilla/5.0 NauticalSEOAudit/1.0',
            ]
        );

        if (is_wp_error($response)) {
            return [
                'status_code' => null,
                'final_url' => $url,
                'error' => $response->get_error_message(),
            ];
        }

        return [
            'status_code' => (int) wp_remote_retrieve_response_code($response),
            'final_url' => $this->responseFinalUrl($response, $url),
            'error' => '',
        ];
    }

    private function responseFinalUrl(array $response, string $fallbackUrl): string
    {
        $httpResponse = $response['http_response'] ?? null;
        if ($httpResponse && method_exists($httpResponse, 'get_response_object')) {
            $object = $httpResponse->get_response_object();
            if (!empty($object->url)) {
                return (string) $object->url;
            }
        }

        return $fallbackUrl;
    }

    private function analyzeHtml(string $html, $headers, string $url, int $statusCode): array
    {
        [$dom, $xpath] = $this->loadDom($html);

        $title = trim((string) $this->firstNodeText($xpath, '//title'));
        $h1Tags = $this->nodeTexts($xpath, '//h1');
        $canonicalUrl = $this->firstAttribute(
            $xpath,
            '//link[contains(concat(" ", translate(@rel, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), " "), " canonical ")]',
            'href'
        );
        $metaDescription = $this->firstAttribute(
            $xpath,
            '//meta[translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "description"]',
            'content'
        );
        $description = $metaDescription ?: $this->firstAttribute(
            $xpath,
            '//meta[translate(@property, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "og:description" or translate(@name, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "twitter:description"]',
            'content'
        );

        $noindexSources = $this->noindexSources($xpath, $headers);
        $imagesMissingAlt = $this->imagesMissingAlt($xpath, $url);
        $visibleText = $this->visibleText($dom, $xpath);
        $contact = $this->contactInfo($xpath, $visibleText, $url);

        return [
            'url' => $url,
            'status_code' => $statusCode,
            'checks' => [
                'title' => $title !== '',
                'description' => $description !== '',
                'canonical_url' => $canonicalUrl !== '',
                'h1_tag' => count($h1Tags) > 0,
                'meta_description_tag' => $metaDescription !== '',
            ],
            'noindex' => [
                'is_noindex' => count($noindexSources) > 0,
                'sources' => $noindexSources,
            ],
            'contact' => $contact,
            'images_missing_alt' => $imagesMissingAlt,
            'google_analytics_present' => $this->hasGoogleAnalytics($html),
            'values' => [
                'title' => $title,
                'description' => $description,
                'canonical_url' => $canonicalUrl,
                'h1_tags' => $h1Tags,
                'meta_description' => $metaDescription,
            ],
        ];
    }

    private function loadDom(string $html): array
    {
        $dom = new DOMDocument();
        $previous = libxml_use_internal_errors(true);
        $dom->loadHTML('<?xml encoding="utf-8" ?>' . $html);
        libxml_clear_errors();
        libxml_use_internal_errors($previous);

        return [$dom, new DOMXPath($dom)];
    }

    private function firstNodeText(DOMXPath $xpath, string $query): string
    {
        $nodes = $xpath->query($query);
        if (!$nodes || $nodes->length === 0) {
            return '';
        }

        return preg_replace('/\s+/', ' ', trim((string) $nodes->item(0)->textContent));
    }

    private function nodeTexts(DOMXPath $xpath, string $query): array
    {
        $values = [];
        $nodes = $xpath->query($query);
        if (!$nodes) {
            return $values;
        }

        foreach ($nodes as $node) {
            $text = preg_replace('/\s+/', ' ', trim((string) $node->textContent));
            if ($text !== '') {
                $values[] = $text;
            }
        }

        return $values;
    }

    private function firstAttribute(DOMXPath $xpath, string $query, string $attribute): string
    {
        $nodes = $xpath->query($query);
        if (!$nodes || $nodes->length === 0) {
            return '';
        }

        return trim((string) $nodes->item(0)->getAttribute($attribute));
    }

    private function visibleText(DOMDocument $dom, DOMXPath $xpath): string
    {
        $hiddenNodes = $xpath->query('//script|//style|//noscript|//template|//svg|//head');
        if ($hiddenNodes) {
            foreach ($hiddenNodes as $node) {
                if ($node->parentNode) {
                    $node->parentNode->removeChild($node);
                }
            }
        }

        $breakNodes = $xpath->query('//br');
        if ($breakNodes) {
            foreach ($breakNodes as $node) {
                if ($node->parentNode) {
                    $node->parentNode->insertBefore($dom->createTextNode(' '), $node);
                    if ($node->nextSibling) {
                        $node->parentNode->insertBefore($dom->createTextNode(' '), $node->nextSibling);
                    } else {
                        $node->parentNode->appendChild($dom->createTextNode(' '));
                    }
                }
            }
        }

        $body = $xpath->query('//body')->item(0);
        $text = $body ? $body->textContent : $dom->textContent;

        return preg_replace('/\s+/', ' ', trim((string) $text));
    }

    private function noindexSources(DOMXPath $xpath, $headers): array
    {
        $sources = [];
        $names = ['robots', 'googlebot', 'googlebot-news', 'bingbot', 'slurp', 'duckduckbot', 'baiduspider', 'yandex', 'yandexbot'];
        $nodes = $xpath->query('//meta[@name and @content]');

        if ($nodes) {
            foreach ($nodes as $node) {
                $name = strtolower(trim((string) $node->getAttribute('name')));
                $content = trim((string) $node->getAttribute('content'));
                if (in_array($name, $names, true) && $this->hasNoindexDirective($content)) {
                    $sources[] = [
                        'source' => 'meta name=' . $name,
                        'directive' => $content,
                    ];
                }
            }
        }

        $xRobots = '';
        if (is_object($headers) && method_exists($headers, 'offsetGet')) {
            $xRobots = (string) $headers->offsetGet('x-robots-tag');
        } elseif (is_array($headers) && isset($headers['x-robots-tag'])) {
            $xRobots = (string) $headers['x-robots-tag'];
        }

        if ($xRobots !== '' && $this->hasNoindexDirective($xRobots)) {
            $sources[] = [
                'source' => 'X-Robots-Tag header',
                'directive' => $xRobots,
            ];
        }

        return $sources;
    }

    private function hasNoindexDirective(string $value): bool
    {
        $parts = preg_split('/[\s,;:]+/', strtolower($value), -1, PREG_SPLIT_NO_EMPTY);
        return in_array('noindex', $parts, true) || in_array('none', $parts, true);
    }

    private function imagesMissingAlt(DOMXPath $xpath, string $pageUrl): array
    {
        $items = [];
        $nodes = $xpath->query('//img[not(@alt) or normalize-space(@alt) = ""]');
        if (!$nodes) {
            return $items;
        }

        foreach ($nodes as $node) {
            $src = trim((string) ($node->getAttribute('src') ?: $node->getAttribute('data-src') ?: $node->getAttribute('data-lazy-src')));
            $items[] = [
                'url' => $src !== '' ? $this->absoluteUrl($pageUrl, $src) : '[image source missing]',
                'page_url' => $pageUrl,
            ];
        }

        return $items;
    }

    private function contactInfo(DOMXPath $xpath, string $visibleText, string $url): array
    {
        $phone = '';
        $telNode = $xpath->query('//a[starts-with(translate(@href, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "tel:")]')->item(0);
        if ($telNode) {
            $phone = $this->cleanPhone(substr((string) $telNode->getAttribute('href'), 4));
        }

        if ($phone === '' && preg_match('/(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}/', $visibleText, $match)) {
            $phone = $this->cleanPhone($match[0]);
        }

        $addressParts = [];
        $addressNodes = $xpath->query('//*[translate(@itemprop, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "streetaddress" or translate(@itemprop, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "addresslocality" or translate(@itemprop, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "addressregion" or translate(@itemprop, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "postalcode"]');
        if ($addressNodes) {
            foreach ($addressNodes as $node) {
                $value = trim((string) ($node->getAttribute('content') ?: $node->textContent));
                if ($value !== '') {
                    $addressParts[] = $value;
                }
            }
        }
        $address = trim(implode(' ', $addressParts));

        $addressPatterns = [
            '/\b\d{1,6}\s+[A-Za-z0-9.\'-]+(?:\s+[A-Za-z0-9.\'-]+){0,5}\s+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Court|Ct\.?|Place|Pl\.?|Way|Circle|Cir\.?|Highway|Hwy\.?|Parkway|Pkwy\.?|Turnpike|Tpke\.?|Route|Rte\.?)\b[^\n;]{0,120}?\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b/i',
            '/\b\d{1,6}\s+[A-Za-z0-9.\'-]+(?:\s+[A-Za-z0-9.\'-]+){0,5}\s+(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Court|Ct\.?|Place|Pl\.?|Way|Circle|Cir\.?|Highway|Hwy\.?|Parkway|Pkwy\.?|Turnpike|Tpke\.?|Route|Rte\.?)\b[^\n,;]{0,80}/i',
        ];

        foreach ($addressPatterns as $pattern) {
            if ($address === '' && preg_match($pattern, $visibleText, $match)) {
                $address = trim($match[0], " ,.;");
            }
        }

        $privacyUrl = '';
        $privacyNode = $xpath->query('//a[contains(translate(@href, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "privacy") or contains(translate(normalize-space(.), "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "privacy policy")]')->item(0);
        if ($privacyNode) {
            $privacyUrl = trim((string) $privacyNode->getAttribute('href'));
        }
        $hasPrivacy = $privacyUrl !== '' || stripos($visibleText, 'privacy policy') !== false;

        return [
            'phone' => [
                'exists' => $phone !== '',
                'value' => $phone,
            ],
            'address' => [
                'exists' => $address !== '',
                'value' => $address,
            ],
            'privacy_policy' => [
                'exists' => $hasPrivacy,
                'url' => $privacyUrl !== '' ? $this->absoluteUrl($url, $privacyUrl) : '',
            ],
        ];
    }

    private function cleanPhone(string $value): string
    {
        $digits = preg_replace('/\D/', '', $value);
        if (strlen($digits) === 11 && substr($digits, 0, 1) === '1') {
            $digits = substr($digits, 1);
        }

        if (strlen($digits) === 10) {
            return substr($digits, 0, 3) . '-' . substr($digits, 3, 3) . '-' . substr($digits, 6);
        }

        return trim($value);
    }

    private function hasGoogleAnalytics(string $html): bool
    {
        $patterns = [
            '/google-analytics\.com\/analytics\.js/i',
            '/google-analytics\.com\/ga\.js/i',
            '/googletagmanager\.com\/gtag\/js\?id=(?:G|UA|AW)-[A-Z0-9-]+/i',
            '/googletagmanager\.com\/gtm\.js\?id=GTM-[A-Z0-9-]+/i',
            '/googletagmanager\.com\/ns\.html\?id=GTM-[A-Z0-9-]+/i',
            '/(?<![A-Z0-9_-])G-[A-Z0-9]{6,}(?![A-Z0-9_-])/i',
            '/(?<![A-Z0-9_-])UA-\d+-\d+(?![A-Z0-9_-])/i',
            '/(?<![A-Z0-9_-])GTM-[A-Z0-9-]+(?![A-Z0-9_-])/i',
            '/gtag\(\s*[\'"]config[\'"]\s*,\s*[\'"](?:G|UA|AW)-[A-Z0-9-]+[\'"]/i',
            '/GoogleAnalyticsObject/i',
            '/static\.parastorage\.com\/services\/tag-manager-client\/[^\'"]*siteTags\.bundle\.min\.js/i',
            '/\/services\/tag-manager-client\/[^\'"]*siteTags\.bundle/i',
        ];

        foreach ($patterns as $pattern) {
            if (preg_match($pattern, $html)) {
                return true;
            }
        }

        return false;
    }

    private function checkSsl(string $url, int $timeout): array
    {
        $httpsUrl = $this->urlWithScheme($url, 'https');
        $status = $this->fetchStatus($httpsUrl, $timeout);

        return [
            'checked_url' => $httpsUrl,
            'has_ssl' => $status['status_code'] !== null,
            'status_code' => $status['status_code'],
            'final_url' => $status['final_url'],
            'error' => $status['error'],
        ];
    }

    private function checkSitemap(string $url, int $timeout): array
    {
        $candidates = [
            $this->siteRoot($url, 'https') . 'sitemap.xml',
            $this->siteRoot($url, 'https') . 'sitemap_index.xml',
        ];
        $checked = [];

        foreach ($candidates as $candidate) {
            $status = $this->fetchStatus($candidate, $timeout);
            $checked[] = [
                'url' => $candidate,
                'status_code' => $status['status_code'],
                'final_url' => $status['final_url'],
                'error' => $status['error'],
            ];

            if ($status['status_code'] !== null && $status['status_code'] >= 200 && $status['status_code'] < 400) {
                return [
                    'exists' => true,
                    'url' => $status['final_url'],
                    'checked' => $checked,
                ];
            }
        }

        return [
            'exists' => false,
            'url' => '',
            'checked' => $checked,
        ];
    }

    private function checkLlmsTxt(string $url, int $timeout): array
    {
        $llmsUrl = $this->siteRoot($url, 'https') . 'llms.txt';
        $status = $this->fetchStatus($llmsUrl, $timeout);
        $exists = $status['status_code'] !== null && $status['status_code'] >= 200 && $status['status_code'] < 400;

        return [
            'exists' => $exists,
            'url' => $exists ? $status['final_url'] : '',
            'checked_url' => $llmsUrl,
            'status_code' => $status['status_code'],
            'final_url' => $status['final_url'],
            'error' => $status['error'],
        ];
    }

    private function siteRoot(string $url, string $scheme): string
    {
        $parts = wp_parse_url($url);
        if (!$parts || empty($parts['host'])) {
            return '';
        }

        $port = !empty($parts['port']) ? ':' . $parts['port'] : '';
        return $scheme . '://' . $parts['host'] . $port . '/';
    }

    private function urlWithScheme(string $url, string $scheme): string
    {
        $parts = wp_parse_url($url);
        if (!$parts || empty($parts['host'])) {
            return $url;
        }

        $port = !empty($parts['port']) ? ':' . $parts['port'] : '';
        $path = $parts['path'] ?? '/';
        $query = !empty($parts['query']) ? '?' . $parts['query'] : '';
        return $scheme . '://' . $parts['host'] . $port . $path . $query;
    }

    private function absoluteUrl(string $baseUrl, string $value): string
    {
        if ($value === '' || preg_match('/^https?:\/\//i', $value)) {
            return $value;
        }

        if (substr($value, 0, 2) === '//') {
            $scheme = wp_parse_url($baseUrl, PHP_URL_SCHEME) ?: 'https';
            return $scheme . ':' . $value;
        }

        $base = wp_parse_url($baseUrl);
        if (!$base || empty($base['scheme']) || empty($base['host'])) {
            return $value;
        }

        if (substr($value, 0, 1) === '/') {
            return $base['scheme'] . '://' . $base['host'] . $value;
        }

        $path = $base['path'] ?? '/';
        $lastSlash = strrpos($path, '/');
        $dir = $lastSlash === false ? '' : rtrim(substr($path, 0, $lastSlash + 1), '/');
        return $base['scheme'] . '://' . $base['host'] . $dir . '/' . $value;
    }
}

register_activation_hook(__FILE__, ['Nautical_SEO_Audit_Plugin', 'activate']);
new Nautical_SEO_Audit_Plugin();
