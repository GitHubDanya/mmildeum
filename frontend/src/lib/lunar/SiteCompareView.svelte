<script lang="ts">
    import type { SelectedSite } from './types';
    import { evaluateSiteAtTimestamp, formatShortDateOnlyUtc, getScoreClass } from './telemetry';
    import TelemetryChart from './TelemetryChart.svelte';

    export let siteA: SelectedSite;
    export let siteB: SelectedSite;
    export let allSites: SelectedSite[] = [];
    export let selectedTimeMs: number;
    export let timelineStartMs: number;
    export let onChangePair: (pair: [number, number]) => void;
    export let onBack: () => void;
    export let onFocus: (site: SelectedSite) => void;
    export let onRetry: (site: SelectedSite) => void;

    const COLOR_A = '#facc15';
    const COLOR_B = '#38bdf8';

    function handleSelectA(e: Event) {
        const nextId = Number((e.currentTarget as HTMLSelectElement).value);
        if (nextId === siteB.id) {
            onChangePair([siteB.id, siteA.id]);
        } else {
            onChangePair([nextId, siteB.id]);
        }
    }

    function handleSelectB(e: Event) {
        const nextId = Number((e.currentTarget as HTMLSelectElement).value);
        if (nextId === siteA.id) {
            onChangePair([siteB.id, siteA.id]);
        } else {
            onChangePair([siteA.id, nextId]);
        }
    }

    function swapSites() {
        onChangePair([siteB.id, siteA.id]);
    }

    function compareWinner(
        valA: number | null,
        valB: number | null,
        higherIsBetter: boolean
    ): 'A' | 'B' | null {
        if (valA === null || valB === null || Math.abs(valA - valB) < 0.01) return null;
        if (higherIsBetter) return valA > valB ? 'A' : 'B';
        return valA < valB ? 'A' : 'B';
    }

    $: evalA = evaluateSiteAtTimestamp(siteA, selectedTimeMs);
    $: evalB = evaluateSiteAtTimestamp(siteB, selectedTimeMs);
    $: dateWinner = compareWinner(evalA.suitabilityScore, evalB.suitabilityScore, true);

    $: scoreWinner = compareWinner(siteA.score, siteB.score, true);
    $: slopeWinner = compareWinner(siteA.groundAngle, siteB.groundAngle, false);
    $: roughnessWinner = compareWinner(siteA.lolaRoughnessDeg, siteB.lolaRoughnessDeg, false);
    $: visibilityWinner = compareWinner(
        siteA.visibilityCoveragePct,
        siteB.visibilityCoveragePct,
        true
    );
    $: avgSunWinner = compareWinner(siteA.daytimeAvgSunAngle, siteB.daytimeAvgSunAngle, true);
    $: canOverlayVisibility = siteA.visibilityLabels.length === siteB.visibilityLabels.length;

    $: visibilityCursorIndex = (() => {
        if (!siteA.hasRealVisibility || siteA.visibilitySeries.length === 0) return null;
        const idx = Math.round((selectedTimeMs - timelineStartMs) / (6 * 3600 * 1000));
        return Math.max(0, Math.min(siteA.visibilitySeries.length - 1, idx));
    })();
</script>

