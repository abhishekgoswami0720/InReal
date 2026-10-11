let allInternships = [];
let isLoadingData = false;

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function sanitizeUrl(url) {
    if (!url) return '#';
    try {
        const parsed = new URL(url, window.location.origin);
        if (['http:', 'https:'].includes(parsed.protocol)) {
            return url;
        }
    } catch (e) { }
    return '#';
}

document.addEventListener("DOMContentLoaded", () => {
    loadData();
    checkScraperStatus();
    pollAlerts();  // Start polling for CAPTCHA/popup alerts

    // Setup event listeners
    document.getElementById("search-input").addEventListener("input", renderListings);
    document.getElementById("source-filter").addEventListener("change", renderListings);

    // Group filter listeners
    setupFilters("location-filters", "location");
    setupFilters("stipend-filters", "stipend");
    setupFilters("org-filters", "org");
    setupFilters("role-filters", "role");

    // Region tab bar (Everything / India / Global / Remote)
    setupRegionTabs();

    // Scraper Config Modal controls
    const configModal = document.getElementById("scrape-config-modal");
    document.getElementById("trigger-scrape-btn").addEventListener("click", () => configModal.classList.remove("hidden"));
    document.getElementById("close-config-btn").addEventListener("click", () => configModal.classList.add("hidden"));

    document.getElementById("scrape-config-form").addEventListener("submit", (e) => {
        e.preventDefault();
        configModal.classList.add("hidden");

        // Build config payload from checked boxes
        const getCheckedValues = (name) => Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(cb => cb.value);

        const config = {
            regions: getCheckedValues("regions"),
            topics: getCheckedValues("topics"),
            sources: getCheckedValues("sources")
        };

        triggerScraper(config);
    });

    document.getElementById("action-dismiss-btn").addEventListener("click", async () => {
        document.getElementById("action-banner").classList.remove("show");
        try {
            await fetch("/api/alerts/dismiss", { method: "POST" });
        } catch (e) { }
    });

    // Modal controls
    const modal = document.getElementById("instructions-modal");
    document.getElementById("info-btn").addEventListener("click", () => modal.classList.remove("hidden"));
    document.getElementById("close-modal-btn").addEventListener("click", () => modal.classList.add("hidden"));
    modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.add("hidden");
    });

    // Clear data controls
    document.getElementById("clear-data-btn").addEventListener("click", async () => {
        if (!confirm("Are you sure you want to permanently delete all scraped internships and logs? This cannot be undone.")) return;

        try {
            const res = await fetch("/api/clear", { method: "POST" });
            const data = await res.json();

            if (data.status === "success") {
                allInternships = [];
                renderListings();
                updateRegionCounts();
                document.getElementById("total-count").innerText = "0";

                // Fetch fresh logs to clear the panel
                const content = document.getElementById("logs-content");
                if (content) content.innerHTML = "<div>No logs yet. Click 'Run Scraper Now' to start!</div>";

                alert("Database successfully cleared!");
            } else {
                alert("Failed to clear data: " + data.message);
            }
        } catch (e) {
            console.error("Error clearing data:", e);
            alert("An error occurred while clearing data.");
        }
    });

    // Logs panel controls
    document.getElementById("toggle-logs-btn").addEventListener("click", () => {
        const panel = document.getElementById("logs-panel");
        panel.classList.toggle("hidden");
        if (!panel.classList.contains("hidden")) {
            fetchLogs();
        }
    });

    document.getElementById("close-logs-btn").addEventListener("click", () => {
        document.getElementById("logs-panel").classList.add("hidden");
    });

    // Poll status and logs
    setInterval(() => {
        checkScraperStatus();
        fetchLogs();
    }, 4000);
});

