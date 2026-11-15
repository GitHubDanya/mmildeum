<script lang="ts">
    import scoringPdf from '../../../docs/Lunar_Landing_Site_Scoring_EN.pdf';
    import { onDestroy } from 'svelte';
    import '#lib/lunar/shared.css';
    import type { HistoricalLandingSite, SelectedSite } from '#lib/lunar/types';
    import {
        DEFAULT_TIMELINE_START_MS,
        HOURS_LABELS,
        MAX_MISSION_PAD_MS,
        applyFallbackRescore,
        buildFallbackSeries,
        fetchSiteTelemetry,
        fetchTimelineBlockTelemetry,
        findRecommendedLandingWindows,
        getMonthBounds
    } from '#lib/lunar/telemetry';
    import {
        DEFAULT_PRESET_LANDING_SITES,
        HISTORICAL_LANDING_SITES
    } from '#lib/lunar/historicalSites';
    import LunarGlobe from '#lib/lunar/LunarGlobe.svelte';
    import SitesListView from '#lib/lunar/SitesListView.svelte';
    import SiteDetailView from '#lib/lunar/SiteDetailView.svelte';
    import SiteCompareView from '#lib/lunar/SiteCompareView.svelte';
    import MissionTimelineSlider from '#lib/lunar/MissionTimelineSlider.svelte';
    import HistoricalSiteSearch from '#lib/lunar/HistoricalSiteSearch.svelte';

    let globe: LunarGlobe;
    let isViewingEarth = false;
    let isMenuOpen = true;
    let isTimelineOpen = true;
    let selectedSites: SelectedSite[] = [];
    let activeSiteId: number | null = null;
    let comparePairIds: [number, number] | null = null;
    let nextSiteId = 1;
    let viewportWidth = 1440;

    let activeTimelineYear = 2026;
    let activeTimelineMonth = 9; // 0-indexed (9 = October)
    let selectedTimeMs = DEFAULT_TIMELINE_START_MS;
    let missionDurationHours = 72;
    let hasUserScrubbedTime = false;

    const telemetryCache = new Map<string, Partial<SelectedSite>>();
    const activeAbortControllers = new Map<number, AbortController>();
    const inFlightKeys = new Map<number, string>();
    let refreshDebounceTimer: ReturnType<typeof setTimeout> | undefined = undefined;
    let lastScheduledWindowKey = '';

    $: loadingCount = selectedSites.filter((s) => s.loadingScore || s.updatingTelemetry).length;
    $: isLoadingData = loadingCount > 0;

    $: activeSite = selectedSites.find((s) => s.id === activeSiteId) ?? null;

    $: compareSites = (() => {
        if (!comparePairIds) return null;
        const a = selectedSites.find((s) => s.id === comparePairIds![0]);
        const b = selectedSites.find((s) => s.id === comparePairIds![1]);
        return a && b ? ([a, b] as [SelectedSite, SelectedSite]) : null;
    })();

    $: timelineTargetSites = compareSites
        ? [compareSites[0], compareSites[1]]
        : activeSite
            ? [activeSite]
            : selectedSites;

    $: timelineBounds = getMonthBounds(activeTimelineYear, activeTimelineMonth);

    $: if (selectedTimeMs < timelineBounds.startMs) {
        selectedTimeMs = timelineBounds.startMs;
    } else if (selectedTimeMs > timelineBounds.endMs) {
        selectedTimeMs = timelineBounds.endMs;
    }

    $: currentWindowKey = `${selectedTimeMs}|${missionDurationHours}`;
    $: if (currentWindowKey !== lastScheduledWindowKey) {
        lastScheduledWindowKey = currentWindowKey;
        handleTimeOrDurationUpdate(selectedTimeMs, missionDurationHours);
    }

    $: isExpanded = Boolean(activeSite || compareSites);

    $: highlightedSiteIds = compareSites
        ? [compareSites[0].id, compareSites[1].id]
        : activeSite
            ? [activeSite.id]
            : [];

    $: menuWidthPx = isExpanded
        ? Math.min(viewportWidth * 0.65, 1040)
        : viewportWidth * 0.4;
    $: rightInsetPx = Math.max(0, menuWidthPx - viewportWidth * 0.08);
    $: effectiveRightInsetPx = isMenuOpen ? rightInsetPx : 0;

    function buildTelemetryCacheKey(
        lat: number,
        lon: number,
        startMs: number,
        durationHours: number
    ): string {
        return `${lat.toFixed(5)}_${lon.toFixed(5)}_${startMs}_${durationHours}`;
    }

    function createSiteRecord(params: {
        lat: number;
        lon: number;
        alt?: number;
        customName?: string;
        historicalId?: string;
        historicalSubtitle?: string;
    }): SelectedSite {
        const id = nextSiteId++;
        const alt = params.alt ?? 0;
        const fallback = buildFallbackSeries(params.lat, params.lon, null);

        return {
            id,
            historicalId: params.historicalId,
            historicalSubtitle: params.historicalSubtitle,
            name: params.customName ?? `Site #${id}`,
            lat: params.lat.toFixed(3),
            lon: params.lon.toFixed(3),
            alt: alt.toFixed(1),
            rawLat: params.lat,
            rawLon: params.lon,
            rawAlt: alt,
            score: null,
            rescoreResult: null,
            scoringMetrics: null,
            scoringBlock: null,
            terrainType: null,
            terrainClassId: null,
            daytimeAvgSunAngle: null,
            terrainElevationM: null,
            groundAngle: null,
            lolaRoughnessDeg: null,
            slopeSuitability: 0.5,
            visibilityWindows: [],
            sunlightWindows: [],
            timelineVisibilityWindows: [],
            timelineSunlightWindows: [],
            hasTimelineBlockData: false,
            hasRealSunlightWindows: false,
            visibilityCoveragePct: null,
            visibilitySeries: fallback.earthVisibility24h,
            visibilityLabels: HOURS_LABELS,
            hasRealVisibility: false,
            peakSunlight: null,
            peakValue: null,
            sunlight24h: fallback.sunlight24h,
            sunlightAngle24h: fallback.sunlightAngle24h,
            isEstimatedSunSeries: true,
            loadingScore: true,
            updatingTelemetry: false,
            scoreError: false,
            missionSunlight: null,
            loadingMissionSunlight: false,
            missionSunlightError: null
        };
    }

    function autoPickBestTimelineWindow(
        sitesToEvaluate: SelectedSite[],
        bounds = timelineBounds
    ) {
        if (sitesToEvaluate.length === 0) return;
        const best = findRecommendedLandingWindows(
            sitesToEvaluate,
            bounds.startMs,
            bounds.endMs,
            missionDurationHours
        );
        if (best.length > 0) {
            selectedTimeMs = best[0].peakMs;
        }
    }

    function handleTimeOrDurationUpdate(startMs: number, durationHours: number) {
        if (selectedSites.length === 0) return;

        selectedSites = selectedSites.map((site) => {
            if (site.loadingScore) return site;
            return applyFallbackRescore(site, startMs, durationHours);
        });

        if (refreshDebounceTimer !== undefined) {
            clearTimeout(refreshDebounceTimer);
        }

        refreshDebounceTimer = setTimeout(() => {
            for (const site of selectedSites) {
                if (!site.hasTimelineBlockData) {
                    initializeSiteFullTimeline(site);
                } else {
                    refreshSiteMissionWindow(site, startMs, durationHours, false);
                }
            }
        }, 350);
    }

    async function initializeSiteFullTimeline(
        site: SelectedSite,
        bounds = timelineBounds
    ) {
        const prevController = activeAbortControllers.get(site.id);
        if (prevController) prevController.abort();

        const controller = new AbortController();
        activeAbortControllers.set(site.id, controller);
        inFlightKeys.set(site.id, 'FULL_TIMELINE_BLOCK');

        selectedSites = selectedSites.map((s) =>
            s.id === site.id ? { ...s, loadingScore: true, scoreError: false } : s
        );

        try {
            const blockStartMs = bounds.startMs;
            const blockEndMs = bounds.endMs + MAX_MISSION_PAD_MS;

            const blockUpdates = await fetchTimelineBlockTelemetry(
                site.rawLat,
                site.rawLon,
                blockStartMs,
                blockEndMs,
                60,
                controller.signal,
                bounds.endMs
            );

            selectedSites = selectedSites.map((s) => {
                if (s.id !== site.id) return s;
                const merged: SelectedSite = {
                    ...s,
                    ...blockUpdates,
                    loadingScore: false,
                    updatingTelemetry: false,
                    scoreError: false
                };
                return applyFallbackRescore(merged, selectedTimeMs, missionDurationHours);
            });

            if (activeAbortControllers.get(site.id) === controller) {
                activeAbortControllers.delete(site.id);
            }
            if (inFlightKeys.get(site.id) === 'FULL_TIMELINE_BLOCK') {
                inFlightKeys.delete(site.id);
            }

            if (!hasUserScrubbedTime) {
                const targetList = compareSites
                    ? [compareSites[0], compareSites[1]]
                    : activeSite
                        ? [activeSite]
                        : selectedSites;
                autoPickBestTimelineWindow(targetList, bounds);
            }

            const refreshed = selectedSites.find((s) => s.id === site.id);
            if (refreshed) {
                await refreshSiteMissionWindow(
                    refreshed,
                    selectedTimeMs,
                    missionDurationHours,
                    false
                );
            }
        } catch (error: any) {
            if (error?.name === 'AbortError') return;
            console.error(`Failed to load full timeline block for site #${site.id}:`, error);
            selectedSites = selectedSites.map((s) =>
                s.id === site.id
                    ? { ...s, loadingScore: false, updatingTelemetry: false, scoreError: true }
                    : s
            );
        } finally {
            if (activeAbortControllers.get(site.id) === controller) {
                activeAbortControllers.delete(site.id);
            }
            if (inFlightKeys.get(site.id) === 'FULL_TIMELINE_BLOCK') {
                inFlightKeys.delete(site.id);
            }
        }
    }

    async function refreshSiteMissionWindow(
        site: SelectedSite,
        startMs: number,
        durationHours: number,
        isBlockingLoad = false
    ) {
        if (inFlightKeys.get(site.id) === 'FULL_TIMELINE_BLOCK') return;

        const cacheKey = buildTelemetryCacheKey(site.rawLat, site.rawLon, startMs, durationHours);

        if (telemetryCache.has(cacheKey)) {
            const cached = telemetryCache.get(cacheKey)!;
            selectedSites = selectedSites.map((s) =>
                s.id === site.id
                    ? {
                        ...s,
                        ...cached,
                        loadingScore: false,
                        updatingTelemetry: false,
                        scoreError: false
                    }
                    : s
            );
            return;
        }

        if (inFlightKeys.get(site.id) === cacheKey) {
            return;
        }

        const prevController = activeAbortControllers.get(site.id);
        if (prevController) prevController.abort();

        const controller = new AbortController();
        activeAbortControllers.set(site.id, controller);
        inFlightKeys.set(site.id, cacheKey);

        selectedSites = selectedSites.map((s) =>
            s.id === site.id
                ? {
                    ...s,
                    loadingScore: isBlockingLoad,
                    updatingTelemetry: !isBlockingLoad,
                    scoreError: isBlockingLoad ? false : s.scoreError
                }
                : s
        );

        try {
            const endMs = startMs + Math.max(1, durationHours) * 3600 * 1000;
            const updates = await fetchSiteTelemetry(
                site.rawLat,
                site.rawLon,
                startMs,
                endMs,
                60,
                controller.signal
            );

            telemetryCache.set(cacheKey, updates);

            selectedSites = selectedSites.map((s) =>
                s.id === site.id
                    ? {
                        ...s,
                        ...updates,
                        loadingScore: false,
                        updatingTelemetry: false,
                        scoreError: false
                    }
                    : s
            );
        } catch (error: any) {
            if (error?.name === 'AbortError') return;
            console.error(`Failed to refresh mission window for site #${site.id}:`, error);

            selectedSites = selectedSites.map((s) => {
                if (s.id !== site.id) return s;
                const rescored = applyFallbackRescore(s, startMs, durationHours);
                return {
                    ...rescored,
                    loadingScore: false,
                    updatingTelemetry: false,
                    scoreError: isBlockingLoad
                };
            });
        } finally {
            if (activeAbortControllers.get(site.id) === controller) {
                activeAbortControllers.delete(site.id);
            }
            if (inFlightKeys.get(site.id) === cacheKey) {
                inFlightKeys.delete(site.id);
            }
        }
    }

    function handleAddSite({ lat, lon, alt }: { lat: number; lon: number; alt: number }) {
        const newSite = createSiteRecord({ lat, lon, alt });
        selectedSites = [...selectedSites, newSite];

        if (activeSiteId !== null) {
            activeSiteId = newSite.id;
        }

        initializeSiteFullTimeline(newSite, timelineBounds);
    }

    function handleSelectHistoricalSite(histSite: HistoricalLandingSite) {
        isMenuOpen = true;

        const existing = selectedSites.find((s) => s.historicalId === histSite.id);
        if (existing) {
            handleSelectSite(existing);
            return;
        }

        const newSite = createSiteRecord({
            lat: histSite.lat,
            lon: histSite.lon,
            alt: histSite.alt ?? 0,
            customName: histSite.name,
            historicalId: histSite.id,
            historicalSubtitle: `${histSite.region} (${histSite.year})`
        });

        selectedSites = [...selectedSites, newSite];

        if (activeSiteId !== null) {
            activeSiteId = newSite.id;
        }

        globe?.flyToSite(newSite);
        initializeSiteFullTimeline(newSite, timelineBounds);
    }

    function handlePreloadDefaultSites() {
        if (selectedSites.length > 0) return;

        const created = DEFAULT_PRESET_LANDING_SITES.map((preset) =>
            createSiteRecord({
                lat: preset.lat,
                lon: preset.lon,
                alt: preset.alt ?? 0,
                customName: preset.name,
                historicalId: preset.id,
                historicalSubtitle: `${preset.region} (${preset.year})`
            })
        );

        selectedSites = created;

        for (const site of created) {
            initializeSiteFullTimeline(site, timelineBounds);
        }
    }

    function handleMonthChange(year: number, monthIndex: number) {
        if (year === activeTimelineYear && monthIndex === activeTimelineMonth) return;

        if (refreshDebounceTimer !== undefined) {
            clearTimeout(refreshDebounceTimer);
        }

        activeTimelineYear = year;
        activeTimelineMonth = monthIndex;
        hasUserScrubbedTime = false;

        const nextBounds = getMonthBounds(year, monthIndex);
        selectedTimeMs = nextBounds.startMs;

        if (selectedSites.length > 0) {
            selectedSites = selectedSites.map((s) => ({
                ...s,
                hasTimelineBlockData: false,
                loadingScore: true,
                scoreError: false
            }));
            for (const site of selectedSites) {
                initializeSiteFullTimeline(site, nextBounds);
            }
        }
    }

    function handleSelectSite(site: SelectedSite) {
        isMenuOpen = true;
        comparePairIds = null;
        activeSiteId = site.id;
        globe?.flyToSite(site);
    }

    function handleSelectSiteById(siteId: number) {
        const found = selectedSites.find((s) => s.id === siteId);
        if (!found) return;

        isMenuOpen = true;

        if (comparePairIds && comparePairIds.includes(siteId)) {
            globe?.flyToSite(found);
            return;
        }

        handleSelectSite(found);
    }

    function handleStartCompare(pair: [number, number]) {
        activeSiteId = null;
        comparePairIds = pair;
    }

    function handleCompareFromDetail(site: SelectedSite) {
        const other = selectedSites.find((s) => s.id !== site.id);
        if (!other) return;
        activeSiteId = null;
        comparePairIds = [site.id, other.id];
    }

    function handleRemoveSite(id: number) {
        const controller = activeAbortControllers.get(id);
        if (controller) {
            controller.abort();
            activeAbortControllers.delete(id);
        }
        inFlightKeys.delete(id);

        if (activeSiteId === id) activeSiteId = null;
        if (comparePairIds && comparePairIds.includes(id)) {
            comparePairIds = null;
        }
        selectedSites = selectedSites.filter((s) => s.id !== id);
    }

    function handleClearAll() {
        for (const controller of activeAbortControllers.values()) {
            controller.abort();
        }
        activeAbortControllers.clear();
        inFlightKeys.clear();

        selectedSites = [];
        activeSiteId = null;
        comparePairIds = null;
        hasUserScrubbedTime = false;
        nextSiteId = 1;
    }

    function handleTimelineChange(nextMs: number) {
        hasUserScrubbedTime = true;
        selectedTimeMs = Math.max(timelineBounds.startMs, Math.min(timelineBounds.endMs, nextMs));
    }

    function handleDurationChange(nextHours: number) {
        missionDurationHours = nextHours;

        if (!hasUserScrubbedTime && timelineTargetSites.length > 0) {
            autoPickBestTimelineWindow(timelineTargetSites);
        }
    }

    function handleManualAutoPickBest() {
        hasUserScrubbedTime = false;
        autoPickBestTimelineWindow(timelineTargetSites);
    }

    onDestroy(() => {
        if (refreshDebounceTimer !== undefined) {
            clearTimeout(refreshDebounceTimer);
        }
        for (const controller of activeAbortControllers.values()) {
            controller.abort();
        }
        activeAbortControllers.clear();
        inFlightKeys.clear();
    });
