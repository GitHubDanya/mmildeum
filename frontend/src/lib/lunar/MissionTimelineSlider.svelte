<script lang="ts">
    import { onDestroy } from 'svelte';
    import type { SelectedSite } from './types';
    import {
        evaluateSiteAtTimestamp,
        findRecommendedLandingWindows,
        formatDurationHours,
        formatFullUtc,
        formatShortDateOnlyUtc,
        formatShortUtc
    } from './telemetry';

    export let startMs: number;
    export let endMs: number;
    export let selectedTimeMs: number;
    export let missionDurationHours = 72;
    export let targetSites: SelectedSite[] = [];
    export let rightInsetPx = 0;
    export let onChangeTime: (ms: number) => void;
    export let onChangeDuration: (hours: number) => void;

    const STEP_MS = 1 * 3600 * 1000;
    const DURATION_PRESETS = [
        { label: '24h', hours: 24 },
        { label: '3d', hours: 72 },
        { label: '7d', hours: 168 },
        { label: '14d', hours: 336 },
        { label: '28d', hours: 672 }
    ];

    let isPlaying = false;
    let playInterval: ReturnType<typeof setInterval> | undefined = undefined;

    $: safeTimeMs = Math.max(startMs, Math.min(endMs, selectedTimeMs));
    $: missionEndMs = safeTimeMs + missionDurationHours * 3600 * 1000;
    $: recommendedWindows = findRecommendedLandingWindows(
        targetSites,
        startMs,
        endMs,
        missionDurationHours
    );

    $: missionSpanOverlay = (() => {
        const span = Math.max(1, endMs - startMs);
        const leftPct = Math.max(0, Math.min(100, ((safeTimeMs - startMs) / span) * 100));
        const rightPct = Math.max(leftPct, Math.min(100, ((missionEndMs - startMs) / span) * 100));
        return {
            leftPct,
            widthPct: Math.max(0.8, rightPct - leftPct)
        };
    })();

    $: trackSegments = (() => {
        const count = 62;
        if (targetSites.length === 0 || endMs <= startMs) {
            return Array.from({ length: count }, () => 'neutral');
        }

        const span = endMs - startMs;
        return Array.from({ length: count }, (_, i) => {
            const t = startMs + ((i + 0.5) / count) * span;
            const evals = targetSites.map((s) => evaluateSiteAtTimestamp(s, t));
            if (evals.every((e) => e.status === 'Optimal')) return 'optimal';
            if (evals.some((e) => e.status === 'Optimal' || e.status === 'Marginal')) {
                return 'marginal';
            }
            return 'nogo';
        });
    })();

    $: liveSiteEvaluations = targetSites.map((site, idx) => ({
        site,
        accentColor: targetSites.length > 1 ? (idx === 0 ? '#facc15' : '#38bdf8') : '#eaeaea',
        evalData: evaluateSiteAtTimestamp(site, safeTimeMs)
    }));

    function handleRangeInput(e: Event) {
        stopPlayback();
        const val = Number((e.currentTarget as HTMLInputElement).value);
        onChangeTime(val);
    }

    function handleCustomHoursInput(e: Event) {
        const raw = Number((e.currentTarget as HTMLInputElement).value);
        if (Number.isFinite(raw) && raw >= 1) {
            onChangeDuration(Math.min(720, Math.round(raw)));
        }
    }

    function stepByHours(hours: number) {
        stopPlayback();
        const next = Math.max(startMs, Math.min(endMs, safeTimeMs + hours * 3600 * 1000));
        onChangeTime(next);
    }

    function jumpToWindow(peakMs: number) {
        stopPlayback();
        onChangeTime(Math.max(startMs, Math.min(endMs, peakMs)));
    }

    function togglePlay() {
        if (isPlaying) {
            stopPlayback();
            return;
        }

        isPlaying = true;
        if (safeTimeMs >= endMs) {
            onChangeTime(startMs);
        }

        playInterval = setInterval(() => {
            const next = safeTimeMs + STEP_MS;
            if (next > endMs) {
                stopPlayback();
            } else {
                onChangeTime(next);
            }
        }, 180);
    }

    function stopPlayback() {
        isPlaying = false;
        if (playInterval !== undefined) {
            clearInterval(playInterval);
            playInterval = undefined;
        }
    }

    onDestroy(() => {
        stopPlayback();
    });
</script>

<div
        class="timeline-dock"
        style="width: min(670px, calc(100vw - {rightInsetPx}px - 44px));"
