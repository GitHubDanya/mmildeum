<script lang="ts">
    import type { HistoricalLandingSite, SelectedSite } from './types';
    import {
        HISTORICAL_LANDING_SITES,
        HISTORICAL_LANDING_SITES_SOURCE,
        searchHistoricalLandingSites
    } from './historicalSites';

    export let existingSites: SelectedSite[] = [];
    export let showPreloadButton = false;
    export let compact = false;
    export let onSelectHistoricalSite: (site: HistoricalLandingSite) => void;
    export let onPreloadDefaults: (() => void) | undefined = undefined;

    let query = '';
    let isOpen = false;
    let containerEl: HTMLDivElement;

    $: filteredSites = searchHistoricalLandingSites(query, HISTORICAL_LANDING_SITES);$: addedHistoricalIds = new Set(
        existingSites.map((s) => s.historicalId).filter((id): id is string => Boolean(id))
    );

    function handlePick(site: HistoricalLandingSite) {
        onSelectHistoricalSite(site);
        query = '';
        isOpen = false;
    }

    function handleWindowClick(e: MouseEvent) {
        if (containerEl && !containerEl.contains(e.target as Node)) {
            isOpen = false;
        }
    }

    function formatCoord(lat: number, lon: number): string {
        const latDir = lat >= 0 ? 'N' : 'S';
        const lonDir = lon >= 0 ? 'E' : 'W';
        return `${Math.abs(lat).toFixed(2)}°${latDir}, ${Math.abs(lon).toFixed(2)}°${lonDir}`;
    }
</script>

<svelte:window on:click={handleWindowClick} />

