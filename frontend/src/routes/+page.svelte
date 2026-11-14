<script lang="ts">
    import '#lib/lunar/shared.css';
    import type { SelectedSite } from '#lib/lunar/types';
    import {
        HOURS_LABELS,
        buildFallbackSeries,
        fetchSiteTelemetry,
        findRecommendedLandingWindows,
        getTimelineBounds
    } from '#lib/lunar/telemetry';
    import LunarGlobe from '#lib/lunar/LunarGlobe.svelte';
    import SitesListView from '#lib/lunar/SitesListView.svelte';
    import SiteDetailView from '#lib/lunar/SiteDetailView.svelte';
    import SiteCompareView from '#lib/lunar/SiteCompareView.svelte';
    import MissionTimelineSlider from '#lib/lunar/MissionTimelineSlider.svelte';

    let globe: LunarGlobe;
    let isViewingEarth = false;
    let selectedSites: SelectedSite[] = [];
    let activeSiteId: number | null = null;
    let comparePairIds: [number, number] | null = null;
    let nextSiteId = 1;
    let viewportWidth = 1440;

    let selectedTimeMs = Date.UTC(2026, 9, 1, 0, 0);
    let hasUserScrubbedTime = false;

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

    $: timelineBounds = getTimelineBounds(selectedSites);
    $: if (selectedTimeMs < timelineBounds.startMs || selectedTimeMs > timelineBounds.endMs) {
        selectedTimeMs = timelineBounds.startMs;
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

    async function loadTelemetry(site: SelectedSite) {
        selectedSites = selectedSites.map((s) =>
            s.id === site.id ? { ...s, loadingScore: true, scoreError: false } : s
        );

        try {
            const updates = await fetchSiteTelemetry(site.rawLat, site.rawLon);
            selectedSites = selectedSites.map((s) =>
                s.id === site.id
                    ? { ...s, ...updates, loadingScore: false, scoreError: false }
                    : s
            );

            // Auto-position the timeline on the first recommended landing window if user hasn't scrubbed yet
            if (!hasUserScrubbedTime) {
                const updatedSite = selectedSites.find((s) => s.id === site.id);
                if (updatedSite) {
                    const bounds = getTimelineBounds(selectedSites);
                    const best = findRecommendedLandingWindows(
                        [updatedSite],
                        bounds.startMs,
                        bounds.endMs
                    );
                    if (best.length > 0) {
                        selectedTimeMs = best[0].peakMs;
                    }
                }
            }
        } catch (error) {
            console.error(`Failed to fetch data for site #${site.id}:`, error);
            selectedSites = selectedSites.map((s) =>
                s.id === site.id ? { ...s, loadingScore: false, scoreError: true } : s
            );
        }
    }

    function handleAddSite({ lat, lon, alt }: { lat: number; lon: number; alt: number }) {
        const id = nextSiteId++;
        const fallback = buildFallbackSeries(lat, lon, null);

        const newSite: SelectedSite = {
            id,
            name: `Site #${id}`,
            lat: lat.toFixed(3),
            lon: lon.toFixed(3),
            alt: alt.toFixed(1),
            rawLat: lat,
            rawLon: lon,
            rawAlt: alt,
            score: null,
            terrainType: null,
            terrainClassId: null,
            daytimeAvgSunAngle: null,
            terrainElevationM: null,
            groundAngle: null,
            lolaRoughnessDeg: null,
            visibilityWindows: [],
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
            scoreError: false
        };

        selectedSites = [...selectedSites, newSite];

        if (activeSiteId !== null) {
            activeSiteId = id;
        }

        loadTelemetry(newSite);
    }

    function handleSelectSite(site: SelectedSite) {
        comparePairIds = null;
        activeSiteId = site.id;
        globe?.flyToSite(site);
    }

    function handleSelectSiteById(siteId: number) {
        const found = selectedSites.find((s) => s.id === siteId);
        if (!found) return;

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
        if (activeSiteId === id) activeSiteId = null;
        if (comparePairIds && comparePairIds.includes(id)) {
            comparePairIds = null;
        }
        selectedSites = selectedSites.filter((s) => s.id !== id);
    }

    function handleClearAll() {
        selectedSites = [];
        activeSiteId = null;
        comparePairIds = null;
        hasUserScrubbedTime = false;
        nextSiteId = 1;
    }

    function handleTimelineChange(nextMs: number) {
        hasUserScrubbedTime = true;
        selectedTimeMs = nextMs;
    }
</script>

<svelte:window bind:innerWidth={viewportWidth} />

<LunarGlobe
        bind:this={globe}
        bind:isViewingEarth
        sites={selectedSites}
        {highlightedSiteIds}
        {rightInsetPx}
        {selectedTimeMs}
        onAddSite={handleAddSite}
        onSelectSite={handleSelectSiteById}
/>

<div class="menu" class:expanded={isExpanded}>
    <h1 style="margin-top: 6vh;">Lunar Landing Site Navigator</h1>

    {#if compareSites}
        <SiteCompareView
                siteA={compareSites[0]}
                siteB={compareSites[1]}
                allSites={selectedSites}
                {selectedTimeMs}
                timelineStartMs={timelineBounds.startMs}
                onChangePair={(pair) => (comparePairIds = pair)}
                onBack={() => (comparePairIds = null)}
                onFocus={(site) => globe?.flyToSite(site)}
                onRetry={loadTelemetry}
        />
    {:else if activeSite}
        <SiteDetailView
                site={activeSite}
                totalSitesCount={selectedSites.length}
                {selectedTimeMs}
                timelineStartMs={timelineBounds.startMs}
                onBack={() => (activeSiteId = null)}
                onFocus={(site) => globe?.flyToSite(site)}
                onCompareWith={handleCompareFromDetail}
                onRemove={handleRemoveSite}
                onRetry={loadTelemetry}
        />
    {:else if selectedSites.length > 0}
        <SitesListView
                sites={selectedSites}
                onSelect={handleSelectSite}
                onCompare={handleStartCompare}
                onRemove={handleRemoveSite}
                onClearAll={handleClearAll}
        />
    {:else}
        <p class="hint">Click anywhere on the lunar surface to add candidate landing sites.</p>
    {/if}
</div>

<div class="top-bar">
    <button class="btn btn-white">Our Scoring Algorithm</button>
    {#if isViewingEarth}
        <button class="btn btn-moon" on:click={() => globe?.flyToMoon()}>
            ← Back to Moon
        </button>
    {:else}
        <button class="btn btn-earth" on:click={() => globe?.flyToEarth()}>
            View Earth
        </button>
    {/if}
</div>

<MissionTimelineSlider
        startMs={timelineBounds.startMs}
        endMs={timelineBounds.endMs}
        {selectedTimeMs}
        targetSites={timelineTargetSites}
        {rightInsetPx}
        onChangeTime={handleTimelineChange}
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
        transition: width 0.25s ease, padding-left 0.25s ease;
    }

    .menu.expanded {
        width: 65vw;
        max-width: 1040px;
        padding-left: 14vw;
    }

    .hint {
        text-align: center;
        opacity: 0.7;
        font-size: 0.9rem;
    }

    .top-bar {
        position: absolute;
        top: 20px;
        left: 20px;
        display: flex;
        flex-direction: row;
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
</style>