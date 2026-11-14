<script lang="ts">
    import type { SelectedSite } from './types';
    import { getScoreClass } from './telemetry';

    export let sites: SelectedSite[] = [];
    export let onSelect: (site: SelectedSite) => void;
    export let onRemove: (id: number) => void;
    export let onClearAll: () => void;
</script>

<div class="sites-panel">
    <div class="sites-header">
        <span>Selected Sites ({sites.length})</span>
        <button class="btn btn-white" on:click={onClearAll}>Clear All</button>
    </div>

    <div class="sites-list">
        {#each sites as site (site.id)}
            <div class="site-card">
                <button
                        class="site-info"
                        on:click={() => onSelect(site)}
                        title="View details for {site.name}"
                >
                    <strong>{site.name}</strong>
                    <span>Lat: {site.lat}° | Lon: {site.lon}° | Alt: {site.alt}m</span>
                    {#if site.terrainType}
                        <span class="terrain-tag">{site.terrainType}</span>
                    {/if}
                </button>

                <div class="site-actions">
                    {#if site.loadingScore}
                        <span class="score-badge loading">Scoring...</span>
                    {:else if site.scoreError || typeof site.score !== 'number'}
                        <span class="score-badge error">N/A</span>
                    {:else}
                        <span
                                class="score-badge {getScoreClass(site.score)}"
                                title="Landing Suitability Score"
                        >
                            {site.score.toFixed(1)}
                        </span>
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
        transition: background-color 0.15s ease;
    }

    .site-card:hover {
        background-color: rgba(234, 234, 234, 0.14);
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

    .site-info strong {
        font-size: 0.85rem;
        color: #fff;
    }

    .site-info span {
        font-size: 0.75rem;
        opacity: 0.8;
    }

    .terrain-tag {
        font-size: 0.7rem !important;
        opacity: 0.6 !important;
    }

    .site-actions {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-shrink: 0;
    }
</style>