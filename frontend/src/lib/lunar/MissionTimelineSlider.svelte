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
    export let isCompact = false;
    export let isOpen = true;
    export let isLoadingData = false;
    export let onChangeTime: (ms: number) => void;
    export let onChangeDuration: (hours: number) => void;
    export let onChangeMonth: (year: number, monthIndex: number) => void;
    export let onAutoPickBest: (() => void) | undefined = undefined;

    const STEP_MS = 1 * 3600 * 1000;
    const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const DURATION_PRESETS = [
        { label: '24h', hours: 24 },
        { label: '3d', hours: 72 },
        { label: '7d', hours: 168 },
        { label: '14d', hours: 336 },
        { label: '28d', hours: 672 }
    ];

    let isPlaying = false;
    let playInterval: ReturnType<typeof setInterval> | undefined = undefined;

    $: activeDateObj = new Date(startMs);$: activeYear = activeDateObj.getUTCFullYear();
    $: activeMonthIndex = activeDateObj.getUTCMonth();$: monthInputValue = `${activeYear}-${String(activeMonthIndex + 1).padStart(2, '0')}`;
    $: activeMonthLabel = `${MONTH_SHORT[activeMonthIndex]} ${activeYear}`;

    $: durationMs = Math.max(1, missionDurationHours) * 3600 * 1000;
    $: trackEndMs = endMs + durationMs;
    $: safeTimeMs = Math.max(startMs, Math.min(endMs, selectedTimeMs));$: missionEndMs = safeTimeMs + durationMs;

    $: dockWidthCss = isCompact
        ? `min(690px, calc(100vw - ${rightInsetPx}px - 44px))`
        : `calc(100vw - ${rightInsetPx}px - ${rightInsetPx > 0 ? 44 : 40}px)`;

    $: recommendedWindows = findRecommendedLandingWindows(
        targetSites,
        startMs,
        endMs,
        missionDurationHours
    );

    $: missionSpanOverlay = (() => {
        const span = Math.max(1, trackEndMs - startMs);
        const leftPct = Math.max(0, Math.min(100, ((safeTimeMs - startMs) / span) * 100));
        const rightPct = Math.max(leftPct, Math.min(100, ((missionEndMs - startMs) / span) * 100));
        const monthBoundaryPct = Math.max(0, Math.min(100, ((endMs - startMs) / span) * 100));
        return {
            leftPct,
            widthPct: Math.max(0.8, rightPct - leftPct),
            monthBoundaryPct
        };
    })();

    $: trackSegments = (() => {
        const count = 84;
        if (targetSites.length === 0 || trackEndMs <= startMs) {
            return Array.from({ length: count }, () => 'neutral');
        }

        const span = trackEndMs - startMs;
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

    function toggleTimelineOpen() {
        if (isOpen) {
            stopPlayback();
        }
        isOpen = !isOpen;
    }

    function shiftMonth(delta: number) {
        stopPlayback();
        const shifted = new Date(Date.UTC(activeYear, activeMonthIndex + delta, 1));
        onChangeMonth(shifted.getUTCFullYear(), shifted.getUTCMonth());
    }

    function handleMonthInput(e: Event) {
        const raw = (e.currentTarget as HTMLInputElement).value.trim();
        const match = raw.match(/^(\d{4})-(\d{2})$/);
        if (!match) return;
        const year = Number(match[1]);
        const month = Number(match[2]) - 1;
        if (year >= 1970 && year <= 2100 && month >= 0 && month <= 11) {
            stopPlayback();
            onChangeMonth(year, month);
        }
    }

    function handleRangeInput(e: Event) {
        stopPlayback();
        const rawVal = Number((e.currentTarget as HTMLInputElement).value);
        const clamped = Math.max(startMs, Math.min(endMs, rawVal));
        (e.currentTarget as HTMLInputElement).value = String(clamped);
        onChangeTime(clamped);
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

{#if isOpen}
    <div
            class="timeline-dock"
            style="width: {dockWidthCss};"
    >
        <div class="timeline-header">
            <div class="timeline-title-group">
                <span class="timeline-label">Landing</span>
                <strong class="timeline-current-date">{formatFullUtc(safeTimeMs)}</strong>
                <span class="mission-end-hint" title="Mission End ({formatDurationHours(missionDurationHours)})">
                    → {formatShortUtc(missionEndMs)} UTC
                </span>

                {#if isLoadingData}
                    <span class="loading-pill" role="status" aria-live="polite">
                        <span class="spinner" aria-hidden="true"></span>
                        Loading data...
                    </span>
                {/if}
            </div>

            <div class="timeline-controls">
                {#if targetSites.length > 0 && recommendedWindows.length > 0}
                    <button
                            class="step-btn best-btn"
                            on:click={() => {
                            stopPlayback();
                            if (onAutoPickBest) {
                                onAutoPickBest();
                            } else {
                                jumpToWindow(recommendedWindows[0].peakMs);
                            }
                        }}
                            title="Jump to highest-scoring landing date on timeline"
                    >
                        ★ Auto-Best
                    </button>
                {/if}
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
                <button
                        type="button"
                        class="step-btn collapse-timeline-btn"
                        on:click={toggleTimelineOpen}
                        aria-expanded={true}
                        aria-label="Hide mission timeline"
                        title="Hide mission timeline"
                >
                    ▾
                </button>
            </div>
        </div>

        <!-- Launch Month & Mission Duration Selector Bar -->
        <div class="duration-row">
            <div class="month-switcher" title="Select launch month/year">
                <button
                        class="step-btn month-nav-btn"
                        on:click={() => shiftMonth(-1)}
                        aria-label="Previous launch month"
                        title="Previous launch month"
                >
                    ◀
                </button>
                <label class="month-input-wrap">
                    <input
                            class="month-input"
                            type="month"
                            value={monthInputValue}
                            on:change={handleMonthInput}
                            aria-label="Select launch year and month ({activeMonthLabel})"
                    />
                </label>
                <button
                        class="step-btn month-nav-btn"
                        on:click={() => shiftMonth(1)}
                        aria-label="Next launch month"
                        title="Next launch month"
                >
                    ▶
                </button>
            </div>

            <span class="row-divider" aria-hidden="true"></span>

            <span class="duration-label">Duration:</span>
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

        <!-- Track with full-timeline suitability heat-map bar, spillover zone & active mission span overlay -->
        <div class="slider-track-wrapper">
            <div class="suitability-bar" aria-hidden="true">
                {#each trackSegments as seg}
                    <span class="suitability-seg {seg}"></span>
                {/each}
            </div>

            {#if missionSpanOverlay.monthBoundaryPct < 100}
                <div
                        class="spillover-zone"
                        aria-hidden="true"
                        style="left: {missionSpanOverlay.monthBoundaryPct}%; right: 0;"
                        title="Next-month mission spillover region"
                ></div>
                <div
                        class="month-boundary-tick"
                        aria-hidden="true"
                        style="left: {missionSpanOverlay.monthBoundaryPct}%;"
                ></div>
            {/if}

            <div
                    class="mission-span-overlay"
                    aria-hidden="true"
                    style="left: {missionSpanOverlay.leftPct}%; width: {missionSpanOverlay.widthPct}%;"
            ></div>

            <input
                    class="date-slider"
                    type="range"
                    min={startMs}
                    max={trackEndMs}
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
                    <span class="cutoff-hint">· Cutoff {formatShortDateOnlyUtc(endMs)}</span>
                </span>
                <span>{formatShortDateOnlyUtc(trackEndMs)}</span>
            </div>
        </div>

        <!-- Recommended Landing Dates & Live Evaluation -->
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
                                        title="Jump to optimal start window ({win.label} · Score ~{win.avgScore})"
                                >
                                    ★ {win.label}
                                </button>
                            {/each}
                        </div>
                    {:else}
                        <span class="no-rec">Evaluating timeline...</span>
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
                            {#if item.site.missionSunlight}
                                <span
                                        class="sun-dur-tag"
                                        title="Sunlit hours during {formatDurationHours(missionDurationHours)} mission"
                                >
                                    ☀ {item.site.missionSunlight.sunlitHours.toFixed(1)}h ({item.site.missionSunlight.sunlitPercentage.toFixed(0)}%)
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
{:else}
    <button
            type="button"
            class="timeline-collapsed-pill"
            on:click={toggleTimelineOpen}
            aria-expanded={false}
            aria-label="Show mission timeline"
            title="Show mission timeline"
    >
        <span class="pill-arrow">▲</span>
        <span class="pill-title">Timeline</span>
        <span class="pill-sep">·</span>
        <span class="pill-date">{formatFullUtc(safeTimeMs)}</span>
        {#if isLoadingData}
            <span class="spinner" aria-hidden="true"></span>
        {/if}
    </button>
{/if}

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

    .timeline-collapsed-pill {
        position: absolute;
        bottom: 20px;
        left: 20px;
        z-index: 10;
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        background-color: rgba(14, 14, 18, 0.9);
        backdrop-filter: blur(8px);
        color: #eaeaea;
        border: 1px solid rgba(234, 234, 234, 0.28);
        border-radius: 10px;
        padding: 0.42rem 0.8rem;
        font-family: inherit;
        font-size: 0.75rem;
        cursor: pointer;
        transition: background-color 0.15s ease, border-color 0.15s ease;
    }

    .timeline-collapsed-pill:hover {
        background-color: rgba(34, 34, 42, 0.95);
        border-color: rgba(234, 234, 234, 0.55);
    }

    .pill-arrow {
        font-size: 0.65rem;
        opacity: 0.85;
    }

    .pill-title {
        font-weight: 600;
        color: #ffffff;
    }

    .pill-sep {
        opacity: 0.45;
    }

    .pill-date {
        opacity: 0.85;
        font-variant-numeric: tabular-nums;
    }

    .timeline-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
    }

    .timeline-title-group {
        display: flex;
        align-items: center;
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

    .loading-pill {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.68rem;
        font-weight: 500;
        color: #93c5fd;
        background-color: rgba(59, 130, 246, 0.16);
        border: 1px solid rgba(96, 165, 250, 0.35);
        border-radius: 999px;
        padding: 0.1rem 0.5rem;
    }

    .spinner {
        width: 10px;
        height: 10px;
        border: 1.8px solid rgba(147, 197, 253, 0.3);
        border-top-color: #93c5fd;
        border-radius: 50%;
        animation: spin 0.75s linear infinite;
    }

    @keyframes spin {
        to {
            transform: rotate(360deg);
        }
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

    .collapse-timeline-btn {
        margin-left: 0.15rem;
        padding: 0.18rem 0.42rem;
    }

    .best-btn {
        background-color: rgba(34, 197, 94, 0.16);
        border-color: rgba(34, 197, 94, 0.4);
        color: #86efac;
        font-weight: 500;
    }

    .best-btn:hover:not(:disabled) {
        background-color: rgba(34, 197, 94, 0.28);
    }

    .play-btn {
        min-width: 26px;
        text-align: center;
    }

    .duration-row {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.38rem;
        padding: 0.22rem 0;
    }

    .month-switcher {
        display: inline-flex;
        align-items: center;
        gap: 0.22rem;
    }

    .month-nav-btn {
        padding: 0.16rem 0.36rem;
        font-size: 0.64rem;
        line-height: 1.2;
    }

    .month-input-wrap {
        display: inline-flex;
        align-items: center;
    }

    .month-input {
        background-color: #0d0d0d;
        color: #fff;
        border: 1px solid rgba(234, 234, 234, 0.24);
        border-radius: 6px;
        padding: 0.13rem 0.4rem;
        font-family: inherit;
        font-size: 0.7rem;
        font-weight: 500;
        color-scheme: dark;
        cursor: pointer;
    }

    .month-input:focus {
        outline: none;
        border-color: #60a5fa;
    }

    .row-divider {
        width: 1px;
        height: 14px;
        background-color: rgba(234, 234, 234, 0.16);
        margin: 0 0.1rem;
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
        gap: 0.25rem;
    }

    .dur-chip {
        background-color: rgba(234, 234, 234, 0.08);
        color: rgba(234, 234, 234, 0.85);
        border: 1px solid rgba(234, 234, 234, 0.16);
        border-radius: 6px;
        padding: 0.15rem 0.42rem;
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
        width: 48px;
        background-color: #0d0d0d;
        color: #fff;
        border: 1px solid rgba(234, 234, 234, 0.24);
        border-radius: 5px;
        padding: 0.15rem 0.3rem;
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

    .spillover-zone {
        position: absolute;
        top: 7px;
        height: 6px;
        border-top-right-radius: 999px;
        border-bottom-right-radius: 999px;
        background: repeating-linear-gradient(
                -45deg,
                rgba(7, 7, 7, 0.32),
                rgba(7, 7, 7, 0.32) 3px,
                rgba(234, 234, 234, 0.08) 3px,
                rgba(234, 234, 234, 0.08) 6px
        );
        pointer-events: none;
        z-index: 1;
    }

    .month-boundary-tick {
        position: absolute;
        top: 4px;
        width: 1.5px;
        height: 12px;
        background-color: rgba(234, 234, 234, 0.65);
        pointer-events: none;
        z-index: 1;
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

    .cutoff-hint {
        opacity: 0.85;
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