<div class="historical-controls" class:compact bind:this={containerEl}>
    <div class="search-box">
        <span class="search-icon" aria-hidden="true">⌕</span>
        <input
                class="search-input"
                type="text"
                bind:value={query}
                on:focus={() => (isOpen = true)}
                on:input={() => (isOpen = true)}
                placeholder="Search 28 past missions (Apollo, Chang'e, Luna...)"
                aria-label="Search historical lunar landing sites"
        />
        {#if query}
            <button
                    class="clear-search-btn"
                    type="button"
                    on:click={() => {
                    query = '';
                    isOpen = true;
                }}
                    aria-label="Clear search"
            >
                ✕
            </button>
        {/if}
    </div>

    {#if isOpen}
        <div class="dropdown-panel" role="listbox" aria-label="Historical landing sites">
            <div class="dropdown-header">
                <span>{filteredSites.length} of {HISTORICAL_LANDING_SITES.length} missions</span>
                <span class="source-tag" title={HISTORICAL_LANDING_SITES_SOURCE}>
                    NASA NSSDCA / LROC
                </span>
            </div>

            {#if filteredSites.length === 0}
                <div class="empty-results">No historical landing sites match "{query}".</div>
            {:else}
                <div class="results-scroll">
                    {#each filteredSites as site (site.id)}
                        {@const isAdded = addedHistoricalIds.has(site.id)}
                        <button
                                type="button"
                                class="result-item"
                                class:added={isAdded}
                                on:click={() => handlePick(site)}
                        >
                            <div class="result-main">
                                <div class="result-title-row">
                                    <span class="result-name">{site.name}</span>
                                    <span class="result-year">{site.year}</span>
                                    {#if site.isDefaultPreset}
                                        <span class="preset-badge">Featured</span>
                                    {/if}
                                </div>
                                <div class="result-sub">
                                    {site.region} · {site.agency} · {formatCoord(site.lat, site.lon)}
                                </div>
                            </div>
                            <span class="result-action">
                                {isAdded ? 'Focus' : '+ Add'}
                            </span>
                        </button>
                    {/each}
                </div>
            {/if}
        </div>
    {/if}

    {#if showPreloadButton && onPreloadDefaults}
        <button type="button" class="preload-btn" on:click={onPreloadDefaults}>
            ★ Load 5 Iconic Landing Sites
        </button>
    {/if}
</div>

<style>
    .historical-controls {
        position: relative;
        display: flex;
        flex-direction: column;
        gap: 0.55rem;
        width: 100%;
        pointer-events: auto;
        z-index: 20;
    }

    .historical-controls.compact {
        margin-bottom: 0.15rem;
    }

    .search-box {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        background-color: rgba(234, 234, 234, 0.08);
        border: 1px solid rgba(234, 234, 234, 0.2);
        border-radius: 9px;
        padding: 0.45rem 0.65rem;
        transition: border-color 0.15s ease, background-color 0.15s ease;
    }

    .search-box:focus-within {
        border-color: #60a5fa;
        background-color: rgba(20, 20, 24, 0.95);
    }

    .search-icon {
        font-size: 0.95rem;
        opacity: 0.65;
        user-select: none;
    }

    .search-input {
        flex: 1;
        min-width: 0;
        background: transparent;
        border: none;
        color: #ffffff;
        font-family: inherit;
        font-size: 0.78rem;
        outline: none;
    }

    .search-input::placeholder {
        color: rgba(234, 234, 234, 0.5);
    }

    .clear-search-btn {
        background: transparent;
        border: none;
        color: rgba(234, 234, 234, 0.6);
        cursor: pointer;
        font-size: 0.75rem;
        padding: 0.1rem 0.25rem;
    }

    .clear-search-btn:hover {
        color: #ffffff;
    }

    .dropdown-panel {
        position: absolute;
        top: calc(100% + 4px);
        left: 0;
        right: 0;
        background-color: rgba(12, 12, 14, 0.97);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(234, 234, 234, 0.22);
        border-radius: 10px;
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.8);
        overflow: hidden;
        z-index: 30;
    }

    .dropdown-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.4rem 0.65rem;
        font-size: 0.67rem;
        opacity: 0.7;
        border-bottom: 1px solid rgba(234, 234, 234, 0.12);
        background-color: rgba(255, 255, 255, 0.03);
    }

    .source-tag {
        color: #93c5fd;
    }

    .results-scroll {
        max-height: 230px;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
    }

    .result-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.6rem;
        width: 100%;
        text-align: left;
        background: transparent;
        border: none;
        border-bottom: 1px solid rgba(234, 234, 234, 0.08);
        color: #eaeaea;
        padding: 0.5rem 0.65rem;
        font-family: inherit;
        cursor: pointer;
        transition: background-color 0.14s ease;
    }

    .result-item:last-child {
        border-bottom: none;
    }

    .result-item:hover {
        background-color: rgba(96, 165, 250, 0.15);
    }

    .result-main {
        display: flex;
        flex-direction: column;
        gap: 0.16rem;
        min-width: 0;
    }

    .result-title-row {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        flex-wrap: wrap;
    }

    .result-name {
        font-size: 0.8rem;
        font-weight: 600;
        color: #ffffff;
    }

    .result-year {
        font-size: 0.68rem;
        opacity: 0.65;
    }

    .preset-badge {
        font-size: 0.62rem;
        padding: 0.05rem 0.35rem;
        border-radius: 999px;
        background-color: rgba(250, 204, 21, 0.16);
        color: #fde047;
        border: 1px solid rgba(250, 204, 21, 0.35);
    }

    .result-sub {
        font-size: 0.69rem;
        opacity: 0.72;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .result-action {
        flex-shrink: 0;
        font-size: 0.7rem;
        font-weight: 600;
        padding: 0.18rem 0.5rem;
        border-radius: 6px;
        background-color: rgba(74, 222, 128, 0.16);
        color: #86efac;
        border: 1px solid rgba(74, 222, 128, 0.35);
    }

    .result-item.added .result-action {
        background-color: rgba(96, 165, 250, 0.16);
        color: #93c5fd;
        border-color: rgba(96, 165, 250, 0.35);
    }

    .empty-results {
        padding: 0.85rem;
        text-align: center;
        font-size: 0.75rem;
        opacity: 0.65;
    }

    .preload-btn {
        width: 100%;
        padding: 0.52rem 0.8rem;
        border-radius: 9px;
        background-color: rgba(96, 165, 250, 0.16);
        color: #bfdbfe;
        border: 1px solid rgba(96, 165, 250, 0.42);
        font-family: inherit;
        font-size: 0.78rem;
        font-weight: 600;
        cursor: pointer;
        transition: background-color 0.15s ease, border-color 0.15s ease;
    }

    .preload-btn:hover {
        background-color: rgba(96, 165, 250, 0.28);
        border-color: #93c5fd;
        color: #ffffff;
    }
</style>