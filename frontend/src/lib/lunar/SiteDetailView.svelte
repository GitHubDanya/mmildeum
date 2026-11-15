<script lang="ts">
    import type { SelectedSite } from './types';
    import {
        evaluateSiteAtTimestamp,
        formatDurationHours,
        formatShortUtc,
        formatWindowRange,
        getScoreClass
    } from './telemetry';
    import TelemetryChart from './TelemetryChart.svelte';

    export let site: SelectedSite;
    export let totalSitesCount: number;
    export let selectedTimeMs: number;
    export let missionDurationHours = 72;
    export let timelineStartMs: number;
    export let onBack: () => void;
    export let onFocus: (site: SelectedSite) => void;
    export let onCompareWith: ((site: SelectedSite) => void) | undefined = undefined;
    export let onRemove: (id: number) => void;
    export let onRetry: (site: SelectedSite) => void;
    export let onRetrySunlightDuration: ((site: SelectedSite) => void) | undefined = undefined;

    $: dateEval = evaluateSiteAtTimestamp(site, selectedTimeMs);
    $: missionEndMs = selectedTimeMs + missionDurationHours * 3600 * 1000;

    $: visibilityCursorIndex = (() => {
        if (!site.hasRealVisibility || site.visibilitySeries.length === 0) return null;
        const idx = Math.round((selectedTimeMs - timelineStartMs) / (6 * 3600 * 1000));
        return Math.max(0, Math.min(site.visibilitySeries.length - 1, idx));
    })();
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
            {:else if site.scoreError}
                <span class="score-badge error">Error</span>
            {:else if typeof site.score === 'number'}
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
                    {#if site.isEstimatedSunSeries}
                        <span
                                class="est-pill"
                                title="Sun graphs derived from site coordinates; visibility plotted from API windows"
                        >
                            24h Sun Model
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
                            title={site.hasRealVisibility ? 'Earth Visibility' : 'Earth Visibility for 24hrs'}
                            data={site.visibilitySeries}
                            labels={site.visibilityLabels}
                            color="#60a5fa"
                            unit="%"
                            min={0}
                            max={100}
                            stepped={site.hasRealVisibility}
                            activeIndex={visibilityCursorIndex}
                            summaryText={site.visibilityCoveragePct !== null
                            ? `${site.visibilityCoveragePct.toFixed(0)}% visible`
                            : `${Math.max(...site.visibilitySeries).toFixed(0)}% max`}
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
                    <!-- Mission sunlight from the unified site evaluation -->
                    <div class="datapoint-item mission-sun-card">
                        <div class="dp-top-row">
                            <span class="dp-label">
                                Mission Sunlight ({formatDurationHours(missionDurationHours)})
                            </span>
                            {#if site.missionSunlight}
                                <span class="sun-pct-chip">
                                    {site.missionSunlight.sunlitPercentage.toFixed(1)}% Sunlit
                                </span>
                            {/if}
                        </div>

                        <span class="dp-interval-sub">
                            {formatShortUtc(selectedTimeMs)} → {formatShortUtc(missionEndMs)} UTC
                        </span>

                        {#if site.loadingMissionSunlight}
                            <span class="dp-value muted">Calculating sunlight duration...</span>
                        {:else if site.missionSunlightError}
                            <div class="sun-err-row">
                                <span class="sun-err-text">{site.missionSunlightError}</span>
                                {#if onRetrySunlightDuration}
                                    <button
                                            class="mini-retry-btn"
                                            on:click={() => onRetrySunlightDuration && onRetrySunlightDuration(site)}
                                    >
                                        Retry
                                    </button>
                                {/if}
                            </div>
                        {:else if site.missionSunlight}
                            <span class="dp-value sun-highlight">
                                {site.missionSunlight.sunlitHours.toFixed(1)} hrs
                                <small class="dp-sub">
                                    of {site.missionSunlight.missionHours.toFixed(0)} hrs ({site.missionSunlight.stepMinutes}m step)
                                </small>
                            </span>
                            <div class="sun-progress-track" aria-hidden="true">
                                <div
                                        class="sun-progress-fill"
                                        style="width: {site.missionSunlight.sunlitPercentage}%;"
                                ></div>
                            </div>
                        {:else}
                            <span class="dp-value muted">Pending interval</span>
                        {/if}
                    </div>

                    <div class="datapoint-item date-eval-card">
                        <div class="dp-top-row">
                            <span class="dp-label">Touchdown ({formatShortUtc(selectedTimeMs)} UTC)</span>
                            <span class="status-chip {dateEval.status.toLowerCase()}">
                                {dateEval.status}
                            </span>
                        </div>
                        <span class="dp-value">
                            {dateEval.isEarthVisible ? 'Earth Visible' : 'Earth Occluded'} · Sun {dateEval.sunAngleDeg.toFixed(1)}°
                        </span>
                    </div>

                    {#if site.terrainType}
                        <div class="datapoint-item">
                            <span class="dp-label">Terrain Type</span>
                            <span class="dp-value">{site.terrainType}</span>
                        </div>
                    {/if}

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
                        <span class="dp-label">LOLA Roughness</span>
                        <span class="dp-value">
                            {site.lolaRoughnessDeg !== null
                                ? `${site.lolaRoughnessDeg.toFixed(3)}°`
                                : 'N/A'}
                        </span>
                    </div>

                    <div class="datapoint-item">
                        <span class="dp-label">Daytime Avg Sun Angle</span>
                        <span class="dp-value">
                            {site.daytimeAvgSunAngle !== null
                                ? `${site.daytimeAvgSunAngle.toFixed(2)}°`
                                : 'N/A'}
                        </span>
                    </div>

                    <div class="datapoint-item">
                        <span class="dp-label">
                            Visibility Windows ({site.visibilityWindows.length})
                        </span>
                        {#if site.visibilityWindows.length > 0}
                            <ul class="windows-list">
                                {#each site.visibilityWindows as win}
                                    <li>{formatWindowRange(win)}</li>
                                {/each}
                            </ul>
                        {:else}
                            <span class="dp-value">None</span>
                        {/if}
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
        gap: 0.45rem;
        padding: 0.65rem;
        flex: 1;
    }

    .datapoint-item {
        background-color: rgba(7, 7, 7, 0.55);
        border: 1px solid rgba(234, 234, 234, 0.1);
        border-radius: 8px;
        padding: 0.5rem 0.68rem;
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
    }

    .mission-sun-card {
        border-color: rgba(250, 204, 21, 0.32);
        background-color: rgba(250, 204, 21, 0.06);
    }

    .dp-interval-sub {
        font-size: 0.68rem;
        opacity: 0.7;
    }

    .sun-pct-chip {
        font-size: 0.65rem;
        font-weight: 600;
        padding: 0.08rem 0.45rem;
        border-radius: 999px;
        background-color: rgba(250, 204, 21, 0.2);
        color: #fde047;
    }

    .sun-highlight {
        color: #fde047 !important;
    }

    .dp-sub {
        font-size: 0.72rem;
        font-weight: 400;
        color: rgba(234, 234, 234, 0.7);
        margin-left: 0.25rem;
    }

    .sun-progress-track {
        width: 100%;
        height: 5px;
        border-radius: 999px;
        background-color: rgba(234, 234, 234, 0.12);
        overflow: hidden;
        margin-top: 0.15rem;
    }

    .sun-progress-fill {
        height: 100%;
        background-color: #facc15;
        border-radius: 999px;
        transition: width 0.25s ease;
    }

    .sun-err-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.4rem;
    }

    .sun-err-text {
        font-size: 0.72rem;
        color: #fca5a5;
    }

    .mini-retry-btn {
        background-color: rgba(234, 234, 234, 0.16);
        color: #fff;
        border: none;
        border-radius: 4px;
        padding: 0.15rem 0.45rem;
        font-family: inherit;
        font-size: 0.68rem;
        cursor: pointer;
    }

    .date-eval-card {
        border-color: rgba(234, 234, 234, 0.22);
        background-color: rgba(234, 234, 234, 0.07);
    }

    .dp-top-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.4rem;
    }

    .status-chip {
        font-size: 0.65rem;
        font-weight: 600;
        padding: 0.08rem 0.45rem;
        border-radius: 999px;
    }

    .status-chip.optimal {
        background-color: rgba(34, 197, 94, 0.22);
        color: #86efac;
    }

    .status-chip.marginal {
        background-color: rgba(234, 179, 8, 0.2);
        color: #fde047;
    }

    .status-chip.no-go {
        background-color: rgba(239, 68, 68, 0.2);
        color: #fca5a5;
    }

    .dp-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.6;
    }

    .dp-value {
        font-size: 0.85rem;
        font-weight: 500;
        color: #fff;
        word-break: break-word;
    }

    .dp-value.muted {
        font-size: 0.76rem;
        opacity: 0.65;
    }

    .windows-list {
        list-style: none;
        margin: 0.15rem 0 0;
        padding: 0;
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
    }

    .windows-list li {
        font-size: 0.76rem;
        font-weight: 500;
        color: #93c5fd;
        background-color: rgba(59, 130, 246, 0.1);
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 5px;
        padding: 0.22rem 0.45rem;
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