function setupFilters(containerId, filterType) {
    const container = document.getElementById(containerId);
    const buttons = container.querySelectorAll('.filter-btn');

    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            buttons.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            const val = e.target.dataset.val;
            window[`active${filterType.charAt(0).toUpperCase() + filterType.slice(1)}Filter`] = val;

            // Sync region tab bar when sidebar location changes
            if (filterType === 'location') syncRegionTabs(val);

            renderListings();
        });
    });

    // Default
    window[`active${filterType.charAt(0).toUpperCase() + filterType.slice(1)}Filter`] = "all";
}

function setupRegionTabs() {
    const tabs = document.querySelectorAll('.region-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const region = tab.dataset.region;
            // Update active tab
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            // Sync location filter
            window.activeLocationFilter = region;
            // Sync sidebar buttons
            const sidebarBtns = document.querySelectorAll('#location-filters .filter-btn');
            sidebarBtns.forEach(b => {
                b.classList.toggle('active', b.dataset.val === region);
            });
            renderListings();
        });
    });
}

function syncRegionTabs(val) {
    const tabs = document.querySelectorAll('.region-tab');
    tabs.forEach(t => t.classList.toggle('active', t.dataset.region === val));
}

function updateRegionCounts() {
    const counts = { all: allInternships.length, India: 0, International: 0, Remote: 0 };
    allInternships.forEach(i => {
        if (i.location_type === 'India') counts.India++;
        else if (i.location_type === 'Remote') counts.Remote++;
        else counts.International++;
    });
    const fmt = n => n > 0 ? n.toLocaleString() : '—';
    document.getElementById('tab-count-all').textContent = fmt(counts.all);
    document.getElementById('tab-count-india').textContent = fmt(counts.India);
    document.getElementById('tab-count-global').textContent = fmt(counts.International);
    document.getElementById('tab-count-remote').textContent = fmt(counts.Remote);
}


async function loadData() {
    if (isLoadingData) return;
    isLoadingData = true;

    // Only show loading spinner on first load if container is empty
    if (document.getElementById("listings-container").children.length === 0) {
        document.getElementById("loading-spinner").classList.remove("hidden");
    }

    try {
        const res = await fetch("/api/internships");
        const data = await res.json();
        allInternships = data;

        // ----------------------------------------------------------
        // Deduplicate by 'id' field (100% safe — IDs are hash-based)
        // ----------------------------------------------------------
        const seenIds = new Set();
        allInternships = allInternships.filter(item => {
            if (!item.id || seenIds.has(item.id)) return false;
            seenIds.add(item.id);
            return true;
        });

        // Fix location_type based on actual URL / location text
        // (some scrapers tag by query region, not actual listing location)
        normalizeLocationTypes(allInternships);

        document.getElementById("total-count").innerText = allInternships.length;

        // Populate sources without causing dropdown to collapse
        const sources = [...new Set(allInternships.map(i => i.source_platform))].filter(Boolean).sort();
        const sourceSelect = document.getElementById("source-filter");

        const currentOptions = Array.from(sourceSelect.options).map(o => o.value).filter(v => v !== 'all').sort();
        if (JSON.stringify(sources) !== JSON.stringify(currentOptions)) {
            const currentSelection = sourceSelect.value;
            sourceSelect.innerHTML = '<option value="all">All Sources</option>';
            sources.forEach(s => {
                const isSelected = (s === currentSelection) ? 'selected' : '';
                sourceSelect.innerHTML += `<option value="${escapeHtml(s)}" ${isSelected}>${escapeHtml(s)}</option>`;
            });
        }

        renderListings();
        updateRegionCounts();
    } catch (err) {
        console.error("Failed to load data", err);
    } finally {
        document.getElementById("loading-spinner").classList.add("hidden");
        isLoadingData = false;
    }
}

