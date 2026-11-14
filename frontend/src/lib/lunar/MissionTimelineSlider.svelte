<script lang="ts">
    import { onDestroy } from 'svelte';
    import type { SelectedSite } from './types';
    import {
        evaluateSiteAtTimestamp,
        findRecommendedLandingWindows,
        formatFullUtc,
        formatShortDateOnlyUtc
    } from './telemetry';

    export let startMs: number;
    export let endMs: number;
    export let selectedTimeMs: number;
    export let targetSites: SelectedSite[] = [];
    export let rightInsetPx = 0;
    export let onChangeTime: (ms: number) => void;

    const STEP_MS = 6 * 3600 * 1000; // 6-hour increments

    let isPlaying = false;
    let playInterval: ReturnType<typeof setInterval> | undefined = undefined;

    $: safeTimeMs = Math.max(startMs, Math.min(endMs, selectedTimeMs));
    $: recommendedWindows = findRecommendedLandingWindows(targetSites, startMs, endMs);

    // Build 62 visual segments across the slider track showing landing viability per date
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
        style="width: min(640px, calc(100vw - {rightInsetPx}px - 44px));"
>
    <div class="timeline-header">
        <div class="timeline-title-group">
            <span class="timeline-label">Landing Date</span>
            <strong class="timeline-current-date">{formatFullUtc(safeTimeMs)}</strong>
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

    <!-- Track with suitability heat-map bar underneath range input -->
    <div class="slider-track-wrapper">
        <div class="suitability-bar" aria-hidden="true">
            {#each trackSegments as seg}
                <span class="suitability-seg {seg}"></span>
            {/each}
        </div>

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
                <i class="dot nogo"></i> No-Go
            </span>
            <span>{formatShortDateOnlyUtc(endMs)}</span>
        </div>
    </div>

    <!-- Recommended Landing Dates & Live Evaluation at Selected Timestamp -->
    {#if targetSites.length > 0}
        <div class="timeline-footer">
            <div class="recommended-row">
                <span class="rec-heading">
                    {targetSites.length > 1 ? 'Joint Best Dates:' : 'Best Dates:'}
                </span>
                {#if recommendedWindows.length > 0}
                    <div class="rec-chips">
                        {#each recommendedWindows as win}
                            {@const isInside = safeTimeMs >= win.startMs && safeTimeMs <= win.endMs}
                            <button
                                    class="rec-chip"
                                    class:active={isInside}
                                    on:click={() => jumpToWindow(win.peakMs)}
                                    title="Jump to optimal window ({win.label})"
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
        background-color: rgba(7, 7, 7, 0.86);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(234, 234, 234, 0.16);
        border-radius: 12px;
        padding: 0.65rem 0.85rem;
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
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
        gap: 0.5rem;
    }

    .timeline-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.65;
    }

    .timeline-current-date {
        font-size: 0.84rem;
        font-weight: 600;
        color: #fff;
        font-variant-numeric: tabular-nums;
    }

    .timeline-controls {
        display: flex;
        align-items: center;
        gap: 0.3rem;
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

    .dot.nogo {
        background-color: rgba(234, 234, 234, 0.25);
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