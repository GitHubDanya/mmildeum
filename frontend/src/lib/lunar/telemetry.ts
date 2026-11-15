import type {
    DateEvaluation,
    EarthEphemeris,
    FetchDataResponse,
    MissionSunlightMetrics,
    RecommendedDateWindow,
    RescorePayload,
    RescoreResult,
    ScoringBlock,
    ScoringMetrics,
    SelectedSite,
    VisibilityWindow,
    WindowStats
} from './types';

export const HOURS_LABELS = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}h`);
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export const DEFAULT_TIMELINE_START_MS = Date.UTC(2026, 9, 1, 0, 0);
export const DEFAULT_TIMELINE_END_MS = Date.UTC(2026, 9, 31, 23, 0);
export const MAX_MISSION_PAD_MS = 30 * 24 * 3600 * 1000;

const SYNODIC_MONTH_MS = 29.530588853 * 24 * 3600 * 1000;
const J2000_NEW_MOON_MS = Date.UTC(2000, 0, 6, 18, 14, 0);
const J2000_EPOCH_MS = Date.UTC(2000, 0, 1, 12, 0, 0);

const MONTH_INDEX: Record<string, number> = {
    Jan: 0,
    Feb: 1,
    Mar: 2,
    Apr: 3,
    May: 4,
    Jun: 5,
    Jul: 6,
    Aug: 7,
    Sep: 8,
    Oct: 9,
    Nov: 10,
    Dec: 11
};

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function deg2rad(deg: number): number {
    return (deg * Math.PI) / 180;
}

function normalizeDeg180(deg: number): number {
    return (((deg + 180) % 360) + 360) % 360 - 180;
}

function isFiniteNum(val: unknown): val is number {
    return typeof val === 'number' && Number.isFinite(val);
}

export function getMonthBounds(year: number, monthIndex: number): { startMs: number; endMs: number } {
    return {
        startMs: Date.UTC(year, monthIndex, 1, 0, 0),
        endMs: Date.UTC(year, monthIndex + 1, 0, 23, 0)
    };
}

export function getScoreClass(score: number): string {
    if (score < 25) return 'score-red';
    if (score < 50) return 'score-yellow';
    if (score < 75) return 'score-green';
    return 'score-blue';
}

export function getScoreHexColor(score: number): string {
    if (score < 25) return '#f87171';
    if (score < 50) return '#facc15';
    if (score < 75) return '#4ade80';
    return '#60a5fa';
}

export function parseLunarTimestamp(raw: string): number | null {
    const trimmed = raw.trim();
    const match = trimmed.match(/^(\d{4})-([A-Za-z]{3})-(\d{2})\s+(\d{2}):(\d{2})$/);
    if (match) {
        const year = Number(match[1]);
        const month = MONTH_INDEX[match[2]];
        const day = Number(match[3]);
        const hour = Number(match[4]);
        const minute = Number(match[5]);
        if (month !== undefined) {
            return Date.UTC(year, month, day, hour, minute);
        }
    }

    if (/^\d{4}-\d{2}-\d{2}T/.test(trimmed)) {
        const isoParsed = Date.parse(trimmed);
        if (Number.isFinite(isoParsed)) return isoParsed;
    }

    const fallback = Date.parse(`${trimmed} UTC`);
    return Number.isFinite(fallback) ? fallback : null;
}

export function formatShortUtc(ms: number): string {
    const d = new Date(ms);
    const mon = MONTH_NAMES[d.getUTCMonth()];
    const day = String(d.getUTCDate()).padStart(2, '0');
    const hr = String(d.getUTCHours()).padStart(2, '0');
    const min = String(d.getUTCMinutes()).padStart(2, '0');
    return `${mon} ${day} ${hr}:${min}`;
}

export function formatFullUtc(ms: number): string {
    const d = new Date(ms);
    const year = d.getUTCFullYear();
    return `${year}-${formatShortUtc(ms)} UTC`;
}

export function formatShortDateOnlyUtc(ms: number): string {
    const d = new Date(ms);
    const mon = MONTH_NAMES[d.getUTCMonth()];
    const day = String(d.getUTCDate()).padStart(2, '0');
    return `${mon} ${day}`;
}

export function formatDurationHours(hours: number): string {
    if (!Number.isFinite(hours) || hours <= 0) return '0h';
    if (hours < 48) {
        return `${Number(hours.toFixed(1))}h`;
    }
    const days = hours / 24;
    return Number.isInteger(days) ? `${days}d (${hours}h)` : `${days.toFixed(1)}d (${Math.round(hours)}h)`;
}

export function formatWindowRange(win: VisibilityWindow): string {
    const startMs = parseLunarTimestamp(win.start);
    const endMs = parseLunarTimestamp(win.end);
    if (startMs !== null && endMs !== null) {
        return `${formatShortUtc(startMs)} → ${formatShortUtc(endMs)}`;
    }
    return `${win.start} → ${win.end}`;
}

export function clipWindowsToInterval(
    windows: VisibilityWindow[],
    startMs: number,
    endMs: number
): VisibilityWindow[] {
    if (!Array.isArray(windows) || windows.length === 0 || endMs <= startMs) return [];

    const result: VisibilityWindow[] = [];
    for (const w of windows) {
        const s = parseLunarTimestamp(w.start);
        const e = parseLunarTimestamp(w.end);
        if (s === null || e === null) continue;
        const clippedStart = Math.max(startMs, s);
        const clippedEnd = Math.min(endMs, e);
        if (clippedEnd > clippedStart) {
            result.push({
                start: new Date(clippedStart).toISOString(),
                end: new Date(clippedEnd).toISOString()
            });
        }
    }
    return result;
}

export function rescoreFromPayload(
    payload: RescorePayload,
    newStartIso: string,
    newEndIso: string,
    weights: [number, number, number, number, number] = [0.25, 0.20, 0.15, 0.10, 0.30]
): RescoreResult {
    const t0 = parseLunarTimestamp(newStartIso) ?? Date.parse(newStartIso);
    const t1 = parseLunarTimestamp(newEndIso) ?? Date.parse(newEndIso);
    const durationMs = Math.max(1, t1 - t0);
    const durationHours = durationMs / 3600000;

    function computeWindowStats(windows: VisibilityWindow[] | undefined | null): WindowStats {
        if (!Array.isArray(windows) || windows.length === 0) {
            return { fraction: 0, maxOutageHours: durationHours };
        }

        const clipped = windows
            .map((w) => [
                Math.max(t0, parseLunarTimestamp(w.start) ?? Date.parse(w.start)),
                Math.min(t1, parseLunarTimestamp(w.end) ?? Date.parse(w.end))
            ] as [number, number])
            .filter(([s, e]) => Number.isFinite(s) && Number.isFinite(e) && e > s)
            .sort((a, b) => a[0] - b[0]);

        if (clipped.length === 0) return { fraction: 0, maxOutageHours: durationHours };

        let activeMs = 0;
        let maxGapMs = clipped[0][0] - t0;

        for (let i = 0; i < clipped.length; i++) {
            activeMs += clipped[i][1] - clipped[i][0];
            if (i > 0) {
                maxGapMs = Math.max(maxGapMs, clipped[i][0] - clipped[i - 1][1]);
            }
        }
        maxGapMs = Math.max(maxGapMs, t1 - clipped[clipped.length - 1][1]);

        return {
            fraction: activeMs / durationMs,
            maxOutageHours: maxGapMs / 3600000
        };
    }

    const sun = computeWindowStats(payload.sunlight_windows);
    const earth = computeWindowStats(payload.visibility_windows);

    const rawSlopeSuitability =
        payload.normalized_metrics?.slope_suitability ??
        payload.scoring?.normalized_metrics?.slope_suitability;
    const slopeSuitability = isFiniteNum(rawSlopeSuitability) ? rawSlopeSuitability : 0;

    const z: [number, number, number, number, number] = [
        sun.fraction,
        Math.exp(-sun.maxOutageHours / 24.0),
        earth.fraction,
        Math.exp(-earth.maxOutageHours / 120.0),
        slopeSuitability
    ];

    let dPlusSq = 0;
    let dMinusSq = 0;
    for (let i = 0; i < 5; i++) {
        dPlusSq += weights[i] * Math.pow(1 - z[i], 2);
        dMinusSq += weights[i] * Math.pow(z[i], 2);
    }

    const dPlus = Math.sqrt(dPlusSq);
    const dMinus = Math.sqrt(dMinusSq);
    const score = dPlus + dMinus === 0 ? 0 : (100 * dMinus) / (dPlus + dMinus);

    return { score, metrics: { sun, earth }, normalized: z };
}

export function applyFallbackRescore(
    site: SelectedSite,
    startMs: number,
    durationHours: number
): SelectedSite {
    const safeHours = Math.max(1, durationHours);
    const endMs = startMs + safeHours * 3600 * 1000;
    const startIso = new Date(startMs).toISOString();
    const endIso = new Date(endMs).toISOString();

    const fullSunWindows =
        site.timelineSunlightWindows.length > 0
            ? site.timelineSunlightWindows
            : site.sunlightWindows;
    const fullVisWindows =
        site.timelineVisibilityWindows.length > 0
            ? site.timelineVisibilityWindows
            : site.visibilityWindows;

    const rescored = rescoreFromPayload(
        {
            sunlight_windows: fullSunWindows,
            visibility_windows: fullVisWindows,
            normalized_metrics: {
                slope_suitability: site.slopeSuitability
            }
        },
        startIso,
        endIso
    );

    const sunlitHours = Number((rescored.metrics.sun.fraction * safeHours).toFixed(2));
    const sunlitPercentage = Number((rescored.metrics.sun.fraction * 100).toFixed(1));

    const updatedScoringMetrics: ScoringMetrics = {
        sunlight_fraction: rescored.metrics.sun.fraction,
        longest_darkness_hours: Number(rescored.metrics.sun.maxOutageHours.toFixed(2)),
        earth_visibility_fraction: rescored.metrics.earth.fraction,
        longest_earth_blackout_hours: Number(rescored.metrics.earth.maxOutageHours.toFixed(2)),
        slope_p95_degrees: site.scoringMetrics?.slope_p95_degrees ?? null
    };

    const updatedScoringBlock: ScoringBlock = {
        score: rescored.score,
        feasible: site.scoringBlock?.feasible ?? null,
        failed_constraints: site.scoringBlock?.failed_constraints ?? [],
        normalized_metrics: {
            sunlight: rescored.normalized[0],
            darkness_endurance: rescored.normalized[1],
            earth_visibility: rescored.normalized[2],
            communication_endurance: rescored.normalized[3],
            slope_suitability: rescored.normalized[4]
        },
        model_version: site.scoringBlock?.model_version,
        data_quality: site.scoringBlock?.data_quality,
        missing_metrics: site.scoringBlock?.missing_metrics,
        unavailable_sources: site.scoringBlock?.unavailable_sources,
        metadata: site.scoringBlock?.metadata
    };

    return {
        ...site,
        score: Number(rescored.score.toFixed(1)),
        rescoreResult: rescored,
        scoringMetrics: updatedScoringMetrics,
        scoringBlock: updatedScoringBlock,
        sunlightWindows: clipWindowsToInterval(fullSunWindows, startMs, endMs),
        visibilityWindows: clipWindowsToInterval(fullVisWindows, startMs, endMs),
        visibilityCoveragePct: Number((rescored.metrics.earth.fraction * 100).toFixed(1)),
        missionSunlight: {
            startIso,
            endIso,
            missionHours: safeHours,
            sunlitHours,
            sunlitPercentage,
            stepMinutes: site.missionSunlight?.stepMinutes ?? 60,
            sampleCount: safeHours,
            sunlitSampleCount: Math.round(sunlitHours),
            isFallback: true
        }
    };
}

export function computeEarthPositionFromMoon(timestampMs: number): EarthEphemeris {
    const d = (timestampMs - J2000_EPOCH_MS) / 86400000;

    const Mm = deg2rad(134.9633964 + 13.06499295 * d);
    const F = deg2rad(93.272095 + 13.22935024 * d);
    const Ms = deg2rad(357.5291092 + 0.98560028 * d);
    const D = deg2rad(297.8501921 + 12.19074912 * d);

    const subEarthLonDeg =
        -6.289 * Math.sin(Mm) -
        1.274 * Math.sin(2 * D - Mm) -
        0.658 * Math.sin(2 * D) -
        0.214 * Math.sin(2 * Mm) +
        0.186 * Math.sin(Ms);

    const subEarthLatDeg =
        -6.688 * Math.sin(F) -
        0.28 * Math.sin(Mm + F) -
        0.28 * Math.sin(Mm - F);

    const distanceKm =
        385000.56 -
        20905.355 * Math.cos(Mm) -
        3699.111 * Math.cos(2 * D - Mm) -
        2955.968 * Math.cos(2 * D) -
        569.925 * Math.cos(2 * Mm);

    const sunLonDeg = normalizeDeg180(180 - (D * 180) / Math.PI + subEarthLonDeg);
    const sunLatDeg = -1.542 * Math.sin(F - D);

    return {
        subEarthLatDeg: Number(subEarthLatDeg.toFixed(2)),
        subEarthLonDeg: Number(subEarthLonDeg.toFixed(2)),
        distanceKm: Math.round(distanceKm),
        distanceM: distanceKm * 1000,
        sunLonDeg,
        sunLatDeg
    };
}

export function getTimelineBounds(sites: SelectedSite[]): { startMs: number; endMs: number } {
    const allTimestamps: number[] = [];

    for (const site of sites) {
        const visList =
            site.timelineVisibilityWindows.length > 0
                ? site.timelineVisibilityWindows
                : site.visibilityWindows;
        for (const win of visList) {
            const s = parseLunarTimestamp(win.start);
            const e = parseLunarTimestamp(win.end);
            if (s !== null) allTimestamps.push(s);
            if (e !== null) allTimestamps.push(e);
        }

        const sunList =
            site.timelineSunlightWindows.length > 0
                ? site.timelineSunlightWindows
                : site.sunlightWindows;
        for (const win of sunList) {
            const s = parseLunarTimestamp(win.start);
            const e = parseLunarTimestamp(win.end);
            if (s !== null) allTimestamps.push(s);
            if (e !== null) allTimestamps.push(e);
        }
    }

    if (allTimestamps.length === 0) {
        return {
            startMs: DEFAULT_TIMELINE_START_MS,
            endMs: DEFAULT_TIMELINE_END_MS
        };
    }

    const minDate = new Date(Math.min(...allTimestamps, DEFAULT_TIMELINE_START_MS));
    const maxDate = new Date(
        Math.max(...allTimestamps.map((t) => t - MAX_MISSION_PAD_MS), DEFAULT_TIMELINE_END_MS)
    );

    return {
        startMs: Date.UTC(minDate.getUTCFullYear(), minDate.getUTCMonth(), 1, 0, 0),
        endMs: Date.UTC(maxDate.getUTCFullYear(), maxDate.getUTCMonth() + 1, 0, 23, 0)
    };
}

export function evaluateSiteAtTimestamp(site: SelectedSite, timestampMs: number): DateEvaluation {
    const visSource =
        site.timelineVisibilityWindows.length > 0
            ? site.timelineVisibilityWindows
            : site.visibilityWindows;

    const parsedVisWindows = visSource
        .map((w) => ({
            startMs: parseLunarTimestamp(w.start),
            endMs: parseLunarTimestamp(w.end)
        }))
        .filter((w): w is { startMs: number; endMs: number } => w.startMs !== null && w.endMs !== null);

    const hasVisibilityData = site.hasRealVisibility;
    const isEarthVisible = hasVisibilityData
        ? parsedVisWindows.some((w) => timestampMs >= w.startMs && timestampMs <= w.endMs)
        : Math.cos((site.rawLon * Math.PI) / 180) > -0.15;

    const rawPhase = ((timestampMs - J2000_NEW_MOON_MS) % SYNODIC_MONTH_MS) / SYNODIC_MONTH_MS;
    const phase = rawPhase < 0 ? rawPhase + 1 : rawPhase;

    let subsolarLon = (0.5 - phase) * 360;
    while (subsolarLon > 180) subsolarLon -= 360;
    while (subsolarLon < -180) subsolarLon += 360;

    const hourAngleRad = ((site.rawLon - subsolarLon) * Math.PI) / 180;
    const latRad = (site.rawLat * Math.PI) / 180;
    const cosZ = Math.cos(latRad) * Math.cos(hourAngleRad);

    const geometricMaxDeg = Math.max(5, Math.acos(Math.sin(Math.abs(latRad))) * (180 / Math.PI));
    const peakAngleDeg =
        site.daytimeAvgSunAngle !== null && site.daytimeAvgSunAngle > 0
            ? Math.min(89, site.daytimeAvgSunAngle / (2 / Math.PI))
            : geometricMaxDeg;

    const sunAngleDeg = cosZ > 0 ? Number((cosZ * peakAngleDeg).toFixed(1)) : 0;

    const sunSource =
        site.timelineSunlightWindows.length > 0
            ? site.timelineSunlightWindows
            : site.sunlightWindows;

    const parsedSunWindows = site.hasRealSunlightWindows
        ? sunSource
            .map((w) => ({
                startMs: parseLunarTimestamp(w.start),
                endMs: parseLunarTimestamp(w.end)
            }))
            .filter(
                (w): w is { startMs: number; endMs: number } =>
                    w.startMs !== null && w.endMs !== null
            )
        : [];

    const isDaylight =
        parsedSunWindows.length > 0
            ? parsedSunWindows.some((w) => timestampMs >= w.startMs && timestampMs <= w.endMs)
            : sunAngleDeg > 1.0;

    let suitabilityScore = 0;
    if (isEarthVisible) suitabilityScore += 50;
    if (isDaylight) {
        suitabilityScore += 35;
        if (sunAngleDeg >= 5 && sunAngleDeg <= 35) {
            suitabilityScore += 15;
        } else {
            suitabilityScore += 7;
        }
    }

    const status: DateEvaluation['status'] =
        isEarthVisible && isDaylight ? 'Optimal' : isEarthVisible || isDaylight ? 'Marginal' : 'No-Go';

    return {
        isEarthVisible,
        hasVisibilityData,
        sunAngleDeg,
        isDaylight,
        suitabilityScore,
        status
    };
}

export function findRecommendedLandingWindows(
    targetSites: SelectedSite[],
    startMs: number,
    endMs: number,
    missionDurationHours = 72
): RecommendedDateWindow[] {
    if (targetSites.length === 0 || endMs <= startMs) return [];

    const stepMs = 3 * 3600 * 1000;
    const durationMs = Math.max(1, missionDurationHours) * 3600 * 1000;
    const samples: { t: number; score: number; allOptimal: boolean }[] = [];

    for (let t = startMs; t <= endMs; t += stepMs) {
        const startIso = new Date(t).toISOString();
        const endIso = new Date(t + durationMs).toISOString();

        let scoreSum = 0;
        let allSitesStrong = true;

        for (const site of targetSites) {
            const fullSunWindows =
                site.timelineSunlightWindows.length > 0
                    ? site.timelineSunlightWindows
                    : site.sunlightWindows;
            const fullVisWindows =
                site.timelineVisibilityWindows.length > 0
                    ? site.timelineVisibilityWindows
                    : site.visibilityWindows;

            if (site.hasRealVisibility || site.hasRealSunlightWindows) {
                const res = rescoreFromPayload(
                    {
                        sunlight_windows: fullSunWindows,
                        visibility_windows: fullVisWindows,
                        normalized_metrics: {
                            slope_suitability: site.slopeSuitability
                        }
                    },
                    startIso,
                    endIso
                );
                scoreSum += res.score;
                if (res.score < 58) {
                    allSitesStrong = false;
                }
            } else {
                const evalStart = evaluateSiteAtTimestamp(site, t);
                const evalMid = evaluateSiteAtTimestamp(site, t + durationMs * 0.5);
                const avg = (evalStart.suitabilityScore + evalMid.suitabilityScore) / 2;
                scoreSum += avg;
                if (evalStart.status !== 'Optimal' || evalMid.status !== 'Optimal') {
                    allSitesStrong = false;
                }
            }
        }

        const avgScore = scoreSum / targetSites.length;
        samples.push({ t, score: avgScore, allOptimal: allSitesStrong });
    }

    const collectSegments = (predicate: (s: (typeof samples)[number]) => boolean) => {
        const segments: RecommendedDateWindow[] = [];
        let runStart: number | null = null;
        let runEnd = 0;
        let peakMs = 0;
        let peakScore = -1;
        let scoreSum = 0;
        let count = 0;

        for (const s of samples) {
            if (predicate(s)) {
                if (runStart === null) {
                    runStart = s.t;
                    peakMs = s.t;
                    peakScore = s.score;
                    scoreSum = 0;
                    count = 0;
                }
                runEnd = s.t;
                scoreSum += s.score;
                count += 1;
                if (s.score > peakScore) {
                    peakScore = s.score;
                    peakMs = s.t;
                }
            } else if (runStart !== null) {
                const startLabel = formatShortDateOnlyUtc(runStart);
                const endLabel = formatShortDateOnlyUtc(runEnd);
                segments.push({
                    startMs: runStart,
                    endMs: runEnd,
                    peakMs,
                    label: startLabel === endLabel ? startLabel : `${startLabel} – ${endLabel}`,
                    avgScore: Math.round(scoreSum / Math.max(1, count)),
                    isJointOverlap: targetSites.length > 1
                });
                runStart = null;
            }
        }

        if (runStart !== null) {
            const startLabel = formatShortDateOnlyUtc(runStart);
            const endLabel = formatShortDateOnlyUtc(runEnd);
            segments.push({
                startMs: runStart,
                endMs: runEnd,
                peakMs,
                label: startLabel === endLabel ? startLabel : `${startLabel} – ${endLabel}`,
                avgScore: Math.round(scoreSum / Math.max(1, count)),
                isJointOverlap: targetSites.length > 1
            });
        }

        return segments;
    };

    let windows = collectSegments((s) => s.allOptimal);
    if (windows.length === 0) {
        windows = collectSegments((s) => s.score >= 45);
    }
    if (windows.length === 0 && samples.length > 0) {
        const bestSample = [...samples].sort((a, b) => b.score - a.score)[0];
        windows = [
            {
                startMs: bestSample.t,
                endMs: bestSample.t,
                peakMs: bestSample.t,
                label: formatShortDateOnlyUtc(bestSample.t),
                avgScore: Math.round(bestSample.score),
                isJointOverlap: targetSites.length > 1
            }
        ];
    }

    return windows
        .sort((a, b) => b.avgScore - a.avgScore || b.endMs - b.startMs - (a.endMs - a.startMs))
        .slice(0, 3);
}

export function buildVisibilityFromWindows(
    windows: VisibilityWindow[],
    overrideFraction?: number | null,
    fixedSpanStartMs?: number,
    fixedSpanEndMs?: number
) {
    const parsed = windows
        .map((w) => ({
            startMs: parseLunarTimestamp(w.start),
            endMs: parseLunarTimestamp(w.end)
        }))
        .filter((w): w is { startMs: number; endMs: number } => w.startMs !== null && w.endMs !== null && w.endMs >= w.startMs);

    const spanStartMs = fixedSpanStartMs ?? DEFAULT_TIMELINE_START_MS;
    const spanEndMs = fixedSpanEndMs ?? DEFAULT_TIMELINE_END_MS;
    const totalSpanMs = Math.max(spanEndMs - spanStartMs, 3600 * 1000);

    const stepMs = 6 * 3600 * 1000;
    const series: number[] = [];
    const labels: string[] = [];

    for (let t = spanStartMs; t <= spanEndMs; t += stepMs) {
        const isVisible = parsed.some((w) => t >= w.startMs && t <= w.endMs);
        series.push(isVisible ? 100 : 0);
        labels.push(formatShortUtc(t));
    }

    const totalVisibleMs = parsed.reduce((acc, w) => {
        const clampedStart = Math.max(spanStartMs, w.startMs);
        const clampedEnd = Math.min(spanEndMs, w.endMs);
        return acc + Math.max(0, clampedEnd - clampedStart);
    }, 0);

    const computedPct = Number(Math.min(100, (totalVisibleMs / totalSpanMs) * 100).toFixed(1));
    const coveragePct = isFiniteNum(overrideFraction)
        ? Number((overrideFraction * 100).toFixed(1))
        : computedPct;

    return { series, labels, coveragePct };
}

export function buildFallbackSeries(lat: number, lon: number, avgSunAngle: number | null) {
    const latFactor = Math.max(0.15, Math.cos((lat * Math.PI) / 180));
    const basePeakAngle = avgSunAngle !== null ? Math.min(88, avgSunAngle * 1.45) : 65 * latFactor;
    const phaseOffset = ((lon + 180) / 360) * Math.PI * 2;

    const sunlightAngle24h = Array.from({ length: 24 }, (_, h) => {
        const wave = Math.sin((h / 24) * Math.PI * 2 + phaseOffset);
        return Number(Math.max(0, wave * basePeakAngle).toFixed(1));
    });

    const sunlight24h = sunlightAngle24h.map((angle) =>
        angle > 2 ? Number(Math.min(100, 45 + (angle / Math.max(basePeakAngle, 1)) * 55).toFixed(1)) : 0
    );

    const earthVisibility24h = Array.from({ length: 24 }, (_, h) => {
        const libration = Math.cos((h / 24) * Math.PI * 2 - phaseOffset * 0.5);
        const nearSideBias = Math.cos((lon * Math.PI) / 180);
        const raw = (nearSideBias * 0.7 + libration * 0.3 + 0.5) * 100;
        return Number(Math.max(0, Math.min(100, raw)).toFixed(1));
    });

    return { sunlight24h, earthVisibility24h, sunlightAngle24h };
}

export async function fetchTimelineBlockTelemetry(
    lat: number,
    lon: number,
    blockStartMs: number,
    blockEndMs: number,
    stepMinutes = 60,
    signal?: AbortSignal,
    visibleSpanEndMs?: number
): Promise<Partial<SelectedSite>> {
    const startIso = new Date(blockStartMs).toISOString();
    const endIso = new Date(blockEndMs).toISOString();
    const clampedStep = Math.max(1, Math.min(1440, Math.round(stepMinutes)));

    const params = new URLSearchParams({
        lat: lat.toString(),
        long: lon.toString(),
        mission_start: startIso,
        mission_end: endIso,
        start: startIso,
        end: endIso,
        step_minutes: clampedStep.toString()
    });

    const response = await fetch(`${API_BASE_URL}/fetch-data?${params.toString()}`, {
        signal
    });
    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const errBody = await response.json();
            if (typeof errBody?.detail === 'string') {
                detail = errBody.detail;
            }
        } catch {
            // Ignore non-JSON error payload
        }
        throw new Error(detail);
    }

    const data: FetchDataResponse = await response.json();

    const fallback = buildFallbackSeries(lat, lon, data.daytime_avg_sun_angle ?? null);
    const hasRealSunSeries =
        Array.isArray(data.sunlight_24h) &&
        data.sunlight_24h.length === 24 &&
        Array.isArray(data.sunlight_angle_24h) &&
        data.sunlight_angle_24h.length === 24;

    const sunlight24h = hasRealSunSeries ? data.sunlight_24h! : fallback.sunlight24h;
    const sunlightAngle24h = hasRealSunSeries
        ? data.sunlight_angle_24h!
        : fallback.sunlightAngle24h;

    const hasRealVisibility = Array.isArray(data.visibility_windows);
    const timelineVisibilityWindows = hasRealVisibility ? data.visibility_windows! : [];

    const hasRealSunlightWindows = Array.isArray(data.sunlight_windows);
    const timelineSunlightWindows = hasRealSunlightWindows ? data.sunlight_windows! : [];

    const groundAngle = isFiniteNum(data.ground_angle_deg)
        ? data.ground_angle_deg
        : isFiniteNum(data.ground_angle)
            ? data.ground_angle
            : null;

    const slopeSuitability = isFiniteNum(data.scoring?.normalized_metrics?.slope_suitability)
        ? Math.max(0, Math.min(1, data.scoring!.normalized_metrics!.slope_suitability!))
        : groundAngle !== null
            ? Math.max(0, Math.min(1, 1 - groundAngle / 25))
            : 0.5;

    const lolaRoughnessDeg = isFiniteNum(data.lola_roughness_deg) ? data.lola_roughness_deg : null;

    const chartEndMs = visibleSpanEndMs ?? Math.max(blockStartMs + 3600 * 1000, blockEndMs - MAX_MISSION_PAD_MS);

    const builtVisibility = hasRealVisibility
        ? buildVisibilityFromWindows(
            timelineVisibilityWindows,
            null,
            blockStartMs,
            chartEndMs
        )
        : {
            series: fallback.earthVisibility24h,
            labels: HOURS_LABELS,
            coveragePct: null
        };

    const peakSunlight = isFiniteNum(data.peak_sunlight)
        ? data.peak_sunlight
        : Math.max(...sunlight24h);

    const peakValue = isFiniteNum(data.peak)
        ? data.peak
        : isFiniteNum(data.peak_sun_angle)
            ? data.peak_sun_angle
            : Math.max(...sunlightAngle24h);

    return {
        terrainType: data.terrain_type ?? null,
        terrainClassId: isFiniteNum(data.terrain_class_id) ? data.terrain_class_id : null,
        daytimeAvgSunAngle: isFiniteNum(data.daytime_avg_sun_angle)
            ? data.daytime_avg_sun_angle
            : null,
        terrainElevationM: isFiniteNum(data.terrain_elevation_m)
            ? data.terrain_elevation_m
            : null,
        groundAngle,
        lolaRoughnessDeg,
        slopeSuitability,
        timelineVisibilityWindows,
        timelineSunlightWindows,
        hasTimelineBlockData: true,
        hasRealSunlightWindows,
        visibilitySeries: builtVisibility.series,
        visibilityLabels: builtVisibility.labels,
        hasRealVisibility,
        peakSunlight,
        peakValue,
        sunlight24h,
        sunlightAngle24h,
        isEstimatedSunSeries: !hasRealSunSeries
    };
}

export async function fetchSiteTelemetry(
    lat: number,
    lon: number,
    startMs: number,
    endMs: number,
    stepMinutes = 60,
    signal?: AbortSignal
): Promise<Partial<SelectedSite>> {
    const resolvedEndMs = Math.max(endMs, startMs + 3600 * 1000);
    const startIso = new Date(startMs).toISOString();
    const endIso = new Date(resolvedEndMs).toISOString();
    const clampedStep = Math.max(1, Math.min(1440, Math.round(stepMinutes)));

    const params = new URLSearchParams({
        lat: lat.toString(),
        long: lon.toString(),
        mission_start: startIso,
        mission_end: endIso,
        start: startIso,
        end: endIso,
        step_minutes: clampedStep.toString()
    });

    const response = await fetch(`${API_BASE_URL}/fetch-data?${params.toString()}`, {
        signal
    });
    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const errBody = await response.json();
            if (typeof errBody?.detail === 'string') {
                detail = errBody.detail;
            }
        } catch {
            // Ignore non-JSON error payload
        }
        throw new Error(detail);
    }

    const data: FetchDataResponse = await response.json();

    const rawScore = isFiniteNum(data.score)
        ? data.score
        : isFiniteNum(data.scoring?.score)
            ? data.scoring!.score!
            : null;

    const visibilityWindows = Array.isArray(data.visibility_windows) ? data.visibility_windows : [];
    const sunlightWindows = Array.isArray(data.sunlight_windows) ? data.sunlight_windows : [];

    const groundAngle = isFiniteNum(data.ground_angle_deg)
        ? data.ground_angle_deg
        : isFiniteNum(data.ground_angle)
            ? data.ground_angle
            : null;

    const slopeSuitability = isFiniteNum(data.scoring?.normalized_metrics?.slope_suitability)
        ? Math.max(0, Math.min(1, data.scoring!.normalized_metrics!.slope_suitability!))
        : groundAngle !== null
            ? Math.max(0, Math.min(1, 1 - groundAngle / 25))
            : 0.5;

    const lolaRoughnessDeg = isFiniteNum(data.lola_roughness_deg) ? data.lola_roughness_deg : null;

    const parsedStartMs = data.mission_start
        ? (parseLunarTimestamp(data.mission_start) ?? startMs)
        : startMs;
    const parsedEndMs = data.mission_end
        ? (parseLunarTimestamp(data.mission_end) ?? resolvedEndMs)
        : resolvedEndMs;
    const missionHours = Math.max(1, (parsedEndMs - parsedStartMs) / 3600000);
    const resolvedStep = isFiniteNum(data.step_minutes) ? data.step_minutes : clampedStep;

    const fallbackRescore = rescoreFromPayload(
        {
            sunlight_windows: sunlightWindows,
            visibility_windows: visibilityWindows,
            normalized_metrics: { slope_suitability: slopeSuitability }
        },
        new Date(parsedStartMs).toISOString(),
        new Date(parsedEndMs).toISOString()
    );

    const sunlightFraction = isFiniteNum(data.scoring_metrics?.sunlight_fraction)
        ? data.scoring_metrics!.sunlight_fraction!
        : fallbackRescore.metrics.sun.fraction;

    const earthVisibilityFraction = isFiniteNum(data.scoring_metrics?.earth_visibility_fraction)
        ? data.scoring_metrics!.earth_visibility_fraction!
        : fallbackRescore.metrics.earth.fraction;

    const scoringMetrics: ScoringMetrics = {
        sunlight_fraction: sunlightFraction,
        longest_darkness_hours: isFiniteNum(data.scoring_metrics?.longest_darkness_hours)
            ? data.scoring_metrics!.longest_darkness_hours!
            : fallbackRescore.metrics.sun.maxOutageHours,
        earth_visibility_fraction: earthVisibilityFraction,
        longest_earth_blackout_hours: isFiniteNum(data.scoring_metrics?.longest_earth_blackout_hours)
            ? data.scoring_metrics!.longest_earth_blackout_hours!
            : fallbackRescore.metrics.earth.maxOutageHours,
        slope_p95_degrees: isFiniteNum(data.scoring_metrics?.slope_p95_degrees)
            ? data.scoring_metrics!.slope_p95_degrees!
            : null
    };

    const scoringBlock: ScoringBlock = {
        score: rawScore ?? fallbackRescore.score,
        feasible: data.scoring?.feasible ?? null,
        failed_constraints: data.scoring?.failed_constraints ?? [],
        normalized_metrics: {
            sunlight: isFiniteNum(data.scoring?.normalized_metrics?.sunlight)
                ? data.scoring!.normalized_metrics!.sunlight!
                : fallbackRescore.normalized[0],
            darkness_endurance: isFiniteNum(data.scoring?.normalized_metrics?.darkness_endurance)
                ? data.scoring!.normalized_metrics!.darkness_endurance!
                : fallbackRescore.normalized[1],
            earth_visibility: isFiniteNum(data.scoring?.normalized_metrics?.earth_visibility)
                ? data.scoring!.normalized_metrics!.earth_visibility!
                : fallbackRescore.normalized[2],
            communication_endurance: isFiniteNum(
                data.scoring?.normalized_metrics?.communication_endurance
            )
                ? data.scoring!.normalized_metrics!.communication_endurance!
                : fallbackRescore.normalized[3],
            slope_suitability: slopeSuitability
        },
        model_version: data.scoring?.model_version,
        data_quality: data.scoring?.data_quality,
        missing_metrics: data.scoring?.missing_metrics,
        unavailable_sources: data.scoring?.unavailable_sources,
        metadata: data.scoring?.metadata
    };

    const sunlitHours = Number((sunlightFraction * missionHours).toFixed(2));
    const sunlitPercentage = Number((sunlightFraction * 100).toFixed(1));
    const sampleCount = isFiniteNum(data.scoring?.metadata?.sample_count)
        ? data.scoring!.metadata!.sample_count!
        : null;

    const missionSunlight: MissionSunlightMetrics = {
        startIso: new Date(parsedStartMs).toISOString(),
        endIso: new Date(parsedEndMs).toISOString(),
        missionHours: Number(missionHours.toFixed(2)),
        sunlitHours,
        sunlitPercentage,
        stepMinutes: resolvedStep,
        sampleCount,
        sunlitSampleCount:
            sampleCount !== null ? Math.round(sunlightFraction * sampleCount) : null,
        isFallback: false
    };

    const finalScore = rawScore !== null ? rawScore : fallbackRescore.score;

    return {
        score: Number(finalScore.toFixed(1)),
        rescoreResult: fallbackRescore,
        scoringMetrics,
        scoringBlock,
        terrainElevationM: isFiniteNum(data.terrain_elevation_m)
            ? data.terrain_elevation_m
            : undefined,
        groundAngle: groundAngle ?? undefined,
        lolaRoughnessDeg: lolaRoughnessDeg ?? undefined,
        slopeSuitability,
        visibilityWindows,
        sunlightWindows,
        visibilityCoveragePct: Number((earthVisibilityFraction * 100).toFixed(1)),
        missionSunlight,
        loadingMissionSunlight: false,
        missionSunlightError: null
    };
}