function renderListings() {
    const container = document.getElementById("listings-container");

    const searchQ = document.getElementById("search-input").value.toLowerCase();
    const sourceF = document.getElementById("source-filter").value;
    const locF = window.activeLocationFilter || "all";
    const stipF = window.activeStipendFilter || "all";
    const orgF = window.activeOrgFilter || "all";
    const roleF = window.activeRoleFilter || "all";

    let filtered = allInternships.filter(item => {
        // Search
        if (searchQ) {
            const str = `${item.role_title} ${item.company_name} ${item.required_skills}`.toLowerCase();
            if (!str.includes(searchQ)) return false;
        }

        // Source
        if (sourceF !== "all" && item.source_platform !== sourceF) return false;

        // Location
        if (locF !== "all" && item.location_type !== locF) return false;

        // Stipend
        const stipNum = parseFloat(item.stipend_numeric) || 0;
        if (stipF === "paid" && stipNum <= 0 && (!item.stipend || !item.stipend.toLowerCase().includes("month"))) return false;
        if (stipF === "10k" && stipNum < 10000) return false;
        if (stipF === "20k" && stipNum < 20000) return false;
        if (stipF === "50k" && stipNum < 50000) return false;
        if (stipF === "unpaid" && stipNum > 0) return false;

        // Org Type
        if (orgF !== "all" && item.org_type !== orgF) return false;

        // Role Type
        if (roleF !== "all" && item.role_type !== roleF) return false;

        return true;
    });

    // Sort by Match Score Descending, then Date
    filtered.sort((a, b) => {
        const scoreA = a.match_score || 0;
        const scoreB = b.match_score || 0;
        if (scoreB !== scoreA) {
            return scoreB - scoreA;
        }
        return new Date(b.date_scraped) - new Date(a.date_scraped);
    });

    document.getElementById("visible-count").innerText = filtered.length;

    const existingCards = Array.from(container.children).filter(c => c.tagName === 'DIV' && c.hasAttribute('data-id'));
    const existingIds = new Set(existingCards.map(c => c.dataset.id));
    const validIds = new Set(filtered.map(i => i.id));

    if (filtered.length === 0) {
        // Keep it empty, show message
        container.innerHTML = `<p class="empty-msg" style="color:var(--text-muted); grid-column: 1/-1; text-align:center; padding: 40px;">No internships found matching your criteria.</p>`;
        return;
    } else {
        // Remove empty state message if it exists
        const emptyMsg = container.querySelector(".empty-msg");
        if (emptyMsg) emptyMsg.remove();
    }

    // 1. Remove cards that are no longer valid (filtered out)
    existingCards.forEach(card => {
        if (!validIds.has(card.dataset.id)) {
            card.remove();
            existingIds.delete(card.dataset.id);
        }
    });

    // 2. Add new cards that aren't in the DOM yet
    const fragment = document.createDocumentFragment();
    let newCardsCount = 0;

    filtered.forEach((item, index) => {
        if (!existingIds.has(item.id)) {
            const isNewHtml = item.is_new ? `<div class="new-badge">New</div>` : '';
            const stipendDisp = escapeHtml(item.stipend ? item.stipend : "Stipend not disclosed");  // unpaid listings are never saved
            const durDisp = escapeHtml(item.duration ? item.duration : "N/A");
            const locDisp = escapeHtml(item.location ? item.location : item.location_type);
            const skillsDisp = escapeHtml(item.required_skills ? item.required_skills : "Not specified");
            const scoreBadge = item.match_score ? `<div class="match-score-badge ${item.match_score >= 80 ? 'high-score' : (item.match_score >= 60 ? 'med-score' : 'low-score')}">${item.match_score}% Match</div>` : '';
            const orgBadge = item.org_type ? `<span class="tag tag-org"><i class="ph ph-bank"></i> ${escapeHtml(item.org_type)}</span>` : '';
            const roleBadge = item.role_type ? `<span class="tag tag-role"><i class="ph ph-flask"></i> ${escapeHtml(item.role_type)}</span>` : '';
            const durBadge = item.duration ? `<span class="tag tag-dur"><i class="ph ph-clock"></i> ${durDisp}</span>` : '';
            // Genuine check (genuine.py): listings that failed it are never saved; softer warnings arrive in trust_flags
            const flags = String(item.trust_flags || "").split(";").map(f => f.trim()).filter(Boolean);
            const trustHtml = flags.length
                ? `<div class="trust trust-warn"><i class="ph ph-warning"></i><span><strong>Check before applying:</strong> ${flags.map(escapeHtml).join(" &bull; ")}</span></div>`
                : `<div class="trust trust-ok"><i class="ph ph-shield-check"></i><span>No warning signs found</span></div>`;

            const safeCompany = escapeHtml(item.company_name);
            const safeRole = escapeHtml(item.role_title);
            const safeSource = escapeHtml(item.source_platform);
            const safeDate = escapeHtml(item.date_scraped);

            const card = document.createElement("div");
            card.dataset.id = item.id;

            // Only animate the newly added cards that fit in the first page view to prevent lag 
            if (newCardsCount < 30) {
                card.className = "card animate-in";
                card.style.animationDelay = `${(newCardsCount * 0.04).toFixed(2)}s`;
            } else {
                card.className = "card";
            }

            card.innerHTML = `
                ${isNewHtml}
                ${scoreBadge}
                <div class="card-header" style="margin-top: ${item.match_score ? '20px' : '0'};">
                    <div class="company-name"><i class="ph ph-buildings"></i> ${safeCompany}</div>
                </div>
                <h3 class="role-title">${safeRole}</h3>
                
                <div class="tags">
                    <span class="tag tag-loc"><i class="ph ph-map-pin"></i> ${locDisp}</span>
                    <span class="tag tag-stipend"><i class="ph ph-money"></i> ${stipendDisp}</span>
                    ${durBadge}
                    ${orgBadge}
                    ${roleBadge}
                </div>

                ${trustHtml}
                
                <div class="skills-list">
                    <strong>Skills:</strong> ${skillsDisp}
                </div>
                
                <div class="card-footer">
                    <span class="source-info">Via ${safeSource} &bull; ${safeDate}</span>
                    <a href="${sanitizeUrl(item.apply_link)}" target="_blank" rel="noopener noreferrer" class="apply-btn">View Details</a>
                </div>
            `;
            fragment.appendChild(card);
            newCardsCount++;
        }
    });

    // Append all new cards at once
    container.appendChild(fragment);

    // Completely eliminate UI flickering: DO NOT physically detach/reattach DOM nodes to sort them.
    // Since the container is a CSS Grid, we can flawlessly sort them visually using the flex/grid 'order' property.
    const idToNode = new Map();
    Array.from(container.children).forEach(c => {
        if (c.tagName === 'DIV' && c.hasAttribute('data-id')) {
            idToNode.set(c.dataset.id, c);
        }
    });

    filtered.forEach((item, index) => {
        const cardNode = idToNode.get(String(item.id));
        if (cardNode) {
            cardNode.style.order = index;
        }
    });
}