>
    <div class="timeline-header">
        <div class="timeline-title-group">
            <span class="timeline-label">Landing</span>
            <strong class="timeline-current-date">{formatFullUtc(safeTimeMs)}</strong>
            <span class="mission-end-hint" title="Mission End ({formatDurationHours(missionDurationHours)})">
                → {formatShortUtc(missionEndMs)} UTC
            </span>
        </div>

        <div class="timeline-controls">
            <button
                    class="step-btn"
                    on:click={() => stepByHours(-12)}
                    disabled={safeTimeMs <= startMs}
                    title="Back 12 hours"
            >
                -12h
            </button>
            <button
                    class="step-btn play-btn"
                    on:click={togglePlay}
                    title={isPlaying ? 'Pause timeline' : 'Scrub through dates'}
            >
                {isPlaying ? '❚❚' : '▶'}
            </button>
            <button
                    class="step-btn"
                    on:click={() => stepByHours(12)}
                    disabled={safeTimeMs >= endMs}
                    title="Forward 12 hours"
            >
                +12h
            </button>
        </div>
    </div>

    <!-- Mission Duration Selector Bar -->
    <div class="duration-row">
        <span class="duration-label">Mission Duration:</span>
        <div class="duration-presets">
            {#each DURATION_PRESETS as preset}
                <button
                        class="dur-chip"
                        class:active={missionDurationHours === preset.hours}
                        on:click={() => onChangeDuration(preset.hours)}
                >
                    {preset.label}
                </button>
            {/each}
        </div>

        <label class="custom-dur-wrap" title="Custom mission duration in hours (1–720h)">
            <input
                    class="custom-dur-input"
                    type="number"
                    min="1"
                    max="720"
                    step="1"
                    value={missionDurationHours}
                    on:change={handleCustomHoursInput}
                    aria-label="Mission duration in hours"
            />
            <span>hrs</span>
        </label>
    </div>

    <!-- Track with suitability heat-map bar & active mission span overlay -->
    <div class="slider-track-wrapper">
        <div class="suitability-bar" aria-hidden="true">
            {#each trackSegments as seg}
                <span class="suitability-seg {seg}"></span>
            {/each}
        </div>

        <div
                class="mission-span-overlay"
                aria-hidden="true"
                style="left: {missionSpanOverlay.leftPct}%; width: {missionSpanOverlay.widthPct}%;"
        ></div>

        <input
                class="date-slider"
                type="range"
                min={startMs}
                max={endMs}
                step={STEP_MS}
                value={safeTimeMs}
                on:input={handleRangeInput}
                aria-label="Select candidate landing date"
        />

        <div class="slider-endpoints">
            <span>{formatShortDateOnlyUtc(startMs)}</span>
            <span class="legend-inline">
                <i class="dot optimal"></i> Optimal
                <i class="dot marginal"></i> Partial
                <i class="dot span"></i> Mission Span
            </span>
            <span>{formatShortDateOnlyUtc(endMs)}</span>
        </div>
    </div>

    <!-- Recommended Landing Dates & Live Sunlight Duration Evaluation -->
    {#if targetSites.length > 0}
        <div class="timeline-footer">
            <div class="recommended-row">
                <span class="rec-heading">
                    {targetSites.length > 1
                        ? `Joint Best Starts (${formatDurationHours(missionDurationHours)}):`
                        : `Best Starts (${formatDurationHours(missionDurationHours)}):`}
                </span>
                {#if recommendedWindows.length > 0}
                    <div class="rec-chips">
                        {#each recommendedWindows as win}
                            {@const isInside = safeTimeMs >= win.startMs && safeTimeMs <= win.endMs}
                            <button
                                    class="rec-chip"
                                    class:active={isInside}
                                    on:click={() => jumpToWindow(win.peakMs)}
                                    title="Jump to optimal start window ({win.label})"
                            >
                                ★ {win.label}
                            </button>
                        {/each}
                    </div>
                {:else}
                    <span class="no-rec">No optimal overlap in range</span>
                {/if}
            </div>

            <div class="site-verdicts">
                {#each liveSiteEvaluations as item (item.site.id)}
                    <div class="verdict-pill">
                        <span class="verdict-site" style="color: {item.accentColor};">
                            {item.site.name}
                        </span>
                        <span class="verdict-detail">
                            {item.evalData.isEarthVisible ? 'Earth LOS' : 'No LOS'} · Sun {item.evalData.sunAngleDeg.toFixed(0)}°
                        </span>
                        {#if item.site.loadingMissionSunlight}
                            <span class="sun-dur-tag loading">Sunlit: ...</span>
                        {:else if item.site.missionSunlight}
                            <span
                                    class="sun-dur-tag"
                                    title="Calculated via /sunlight-duration for {formatDurationHours(missionDurationHours)}"
                            >
                                ☀ {item.site.missionSunlight.sunlitHours.toFixed(1)}h ({item.site.missionSunlight.sunlitPercentage.toFixed(0)}%)
                            </span>
                        {:else if item.site.missionSunlightError}
                            <span class="sun-dur-tag err" title={item.site.missionSunlightError}>
                                ☀ N/A
                            </span>
                        {/if}
                        <span class="verdict-badge {item.evalData.status.toLowerCase()}">
                            {item.evalData.status}
                        </span>
                    </div>
                {/each}
            </div>
        </div>
    {/if}
</div>

<style>
    .timeline-dock {
        position: absolute;
        bottom: 20px;
        left: 20px;
        z-index: 10;
        background-color: rgba(7, 7, 7, 0.88);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(234, 234, 234, 0.16);
        border-radius: 12px;
        padding: 0.65rem 0.85rem;
        display: flex;
        flex-direction: column;
        gap: 0.45rem;
        box-sizing: border-box;
        transition: width 0.25s ease;
    }

    .timeline-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
    }

    .timeline-title-group {
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        gap: 0.45rem;
    }

    .timeline-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.65;
    }

    .timeline-current-date {
        font-size: 0.82rem;
        font-weight: 600;
        color: #fff;
        font-variant-numeric: tabular-nums;
    }

    .mission-end-hint {
        font-size: 0.72rem;
        color: #fde047;
        opacity: 0.9;
        font-variant-numeric: tabular-nums;
    }

    .timeline-controls {
        display: flex;
        align-items: center;
        gap: 0.3rem;
        flex-shrink: 0;
    }

    .step-btn {
        background-color: rgba(234, 234, 234, 0.1);
        color: #eaeaea;
        border: 1px solid rgba(234, 234, 234, 0.16);
        border-radius: 6px;
        padding: 0.18rem 0.45rem;
        font-family: inherit;
        font-size: 0.7rem;
        cursor: pointer;
        transition: background-color 0.15s ease;
    }

    .step-btn:hover:not(:disabled) {
        background-color: rgba(234, 234, 234, 0.22);
    }

    .step-btn:disabled {
        opacity: 0.35;
        cursor: not-allowed;
    }

    .play-btn {
        min-width: 26px;
        text-align: center;
    }

    .duration-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.4rem;
        padding: 0.25rem 0;
    }

    .duration-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.65;
    }

    .duration-presets {
        display: flex;
        align-items: center;
        gap: 0.28rem;
    }

    .dur-chip {
        background-color: rgba(234, 234, 234, 0.08);
        color: rgba(234, 234, 234, 0.85);
        border: 1px solid rgba(234, 234, 234, 0.16);
        border-radius: 6px;
        padding: 0.15rem 0.45rem;
        font-family: inherit;
        font-size: 0.7rem;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.15s ease, border-color 0.15s ease;
    }

    .dur-chip:hover {
        background-color: rgba(234, 234, 234, 0.18);
    }

    .dur-chip.active {
        background-color: rgba(250, 204, 21, 0.2);
        border-color: #facc15;
        color: #fde047;
        font-weight: 600;
    }

    .custom-dur-wrap {
        display: inline-flex;
        align-items: center;
        gap: 0.25rem;
        margin-left: auto;
        font-size: 0.7rem;
        opacity: 0.85;
    }

    .custom-dur-input {
        width: 52px;
        background-color: #0d0d0d;
        color: #fff;
        border: 1px solid rgba(234, 234, 234, 0.24);
        border-radius: 5px;
        padding: 0.15rem 0.35rem;
        font-family: inherit;
        font-size: 0.7rem;
        text-align: right;
    }

    .slider-track-wrapper {
        position: relative;
        display: flex;
        flex-direction: column;
        gap: 0.25rem;
        padding-top: 2px;
    }

    .suitability-bar {
        position: absolute;
        top: 7px;
        left: 0;
        right: 0;
        height: 6px;
        border-radius: 999px;
        overflow: hidden;
        display: flex;
        background-color: rgba(234, 234, 234, 0.12);
        pointer-events: none;
    }

    .mission-span-overlay {
        position: absolute;
        top: 4px;
        height: 12px;
        border-radius: 4px;
        background-color: rgba(250, 204, 21, 0.24);
        border: 1px solid rgba(250, 204, 21, 0.75);
        pointer-events: none;
        z-index: 1;
        box-sizing: border-box;
    }

    .suitability-seg {
        flex: 1;
        height: 100%;
    }

    .suitability-seg.optimal {
        background-color: #4ade80;
    }

    .suitability-seg.marginal {
        background-color: rgba(96, 165, 250, 0.65);
    }

    .suitability-seg.nogo {
        background-color: rgba(234, 234, 234, 0.08);
    }

    .suitability-seg.neutral {
        background-color: rgba(234, 234, 234, 0.18);
    }

    .date-slider {
        -webkit-appearance: none;
        appearance: none;
        width: 100%;
        height: 16px;
        background: transparent;
        margin: 0;
        cursor: pointer;
        position: relative;
        z-index: 2;
    }

    .date-slider::-webkit-slider-thumb {
        -webkit-appearance: none;
        appearance: none;
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #ffffff;
        border: 2px solid #070707;
        box-shadow: 0 0 0 1.5px #eaeaea;
        cursor: grab;
    }

    .date-slider::-moz-range-thumb {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        background: #ffffff;
        border: 2px solid #070707;
        box-shadow: 0 0 0 1.5px #eaeaea;
        cursor: grab;
    }

    .slider-endpoints {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.66rem;
        opacity: 0.65;
    }

    .legend-inline {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
    }

    .legend-inline .dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        margin-left: 0.3rem;
    }

    .dot.optimal {
        background-color: #4ade80;
    }

    .dot.marginal {
        background-color: #60a5fa;
    }

    .dot.span {
        background-color: #facc15;
    }

    .timeline-footer {
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
        padding-top: 0.35rem;
        border-top: 1px solid rgba(234, 234, 234, 0.1);
    }

    .recommended-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.4rem;
    }

    .rec-heading {
        font-size: 0.7rem;
        opacity: 0.7;
    }

    .rec-chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
    }

    .rec-chip {
        background-color: rgba(34, 197, 94, 0.14);
        color: #86efac;
        border: 1px solid rgba(34, 197, 94, 0.35);
        border-radius: 999px;
        padding: 0.15rem 0.55rem;
        font-family: inherit;
        font-size: 0.7rem;
        font-weight: 500;
        cursor: pointer;
        transition: background-color 0.15s ease;
    }

    .rec-chip:hover {
        background-color: rgba(34, 197, 94, 0.25);
    }

    .rec-chip.active {
        background-color: #4ade80;
        color: #070707;
        font-weight: 600;
    }

    .no-rec {
        font-size: 0.7rem;
        opacity: 0.55;
    }

    .site-verdicts {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
    }

    .verdict-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background-color: rgba(234, 234, 234, 0.06);
        border: 1px solid rgba(234, 234, 234, 0.1);
        border-radius: 6px;
        padding: 0.2rem 0.5rem;
        font-size: 0.7rem;
    }

    .verdict-site {
        font-weight: 600;
    }

    .verdict-detail {
        opacity: 0.75;
    }

    .sun-dur-tag {
        font-weight: 600;
        color: #fde047;
        background-color: rgba(250, 204, 21, 0.12);
        border: 1px solid rgba(250, 204, 21, 0.28);
        border-radius: 4px;
        padding: 0.05rem 0.35rem;
        font-variant-numeric: tabular-nums;
    }

    .sun-dur-tag.loading {
        opacity: 0.65;
    }

    .sun-dur-tag.err {
        color: #fca5a5;
        background-color: rgba(239, 68, 68, 0.12);
        border-color: rgba(239, 68, 68, 0.28);
    }

    .verdict-badge {
        font-size: 0.65rem;
        font-weight: 600;
        padding: 0.08rem 0.4rem;
        border-radius: 999px;
    }

    .verdict-badge.optimal {
        background-color: rgba(34, 197, 94, 0.22);
        color: #86efac;
    }

    .verdict-badge.marginal {
        background-color: rgba(234, 179, 8, 0.2);
        color: #fde047;
    }

    .verdict-badge.no-go {
        background-color: rgba(239, 68, 68, 0.2);
        color: #fca5a5;
    }
</style>