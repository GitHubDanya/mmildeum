<script lang="ts">
    import type { HistoricalLandingSite, SelectedSite } from './types';
    import { getScoreClass } from './telemetry';
    import HistoricalSiteSearch from './HistoricalSiteSearch.svelte';

    export let sites: SelectedSite[] = [];
    export let onSelect: (site: SelectedSite) => void;
    export let onCompare: (siteIds: [number, number]) => void;
    export let onRemove: (id: number) => void;
    export let onClearAll: () => void;
    export let onSelectHistoricalSite: ((site: HistoricalLandingSite) => void) | undefined =
        undefined;

    let compareMode = false;
    let pickedIds: number[] = [];

    $: if (sites.length < 2 && compareMode) {
        compareMode = false;
        pickedIds = [];
    }

    $: pickedIds = pickedIds.filter((id) => sites.some((s) => s.id === id));

    function toggleCompareMode() {
        compareMode = !compareMode;
        pickedIds = [];
    }

    function handleCardClick(site: SelectedSite) {
        if (!compareMode) {
            onSelect(site);
            return;
        }

        if (pickedIds.includes(site.id)) {
            pickedIds = pickedIds.filter((id) => id !== site.id);
        } else if (pickedIds.length === 0) {
            pickedIds = [site.id];
        } else {
            const pair: [number, number] = [pickedIds[0], site.id];
            compareMode = false;
            pickedIds = [];
            onCompare(pair);
        }
    }
</script>

<div class="sites-panel">
    {#if onSelectHistoricalSite}
        <HistoricalSiteSearch
                existingSites={sites}
                compact={true}
                {onSelectHistoricalSite}
        />
    {/if}

    <div class="sites-header">
        <span>
            {#if compareMode}
                Select 2 sites ({pickedIds.length}/2)
            {:else}
                Selected Sites ({sites.length})
            {/if}
        </span>

        <div class="header-actions">
            {#if sites.length >= 2}
                <button
                        class="btn {compareMode ? 'btn-active' : 'btn-outline'}"
                        on:click={toggleCompareMode}
                >
                    {compareMode ? 'Cancel' : 'Compare'}
                </button>
            {/if}
            <button class="btn btn-white" on:click={onClearAll}>Clear All</button>
        </div>
    </div>

    <div class="sites-list">
        {#each sites as site (site.id)}
            {@const pickIndex = pickedIds.indexOf(site.id)}
            <div class="site-card" class:picked={pickIndex !== -1}>
                <button
                        class="site-info"
                        on:click={() => handleCardClick(site)}
                        title={compareMode
                        ? `Select ${site.name} for comparison`
                        : `View details for ${site.name}`}
                >
                    <div class="site-title-line">
                        {#if compareMode}
                            <span class="pick-indicator" class:checked={pickIndex !== -1}>
                                {pickIndex === 0 ? 'A' : pickIndex === 1 ? 'B' : ''}
                            </span>
                        {/if}
                        <strong>{site.name}</strong>
                    </div>
                    {#if site.historicalSubtitle}
                        <span class="historical-tag">{site.historicalSubtitle}</span>
                    {/if}
                    <span>Lat: {site.lat}° | Lon: {site.lon}° | Alt: {site.alt}m</span>
                    {#if site.terrainType}
                        <span class="terrain-tag">{site.terrainType}</span>
                    {:else if site.groundAngle !== null || site.lolaRoughnessDeg !== null}
                        <span class="terrain-tag">
                            {#if site.groundAngle !== null}Slope: {site.groundAngle.toFixed(1)}°{/if}
                            {#if site.groundAngle !== null && site.lolaRoughnessDeg !== null} · {/if}
                            {#if site.lolaRoughnessDeg !== null}Roughness: {site.lolaRoughnessDeg.toFixed(2)}°{/if}
                        </span>
                    {/if}
                </button>

                <div class="site-actions">
                    {#if site.loadingScore}
                        <span class="score-badge loading">Loading...</span>
                    {:else if site.scoreError}
                        <span class="score-badge error">Error</span>
                    {:else if typeof site.score === 'number'}
                        <span
                                class="score-badge {getScoreClass(site.score)}"
                                title="Landing Suitability Score"
                        >
                            {site.score.toFixed(1)}
                        </span>
                    {:else}
                        <span class="score-badge neutral">Ready</span>
                    {/if}

                    <button
                            class="remove-btn"
                            on:click={() => onRemove(site.id)}
                            aria-label="Remove {site.name}"
                            title="Remove site"
                    >
                        ✕
                    </button>
                </div>
            </div>
        {/each}
    </div>
</div>

<style>
    .sites-panel {
        pointer-events: auto;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        max-height: 78vh;
    }

    .sites-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.9rem;
        padding-bottom: 0.55rem;
        border-bottom: 1px solid rgba(234, 234, 234, 0.15);
    }

    .header-actions {
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    .btn-outline {
        background-color: transparent;
        color: #eaeaea;
        border: 1px solid rgba(234, 234, 234, 0.35);
    }

    .btn-active {
        background-color: #facc15;
        color: #070707;
    }

    .sites-list {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        overflow-y: auto;
        padding-right: 0.25rem;
    }

    .site-card {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        background-color: rgba(234, 234, 234, 0.08);
        border: 1px solid rgba(234, 234, 234, 0.12);
        border-radius: 10px;
        padding: 0.6rem 0.75rem;
        transition: background-color 0.15s ease, border-color 0.15s ease;
    }

    .site-card:hover {
        background-color: rgba(234, 234, 234, 0.14);
    }

    .site-card.picked {
        border-color: #facc15;
        background-color: rgba(250, 204, 21, 0.1);
    }

    .site-info {
        background: none;
        border: none;
        color: inherit;
        font-family: inherit;
        text-align: left;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
        padding: 0;
        flex: 1;
    }

    .site-title-line {
        display: flex;
        align-items: center;
        gap: 0.45rem;
    }

    .pick-indicator {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid rgba(234, 234, 234, 0.4);
        font-size: 0.68rem;
        font-weight: 700;
        color: #070707;
    }

    .pick-indicator.checked {
        background-color: #facc15;
        border-color: #facc15;
    }

    .site-info strong {
        font-size: 0.85rem;
        color: #fff;
    }

    .site-info span {
        font-size: 0.75rem;
        opacity: 0.8;
    }

    .historical-tag {
        font-size: 0.7rem !important;
        color: #93c5fd;
        opacity: 0.9 !important;
    }

    .terrain-tag {
        font-size: 0.7rem !important;
        opacity: 0.65 !important;
    }

    .site-actions {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-shrink: 0;
    }

    .score-badge.neutral {
        background-color: rgba(234, 234, 234, 0.12);
        color: rgba(234, 234, 234, 0.85);
        font-weight: 500;
    }
</style>