/**
 * Re-classify location_type based on actual URL domain and location text.
 * This overrides query-based tagging (e.g. a Virginia Tech page found via
 * an "India Edu" query must not be labelled location_type="India").
 */
function normalizeLocationTypes(items) {
    const INDIA_DOMAINS = ['.ac.in', '.edu.in', '.co.in', '.res.in', '.gov.in', '.nic.in', '.org.in', '.net.in'];
    const INDIA_CITIES = ['bangalore', 'bengaluru', 'mumbai', 'delhi', 'hyderabad', 'pune', 'chennai', 'kolkata',
        'ahmedabad', 'noida', 'gurgaon', 'gurugram', 'india'];
    const REMOTE_TERMS = ['remote', 'work from home', 'wfh', 'anywhere', 'distributed'];
    // Foreign TLDs that should NEVER be India
    const FOREIGN_DOMAINS = ['.edu', '.gov', '.ac.uk', '.co.uk', '.de', '.fr', '.nl', '.se',
        '.fi', '.dk', '.no', '.ch', '.at', '.be', '.sg', '.jp', '.kr',
        '.cn', '.au', '.nz', '.ca', '.ae', '.sa', '.il', '.br'];

    items.forEach(item => {
        const url = (item.apply_link || '').toLowerCase();
        const loc = (item.location || '').toLowerCase();
        const comp = (item.company_name || '').toLowerCase();

        // REMOTE check first
        if (REMOTE_TERMS.some(t => loc.includes(t) || comp.includes(t))) {
            item.location_type = 'Remote';
            return;
        }

        // INDIA check: URL domain or location text
        const isIndiaUrl = INDIA_DOMAINS.some(d => url.includes(d));
        const isIndiaLoc = INDIA_CITIES.some(c => loc.includes(c));
        // Explicit foreign domain → definitely NOT India
        const isForeignUrl = FOREIGN_DOMAINS.some(d => {
            // match domain suffix precisely: .edu must not match .edu.in
            const idx = url.indexOf(d);
            if (idx === -1) return false;
            // Check the char immediately after is not a letter (i.e., .edu not followed by .in)
            const after = url[idx + d.length];
            return !after || !/[a-z]/.test(after);
        });

        if (isForeignUrl && !isIndiaUrl) {
            item.location_type = 'International';
        } else if (isIndiaUrl || isIndiaLoc) {
            item.location_type = 'India';
        }
        // otherwise keep stored value
    });
}