<div class="compare-panel">
    <div class="compare-nav">
        <button class="back-btn" on:click={onBack}>
            ← All Sites ({allSites.length})
        </button>

        <span class="compare-heading">Site Comparison</span>

        <button class="btn btn-outline" on:click={swapSites} title="Swap Site A and Site B">
            Swap ⇄
        </button>
    </div>

    <div class="selectors-row">
        <div class="selector-card" style="border-top: 2px solid {COLOR_A};">
            <div class="selector-top">
                <select
                        class="site-select"
                        value={siteA.id}
                        on:change={handleSelectA}
                        aria-label="Select first site to compare"
                >
                    {#each allSites as s (s.id)}
                        <option value={s.id}>{s.name} ({s.lat}°, {s.lon}°)</option>
                    {/each}
                </select>

                <button
                        class="mini-focus-btn"
                        on:click={() => onFocus(siteA)}
                        title="Fly to {siteA.name}"
                >
                    Focus
                </button>
            </div>

            <div class="selector-meta">
                <span>{siteA.lat}°, {siteA.lon}°</span>
                {#if siteA.loadingScore}
                    <span class="score-badge loading">...</span>
                {:else if siteA.scoreError}
                    <span class="score-badge error">Error</span>
                {:else if typeof siteA.score === 'number'}
                    <span class="score-badge {getScoreClass(siteA.score)}">
                        {siteA.score.toFixed(1)}
                    </span>
                {/if}
            </div>
        </div>

        <div class="selector-card" style="border-top: 2px solid {COLOR_B};">
            <div class="selector-top">
                <select
                        class="site-select"
                        value={siteB.id}
                        on:change={handleSelectB}
                        aria-label="Select second site to compare"
                >
                    {#each allSites as s (s.id)}
                        <option value={s.id}>{s.name} ({s.lat}°, {s.lon}°)</option>
                    {/each}
                </select>

                <button
                        class="mini-focus-btn"
                        on:click={() => onFocus(siteB)}
                        title="Fly to {siteB.name}"
                >
                    Focus
                </button>
            </div>

            <div class="selector-meta">
                <span>{siteB.lat}°, {siteB.lon}°</span>
                {#if siteB.loadingScore}
                    <span class="score-badge loading">...</span>
                {:else if siteB.scoreError}
                    <span class="score-badge error">Error</span>
                {:else if typeof siteB.score === 'number'}
                    <span class="score-badge {getScoreClass(siteB.score)}">
                        {siteB.score.toFixed(1)}
                    </span>
                {/if}
            </div>
        </div>
    </div>

    {#if siteA.scoreError || siteB.scoreError}
        <div class="error-strip">
            <span>Telemetry failed for one or more sites.</span>
            <div class="error-actions">
                {#if siteA.scoreError}
                    <button class="btn btn-white" on:click={() => onRetry(siteA)}>
                        Retry {siteA.name}
                    </button>
                {/if}
                {#if siteB.scoreError}
                    <button class="btn btn-white" on:click={() => onRetry(siteB)}>
                        Retry {siteB.name}
                    </button>
                {/if}
            </div>
        </div>
    {/if}

    <div class="compare-columns">
        <section class="wireframe-box">
            <header class="wireframe-box-header">
                <span>Overlay Graphs</span>
                {#if siteA.isEstimatedSunSeries || siteB.isEstimatedSunSeries}
                    <span class="est-pill">24h Sun Model</span>
                {/if}
            </header>

            <div class="graphs-stack">
                <TelemetryChart
                        title="Sunlight for 24hrs"
                        data={siteA.sunlight24h}
                        color={COLOR_A}
                        primaryLabel={siteA.name}
                        compareData={siteB.sunlight24h}
                        compareColor={COLOR_B}
                        compareLabel={siteB.name}
                        unit="%"
                        min={0}
                        max={100}
                        stepped={true}
                />

                <TelemetryChart
                        title={siteA.hasRealVisibility ? 'Earth Visibility' : 'Earth Visibility for 24hrs'}
                        data={siteA.visibilitySeries}
                        labels={siteA.visibilityLabels}
                        color={COLOR_A}
                        primaryLabel={siteA.name}
                        compareData={canOverlayVisibility ? siteB.visibilitySeries : undefined}
                        compareColor={COLOR_B}
                        compareLabel={siteB.name}
                        unit="%"
                        min={0}
                        max={100}
                        stepped={siteA.hasRealVisibility}
                        activeIndex={visibilityCursorIndex}
                />

                <TelemetryChart
                        title="Sunlight angle for 24hrs"
                        data={siteA.sunlightAngle24h}
                        color={COLOR_A}
                        primaryLabel={siteA.name}
                        compareData={siteB.sunlightAngle24h}
                        compareColor={COLOR_B}
                        compareLabel={siteB.name}
                        unit="°"
                        min={0}
                        max={90}
                />
            </div>
        </section>

        <section class="wireframe-box">
            <header class="wireframe-box-header">
                <span>Metrics Comparison</span>
            </header>

            <div class="metrics-table">
                <div class="metric-row header-row">
                    <span>Metric</span>
                    <span style="color: {COLOR_A};">{siteA.name}</span>
                    <span style="color: {COLOR_B};">{siteB.name}</span>
                </div>

                <div class="metric-row highlight-row">
                    <span class="m-label">On {formatShortDateOnlyUtc(selectedTimeMs)}</span>
                    <span class="m-val" class:winner={dateWinner === 'A'}>
                        {evalA.status}
                        <small class="m-sub">
                            {evalA.isEarthVisible ? 'LOS' : 'No LOS'} · {evalA.sunAngleDeg.toFixed(0)}°
                        </small>
                    </span>
                    <span class="m-val" class:winner={dateWinner === 'B'}>
                        {evalB.status}
                        <small class="m-sub">
                            {evalB.isEarthVisible ? 'LOS' : 'No LOS'} · {evalB.sunAngleDeg.toFixed(0)}°
                        </small>
                    </span>
                </div>

                {#if siteA.score !== null || siteB.score !== null}
                    <div class="metric-row">
                        <span class="m-label">Score</span>
                        <span class="m-val" class:winner={scoreWinner === 'A'}>
                            {siteA.score !== null ? siteA.score.toFixed(1) : 'N/A'}
                        </span>
                        <span class="m-val" class:winner={scoreWinner === 'B'}>
                            {siteB.score !== null ? siteB.score.toFixed(1) : 'N/A'}
                        </span>
                    </div>
                {/if}

                <div class="metric-row">
                    <span class="m-label">Elevation</span>
                    <span class="m-val">
                        {siteA.terrainElevationM !== null
                            ? `${siteA.terrainElevationM.toFixed(1)} m`
                            : `${siteA.alt} m`}
                    </span>
                    <span class="m-val">
                        {siteB.terrainElevationM !== null
                            ? `${siteB.terrainElevationM.toFixed(1)} m`
                            : `${siteB.alt} m`}
                    </span>
                </div>

                <div class="metric-row">
                    <span class="m-label">Ground Angle</span>
                    <span class="m-val" class:winner={slopeWinner === 'A'}>
                        {siteA.groundAngle !== null ? `${siteA.groundAngle.toFixed(2)}°` : 'N/A'}
                    </span>
                    <span class="m-val" class:winner={slopeWinner === 'B'}>
                        {siteB.groundAngle !== null ? `${siteB.groundAngle.toFixed(2)}°` : 'N/A'}
                    </span>
                </div>

                <div class="metric-row">
                    <span class="m-label">LOLA Roughness</span>
                    <span class="m-val" class:winner={roughnessWinner === 'A'}>
                        {siteA.lolaRoughnessDeg !== null
                            ? `${siteA.lolaRoughnessDeg.toFixed(3)}°`
                            : 'N/A'}
                    </span>
                    <span class="m-val" class:winner={roughnessWinner === 'B'}>
                        {siteB.lolaRoughnessDeg !== null
                            ? `${siteB.lolaRoughnessDeg.toFixed(3)}°`
                            : 'N/A'}
                    </span>
                </div>

                <div class="metric-row">
                    <span class="m-label">Avg Sun Angle</span>
                    <span class="m-val" class:winner={avgSunWinner === 'A'}>
                        {siteA.daytimeAvgSunAngle !== null
                            ? `${siteA.daytimeAvgSunAngle.toFixed(2)}°`
                            : 'N/A'}
                    </span>
                    <span class="m-val" class:winner={avgSunWinner === 'B'}>
                        {siteB.daytimeAvgSunAngle !== null
                            ? `${siteB.daytimeAvgSunAngle.toFixed(2)}°`
                            : 'N/A'}
                    </span>
                </div>

                <div class="metric-row">
                    <span class="m-label">Visibility</span>
                    <span class="m-val" class:winner={visibilityWinner === 'A'}>
                        {siteA.visibilityCoveragePct !== null
                            ? `${siteA.visibilityCoveragePct.toFixed(1)}% (${siteA.visibilityWindows.length})`
                            : 'N/A'}
                    </span>
                    <span class="m-val" class:winner={visibilityWinner === 'B'}>
                        {siteB.visibilityCoveragePct !== null
                            ? `${siteB.visibilityCoveragePct.toFixed(1)}% (${siteB.visibilityWindows.length})`
                            : 'N/A'}
                    </span>
                </div>
            </div>
        </section>
    </div>
</div>

<style>
    .compare-panel {
        pointer-events: auto;
        display: flex;
        flex-direction: column;
        gap: 0.65rem;
        max-height: 80vh;
    }

    .compare-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(234, 234, 234, 0.15);
    }

    .compare-heading {
        font-size: 0.9rem;
        font-weight: 600;
        color: #fff;
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

    .btn-outline {
        background-color: transparent;
        color: #eaeaea;
        border: 1px solid rgba(234, 234, 234, 0.35);
    }

    .selectors-row {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.65rem;
    }

    .selector-card {
        background-color: rgba(234, 234, 234, 0.07);
        border: 1px solid rgba(234, 234, 234, 0.14);
        border-radius: 8px;
        padding: 0.5rem 0.65rem;
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
    }

    .selector-top {
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    .site-select {
        flex: 1;
        min-width: 0;
        background-color: #0d0d0d;
        color: #fff;
        border: 1px solid rgba(234, 234, 234, 0.2);
        border-radius: 6px;
        padding: 0.25rem 0.4rem;
        font-family: inherit;
        font-size: 0.78rem;
        cursor: pointer;
    }

    .mini-focus-btn {
        background-color: rgba(234, 234, 234, 0.14);
        color: #eaeaea;
        border: none;
        border-radius: 6px;
        padding: 0.25rem 0.5rem;
        font-family: inherit;
        font-size: 0.7rem;
        cursor: pointer;
        flex-shrink: 0;
    }

    .mini-focus-btn:hover {
        background-color: rgba(234, 234, 234, 0.25);
    }

    .selector-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.72rem;
        opacity: 0.85;
    }

    .error-strip {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        padding: 0.45rem 0.65rem;
        border-radius: 8px;
        background-color: rgba(239, 68, 68, 0.14);
        border: 1px solid rgba(239, 68, 68, 0.3);
        color: #fca5a5;
        font-size: 0.76rem;
    }

    .error-actions {
        display: flex;
        gap: 0.4rem;
    }

    .compare-columns {
        display: grid;
        grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
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
        padding: 0.5rem 0.75rem;
        font-size: 0.8rem;
        font-weight: 600;
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
        gap: 0.55rem;
        padding: 0.6rem;
    }

    .metrics-table {
        display: flex;
        flex-direction: column;
        padding: 0.5rem 0.65rem;
        gap: 0.35rem;
    }

    .metric-row {
        display: grid;
        grid-template-columns: 1.05fr 1fr 1fr;
        align-items: center;
        gap: 0.4rem;
        padding: 0.42rem 0.5rem;
        border-radius: 6px;
        background-color: rgba(7, 7, 7, 0.5);
        border: 1px solid rgba(234, 234, 234, 0.08);
        font-size: 0.78rem;
    }

    .metric-row.highlight-row {
        background-color: rgba(234, 234, 234, 0.07);
        border-color: rgba(234, 234, 234, 0.2);
    }

    .metric-row.header-row {
        background-color: transparent;
        border: none;
        padding: 0.2rem 0.5rem;
        font-size: 0.72rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        opacity: 0.85;
    }

    .m-label {
        font-size: 0.7rem;
        opacity: 0.65;
    }

    .m-val {
        display: flex;
        flex-direction: column;
        color: rgba(234, 234, 234, 0.9);
        font-weight: 500;
        word-break: break-word;
    }

    .m-sub {
        font-size: 0.65rem;
        font-weight: 400;
        opacity: 0.7;
    }

    .m-val.winner {
        color: #86efac;
        font-weight: 600;
    }

    @media (max-width: 1150px) {
        .compare-columns {
            grid-template-columns: 1fr;
        }
    }
</style>