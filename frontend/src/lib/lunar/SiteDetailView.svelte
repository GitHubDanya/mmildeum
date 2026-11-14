<script lang="ts">
    import type { SelectedSite } from './types';
    import { getScoreClass } from './telemetry';
    import TelemetryChart from './TelemetryChart.svelte';

    export let site: SelectedSite;
    export let totalSitesCount: number;
    export let onBack: () => void;
    export let onFocus: (site: SelectedSite) => void;
    export let onCompareWith: ((site: SelectedSite) => void) | undefined = undefined;
    export let onRemove: (id: number) => void;
    export let onRetry: (site: SelectedSite) => void;
</script>

<div class="detail-panel">
    <div class="detail-nav">
        <button class="back-btn" on:click={onBack}>
            ← All Sites ({totalSitesCount})
        </button>

        <div class="detail-header-center">
            <strong>{site.name}</strong>
            <span>{site.lat}°, {site.lon}°</span>
        </div>

        <div class="detail-nav-actions">
            {#if site.loadingScore}
                <span class="score-badge loading">...</span>
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

            {#if totalSitesCount >= 2 && onCompareWith}
                <button
                        class="btn btn-outline"
                        on:click={() => onCompareWith && onCompareWith(site)}
                        title="Compare {site.name} with another site"
                >
                    Compare
                </button>
            {/if}

            <button
                    class="btn btn-white"
                    on:click={() => onFocus(site)}
                    title="Center camera on {site.name}"
            >
                Focus
            </button>

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

    {#if site.loadingScore}
        <div class="detail-status">Fetching lunar surface telemetry...</div>
    {:else if site.scoreError}
        <div class="detail-status error-box">
            <span>Failed to load telemetry from the API.</span>
            <button class="btn btn-white" on:click={() => onRetry(site)}>Retry</button>
        </div>
    {:else}
        <div class="wireframe-columns">
            <section class="wireframe-box">
                <header class="wireframe-box-header">
                    <span>Graphs</span>
                    {#if site.isEstimatedSeries}
                        <span
                                class="est-pill"
                                title="Derived from site coordinates until 24h array is provided by API"
                        >
                            24h Model
                        </span>
                    {/if}
                </header>

                <div class="graphs-stack">
                    <TelemetryChart
                            title="Sunlight for 24hrs"
                            data={site.sunlight24h}
                            color="#fde047"
                            unit="%"
                            min={0}
                            max={100}
                            stepped={true}
                            summaryText="{Math.max(...site.sunlight24h).toFixed(0)}% max"
                    />

                    <TelemetryChart
                            title="Earth Visibility for 24hrs"
                            data={site.earthVisibility24h}
                            color="#60a5fa"
                            unit="%"
                            min={0}
                            max={100}
                            summaryText="{Math.max(...site.earthVisibility24h).toFixed(0)}% max"
                    />

                    <TelemetryChart
                            title="Sunlight angle for 24hrs"
                            data={site.sunlightAngle24h}
                            color="#eaeaea"
                            unit="°"
                            min={0}
                            max={90}
                            summaryText="{Math.max(...site.sunlightAngle24h).toFixed(1)}° max"
                    />
                </div>
            </section>

            <section class="wireframe-box">
                <header class="wireframe-box-header">
                    <span>Data points</span>
                </header>

                <div class="datapoints-stack">
                    <div class="datapoint-item">
                        <span class="dp-label">Terrain Type</span>
                        <span class="dp-value">{site.terrainType ?? 'Unknown'}</span>
                    </div>

                    <div class="datapoint-item">
                        <span class="dp-label">Terrain Elevation</span>
                        <span class="dp-value">
                            {site.terrainElevationM !== null
                                ? `${site.terrainElevationM.toFixed(1)} m`
                                : `${site.alt} m`}
                        </span>
                    </div>

                    <div class="datapoint-item">
                        <span class="dp-label">Ground Angle</span>
                        <span class="dp-value">
                            {site.groundAngle !== null ? `${site.groundAngle.toFixed(2)}°` : 'N/A'}
                        </span>
                    </div>

                    <div class="datapoint-item">
                        <span class="dp-label">Peak Sunlight</span>
                        <span class="dp-value">
                            {site.peakSunlight !== null
                                ? `${site.peakSunlight.toFixed(1)}%`
                                : 'N/A'}
                        </span>
                    </div>

                    <div class="datapoint-item">
                        <span class="dp-label">Peak</span>
                        <span class="dp-value">
                            {site.peakValue !== null ? `${site.peakValue.toFixed(1)}°` : 'N/A'}
                        </span>
                    </div>
                </div>
            </section>
        </div>
    {/if}
</div>

<style>
    .detail-panel {
        pointer-events: auto;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        max-height: 78vh;
    }

    .detail-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.9rem;
        padding-bottom: 0.55rem;
        border-bottom: 1px solid rgba(234, 234, 234, 0.15);
    }

    .detail-header-center {
        display: flex;
        flex-direction: column;
        align-items: center;
        line-height: 1.2;
    }

    .detail-header-center strong {
        font-size: 0.92rem;
        color: #fff;
    }

    .detail-header-center span {
        font-size: 0.72rem;
        opacity: 0.65;
    }

    .detail-nav-actions {
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    .btn-outline {
        background-color: transparent;
        color: #eaeaea;
        border: 1px solid rgba(234, 234, 234, 0.35);
    }

    .back-btn {
        background: none;
        border: none;
        color: #eaeaea;
        font-family: inherit;
        font-size: 0.82rem;
        font-weight: 500;
        cursor: pointer;
        padding: 0.25rem 0.45rem;
        border-radius: 6px;
        opacity: 0.85;
        transition: opacity 0.15s ease, background-color 0.15s ease;
    }

    .back-btn:hover {
        opacity: 1;
        background-color: rgba(255, 255, 255, 0.08);
    }

    .wireframe-columns {
        display: grid;
        grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
        gap: 0.75rem;
        overflow-y: auto;
        padding-right: 0.15rem;
    }

    .wireframe-box {
        min-width: 0;
        background-color: rgba(234, 234, 234, 0.06);
        border: 1px solid rgba(234, 234, 234, 0.16);
        border-radius: 10px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
    }

    .wireframe-box-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.55rem 0.75rem;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.02em;
        color: #fff;
        background-color: rgba(234, 234, 234, 0.05);
        border-bottom: 1px solid rgba(234, 234, 234, 0.16);
    }

    .est-pill {
        font-size: 0.65rem;
        font-weight: 400;
        padding: 0.1rem 0.4rem;
        border-radius: 999px;
        background-color: rgba(234, 234, 234, 0.1);
        color: rgba(234, 234, 234, 0.75);
    }

    .graphs-stack {
        display: flex;
        flex-direction: column;
        gap: 0.6rem;
        padding: 0.65rem;
    }

    .datapoints-stack {
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 0.55rem;
        padding: 0.65rem;
        flex: 1;
    }

    .datapoint-item {
        background-color: rgba(7, 7, 7, 0.55);
        border: 1px solid rgba(234, 234, 234, 0.1);
        border-radius: 8px;
        padding: 0.6rem 0.7rem;
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
    }

    .dp-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.6;
    }

    .dp-value {
        font-size: 0.88rem;
        font-weight: 500;
        color: #fff;
        word-break: break-word;
    }

    .detail-status {
        font-size: 0.82rem;
        opacity: 0.8;
        padding: 0.85rem;
        border-radius: 8px;
        background-color: rgba(234, 234, 234, 0.06);
        text-align: center;
    }

    .detail-status.error-box {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.6rem;
        background-color: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.25);
        color: #fca5a5;
        opacity: 1;
    }

    @media (max-width: 1150px) {
        .wireframe-columns {
            grid-template-columns: 1fr;
        }
    }
</style>