</script>

<svelte:window bind:innerWidth={viewportWidth} />

<LunarGlobe
        bind:this={globe}
        bind:isViewingEarth
        sites={selectedSites}
        {highlightedSiteIds}
        rightInsetPx={effectiveRightInsetPx}
        {selectedTimeMs}
        historicalSites={HISTORICAL_LANDING_SITES}
        onAddSite={handleAddSite}
        onSelectSite={handleSelectSiteById}
        onSelectHistoricalSite={handleSelectHistoricalSite}
/>

<button
        class="btn menu-toggle-btn"
        on:click={() => (isMenuOpen = !isMenuOpen)}
        aria-expanded={isMenuOpen}
        aria-label={isMenuOpen ? 'Collapse side panel' : 'Open side panel'}
        title={isMenuOpen ? 'Hide side panel' : 'Show side panel'}
>
    {#if isMenuOpen}
        Hide Panel ▸
    {:else}
        ◂ {selectedSites.length > 0 ? `Sites (${selectedSites.length})` : 'Open Panel'}
    {/if}
</button>

<div
        class="menu"
        class:expanded={isExpanded}
        class:collapsed={!isMenuOpen}
        aria-hidden={!isMenuOpen}
>
    <h1 style="margin-top: 6vh;">Lunar Landing Site Navigator</h1>

    {#if compareSites}
        <SiteCompareView
                siteA={compareSites[0]}
                siteB={compareSites[1]}
                allSites={selectedSites}
                {selectedTimeMs}
                {missionDurationHours}
                timelineStartMs={timelineBounds.startMs}
                onChangePair={(pair) => (comparePairIds = pair)}
                onBack={() => (comparePairIds = null)}
                onFocus={(site) => globe?.flyToSite(site)}
                onRetry={(site) => initializeSiteFullTimeline(site, timelineBounds)}
        />
    {:else if activeSite}
        <SiteDetailView
                site={activeSite}
                totalSitesCount={selectedSites.length}
                {selectedTimeMs}
                {missionDurationHours}
                timelineStartMs={timelineBounds.startMs}
                onBack={() => (activeSiteId = null)}
                onFocus={(site) => globe?.flyToSite(site)}
                onCompareWith={handleCompareFromDetail}
                onRemove={handleRemoveSite}
                onRetry={(site) => initializeSiteFullTimeline(site, timelineBounds)}
        />
    {:else if selectedSites.length > 0}
        <SitesListView
                sites={selectedSites}
                onSelect={handleSelectSite}
                onCompare={handleStartCompare}
                onRemove={handleRemoveSite}
                onClearAll={handleClearAll}
                onSelectHistoricalSite={handleSelectHistoricalSite}
        />
    {:else}
        <div class="empty-state-box">
            <p class="hint">
                Click anywhere on the lunar surface, click a soft reference marker, or search past missions below.
            </p>
            <HistoricalSiteSearch
                    existingSites={selectedSites}
                    showPreloadButton={true}
                    onSelectHistoricalSite={handleSelectHistoricalSite}
                    onPreloadDefaults={handlePreloadDefaultSites}
            />
        </div>
    {/if}
</div>

<div class="top-bar">
    <a
            href={scoringPdf}
            target="_blank"
            rel="noopener noreferrer"
            class="btn btn-white doc-link">
        Our Scoring Algorithm
    </a>    {#if isViewingEarth}
        <button class="btn btn-moon" on:click={() => globe?.flyToMoon()}>
            ← Back to Moon
        </button>
    {:else}
        <button class="btn btn-earth" on:click={() => globe?.flyToEarth()}>
            View Earth
        </button>
    {/if}

    {#if isLoadingData}
        <div class="global-loading-badge" role="status" aria-live="polite">
            <span class="top-spinner" aria-hidden="true"></span>
            <span>
                {loadingCount === 1
                    ? 'Fetching lunar telemetry...'
                    : `Fetching telemetry (${loadingCount} sites)...`}
            </span>
        </div>
    {/if}
</div>

<MissionTimelineSlider
        bind:isOpen={isTimelineOpen}
        startMs={timelineBounds.startMs}
        endMs={timelineBounds.endMs}
        {selectedTimeMs}
        {missionDurationHours}
        targetSites={timelineTargetSites}
        rightInsetPx={effectiveRightInsetPx}
        isCompact={isExpanded && isMenuOpen}
        {isLoadingData}
        onChangeTime={handleTimelineChange}
        onChangeDuration={handleDurationChange}
        onChangeMonth={handleMonthChange}
        onAutoPickBest={handleManualAutoPickBest}
/>

<style>
    @font-face {
        font-family: "Rubik";
        src: url("/fonts/Rubik.ttf") format("truetype");
        font-weight: 400;
        font-style: normal;
        font-display: swap;
    }

    :global(body, html) {
        margin: 0 !important;
        overflow: hidden;
        color: #eaeaea;
        background-color: #000;
        font-family: "Rubik", sans-serif;
    }

    h1 {
        text-align: center;
        margin-bottom: 1.25rem;
    }

    .menu-toggle-btn {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 20;
        background-color: rgba(14, 14, 18, 0.88);
        backdrop-filter: blur(8px);
        color: #eaeaea;
        border: 1px solid rgba(234, 234, 234, 0.28);
        padding: 0.35rem 0.75rem;
        font-family: inherit;
        transition: background-color 0.15s ease, border-color 0.15s ease, opacity 0.15s ease;
    }

    .menu-toggle-btn:hover {
        background-color: rgba(34, 34, 42, 0.95);
        border-color: rgba(234, 234, 234, 0.55);
        opacity: 1;
    }

    .menu {
        position: absolute;
        box-sizing: border-box;
        height: 100%;
        right: 0;
        top: 0;
        width: 40vw;
        padding-left: 12vw;
        padding-right: 2rem;
        display: flex;
        flex-direction: column;
        background: linear-gradient(to right, rgba(7, 7, 7, 0) 0%, #070707 8vw);
        pointer-events: none;
        z-index: 5;
        transition:
                width 0.25s ease,
                padding-left 0.25s ease,
                transform 0.25s ease,
                opacity 0.2s ease;
    }

    .menu.expanded {
        width: 65vw;
        max-width: 1040px;
        padding-left: 14vw;
    }

    .menu.collapsed {
        transform: translateX(100%);
        opacity: 0;
        pointer-events: none !important;
    }

    .menu.collapsed :global(*) {
        pointer-events: none !important;
    }

    .empty-state-box {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        pointer-events: auto;
    }

    .hint {
        text-align: center;
        opacity: 0.75;
        font-size: 0.86rem;
        line-height: 1.4;
        margin: 0;
    }

    .top-bar {
        position: absolute;
        top: 20px;
        left: 20px;
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 0.5rem;
        z-index: 10;
    }

    .btn-earth {
        background-color: rgba(37, 99, 235, 0.25);
        color: #93c5fd;
        border: 1px solid rgba(96, 165, 250, 0.45);
    }

    .btn-earth:hover {
        background-color: rgba(37, 99, 235, 0.4);
    }

    .btn-moon {
        background-color: rgba(234, 234, 234, 0.18);
        color: #ffffff;
        border: 1px solid rgba(234, 234, 234, 0.45);
    }

    .btn-moon:hover {
        background-color: rgba(234, 234, 234, 0.3);
    }

    .global-loading-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.32rem 0.7rem;
        border-radius: 999px;
        background-color: rgba(7, 7, 7, 0.85);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(96, 165, 250, 0.4);
        color: #93c5fd;
        font-size: 0.75rem;
        font-weight: 500;
    }

    .top-spinner {
        width: 12px;
        height: 12px;
        border: 2px solid rgba(147, 197, 253, 0.28);
        border-top-color: #93c5fd;
        border-radius: 50%;
        animation: top-spin 0.75s linear infinite;
    }

    .doc-link {
        text-decoration: none;
        display: inline-flex;
        align-items: center;
    }

    @keyframes top-spin {
        to {
            transform: rotate(360deg);
        }
    }
</style>