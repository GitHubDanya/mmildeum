<script lang="ts">
    import '#lib/lunar/shared.css';
    import type { SelectedSite } from '#lib/lunar/types';
    import { buildFallbackSeries, fetchSiteTelemetry } from '#lib/lunar/telemetry';
    import LunarGlobe from '#lib/lunar/LunarGlobe.svelte';
    import SitesListView from '#lib/lunar/SitesListView.svelte';
    import SiteDetailView from '#lib/lunar/SiteDetailView.svelte';

    let globe: LunarGlobe;
    let selectedSites: SelectedSite[] = [];
    let activeSiteId: number | null = null;
    let nextSiteId = 1;
    let viewportWidth = 1440;

    $: activeSite = selectedSites.find((s) => s.id === activeSiteId) ?? null;

    // Solid covered width on the right (total menu width minus the 8vw transparent fade)
    $: menuWidthPx = activeSite
        ? Math.min(viewportWidth * 0.65, 1000)
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
            peakSunlight: null,
            peakValue: null,
            sunlight24h: fallback.sunlight24h,
            earthVisibility24h: fallback.earthVisibility24h,
            sunlightAngle24h: fallback.sunlightAngle24h,
            isEstimatedSeries: true,
            loadingScore: true,
            scoreError: false
        };

        selectedSites = [...selectedSites, newSite];
        loadTelemetry(newSite);
    }

    function handleSelectSite(site: SelectedSite) {
        activeSiteId = site.id;
        globe?.flyToSite(site);
    }

    function handleSelectSiteById(siteId: number) {
        const found = selectedSites.find((s) => s.id === siteId);
        if (found) handleSelectSite(found);
    }

    function handleRemoveSite(id: number) {
        if (activeSiteId === id) activeSiteId = null;
        selectedSites = selectedSites.filter((s) => s.id !== id);
    }

    function handleClearAll() {
        selectedSites = [];
        activeSiteId = null;
        nextSiteId = 1;
    }
</script>

<svelte:window bind:innerWidth={viewportWidth} />

<LunarGlobe
        bind:this={globe}
        sites={selectedSites}
        {activeSiteId}
        {rightInsetPx}
        onAddSite={handleAddSite}
        onSelectSite={handleSelectSiteById}
/>

<div class="menu" class:expanded={Boolean(activeSite)}>
    <h1 style="margin-top: 6vh;">Lunar Landing Site Navigator</h1>

    {#if activeSite}
        <SiteDetailView
                site={activeSite}
                totalSitesCount={selectedSites.length}
                onBack={() => (activeSiteId = null)}
                onFocus={(site) => globe?.flyToSite(site)}
                onRemove={handleRemoveSite}
                onRetry={loadTelemetry}
        />
    {:else if selectedSites.length > 0}
        <SitesListView
                sites={selectedSites}
                onSelect={handleSelectSite}
                onRemove={handleRemoveSite}
                onClearAll={handleClearAll}
        />
    {:else}
        <p class="hint">Click anywhere on the lunar surface to add candidate landing sites.</p>
    {/if}
</div>

<div class="top-bar">
    <button class="btn btn-white">Our Scoring Algorithm</button>
</div>

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
        max-width: 1000px;
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
        z-index: 10;
    }
</style>