async function triggerScraper(config) {
    setScrapingState(true);
    try {
        const res = await fetch("/api/scrape", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config)
        });
        const data = await res.json();
        setTimeout(checkScraperStatus, 2000);
    } catch (err) {
        console.error("Error triggering scrape", err);
        setScrapingState(false);
    }
}

async function checkScraperStatus() {
    try {
        const res = await fetch("/api/scrape/status");
        const data = await res.json();
        if (data.status === "running") {
            setScrapingState(true);
            // LIVE UPDATES: Fetch data as it's scraped
            loadData();
        } else {
            setScrapingState(false);
        }
    } catch (err) { }
}

let wasRunning = false;
function setScrapingState(isRunning) {
    const btn = document.getElementById("trigger-scrape-btn");
    const txt = document.getElementById("scrape-btn-text");
    const icon = btn.querySelector("i");

    if (isRunning) {
        btn.disabled = true;
        txt.innerText = "Scraping in progress...";
        icon.classList.add("ph-spinner", "ph-spin");
        icon.classList.remove("ph-arrows-clockwise");
        wasRunning = true;
    } else {
        btn.disabled = false;
        txt.innerText = "Run Scraper Now";
        icon.classList.remove("ph-spinner", "ph-spin");
        icon.classList.add("ph-arrows-clockwise");

        // If it just finished, reload data one final time
        if (wasRunning) {
            wasRunning = false;
            loadData();
        }
    }
}

async function fetchLogs() {
    const panel = document.getElementById("logs-panel");
    if (panel && panel.classList.contains("hidden")) return;

    try {
        const res = await fetch("/api/logs");
        const data = await res.json();
        const content = document.getElementById("logs-content");

        const isScrolledToBottom = content.scrollHeight - content.clientHeight <= content.scrollTop + 10;

        content.innerHTML = data.logs.map(l => `<div>${l}</div>`).join("");

        if (isScrolledToBottom) {
            content.scrollTop = content.scrollHeight;
        }
    } catch (e) {
        console.error("Failed to fetch logs", e);
    }
}

async function pollAlerts() {
    try {
        const res = await fetch("/api/alerts");
        const data = await res.json();
        const banner = document.getElementById("action-banner");

        if (data.alert) {
            document.getElementById("action-title").innerText = `Action Required [${data.alert.source}]`;
            document.getElementById("action-message").innerText = data.alert.message;
            if (!banner.classList.contains("show")) {
                banner.classList.add("show");
            }
        } else {
            banner.classList.remove("show");
        }
    } catch (err) {
        // ignore fetch errs
    } finally {
        setTimeout(pollAlerts, 2000);
    }
}

