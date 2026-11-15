import type {
    DateEvaluation,
    EarthEphemeris,
    FetchDataResponse,
    MissionSunlightMetrics,
    RecommendedDateWindow,
    SelectedSite,
    SunlightDurationResponse,
    VisibilityWindow
} from './types';

export const HOURS_LABELS = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}h`);
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

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

function firstFiniteNumber(...values: Array<number | null | undefined>): number | null {
    for (const v of values) {
        if (typeof v === 'number' && Number.isFinite(v)) return v;
    }
    return null;
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
    const match = raw.trim().match(/^(\d{4})-([A-Za-z]{3})-(\d{2})\s+(\d{2}):(\d{2})$/);
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

    const fallback = Date.parse(`${raw} UTC`);
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
        for (const win of site.visibilityWindows) {
            const s = parseLunarTimestamp(win.start);
            const e = parseLunarTimestamp(win.end);
            if (s !== null) allTimestamps.push(s);
            if (e !== null) allTimestamps.push(e);
        }
    }

    if (allTimestamps.length === 0) {
        return {
            startMs: Date.UTC(2026, 9, 1, 0, 0),
            endMs: Date.UTC(2026, 9, 31, 23, 0)
        };
    }

    const minDate = new Date(Math.min(...allTimestamps));
    const maxDate = new Date(Math.max(...allTimestamps));

    return {
        startMs: Date.UTC(minDate.getUTCFullYear(), minDate.getUTCMonth(), 1, 0, 0),
        endMs: Date.UTC(maxDate.getUTCFullYear(), maxDate.getUTCMonth() + 1, 0, 23, 0)
    };
}

export function evaluateSiteAtTimestamp(site: SelectedSite, timestampMs: number): DateEvaluation {
    const parsedWindows = site.visibilityWindows
        .map((w) => ({
            startMs: parseLunarTimestamp(w.start),
            endMs: parseLunarTimestamp(w.end)
        }))
        .filter((w): w is { startMs: number; endMs: number } => w.startMs !== null && w.endMs !== null);

    const hasVisibilityData = site.hasRealVisibility;
    const isEarthVisible = hasVisibilityData
        ? parsedWindows.some((w) => timestampMs >= w.startMs && timestampMs <= w.endMs)
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
    const isDaylight = sunAngleDeg > 1.0;

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

/**
 * Finds contiguous recommended landing start dates across [startMs, endMs],
 * scoring each candidate touchdown date across the full mission duration.
 */
export function findRecommendedLandingWindows(
    targetSites: SelectedSite[],
    startMs: number,
    endMs: number,
    missionDurationHours = 72
): RecommendedDateWindow[] {
    if (targetSites.length === 0 || endMs <= startMs) return [];

    const stepMs = 6 * 3600 * 1000;
    const durationMs = Math.max(1, missionDurationHours) * 3600 * 1000;
    const samples: { t: number; score: number; allOptimal: boolean }[] = [];

    for (let t = startMs; t <= endMs; t += stepMs) {
        // Sample start, midpoint, and end of the mission interval [t, t + durationMs]
        const missionEnd = t + durationMs;
        const checkpoints =
            durationMs <= stepMs
                ? [t]
                : [t, t + durationMs * 0.33, t + durationMs * 0.67, missionEnd];

        let totalScore = 0;
        let allCheckpointsOptimal = true;

        for (const cp of checkpoints) {
            const evals = targetSites.map((s) => evaluateSiteAtTimestamp(s, cp));
            const cpAvg = evals.reduce((acc, e) => acc + e.suitabilityScore, 0) / evals.length;
            totalScore += cpAvg;
            if (!evals.every((e) => e.status === 'Optimal')) {
                allCheckpointsOptimal = false;
            }
        }

        const avgScore = totalScore / checkpoints.length;
        samples.push({ t, score: avgScore, allOptimal: allCheckpointsOptimal });
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
        windows = collectSegments((s) => s.score >= 55);
    }

    return windows
        .sort((a, b) => b.avgScore - a.avgScore || b.endMs - b.startMs - (a.endMs - a.startMs))
        .slice(0, 3);
}

export function buildVisibilityFromWindows(windows: VisibilityWindow[]) {
    const parsed = windows
        .map((w) => ({
            startMs: parseLunarTimestamp(w.start),
            endMs: parseLunarTimestamp(w.end)
        }))
        .filter((w): w is { startMs: number; endMs: number } => w.startMs !== null && w.endMs !== null && w.endMs >= w.startMs);

    if (parsed.length === 0) {
        return {
            series: Array(24).fill(0),
            labels: HOURS_LABELS,
            coveragePct: 0
        };
    }

    const minStart = Math.min(...parsed.map((w) => w.startMs));
    const maxEnd = Math.max(...parsed.map((w) => w.endMs));

    const startDate = new Date(minStart);
    const endDate = new Date(maxEnd);

    const spanStartMs = Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth(), 1, 0, 0);
    const spanEndMs = Date.UTC(endDate.getUTCFullYear(), endDate.getUTCMonth() + 1, 0, 23, 0);
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

    const coveragePct = Number(Math.min(100, (totalVisibleMs / totalSpanMs) * 100).toFixed(1));

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

export async function fetchSiteTelemetry(
    lat: number,
    lon: number
): Promise<Partial<SelectedSite>> {
    const params = new URLSearchParams({
        lat: lat.toString(),
        long: lon.toString()
    });

    const response = await fetch(`${API_BASE_URL}/fetch-data?${params.toString()}`);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const data: FetchDataResponse = await response.json();
    const validScore =
        typeof data.score === 'number' && Number.isFinite(data.score) ? data.score : null;

    const fallback = buildFallbackSeries(lat, lon, data.daytime_avg_sun_angle);
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
    const visibilityWindows = hasRealVisibility ? data.visibility_windows! : [];
    const builtVisibility = hasRealVisibility
        ? buildVisibilityFromWindows(visibilityWindows)
        : {
            series: fallback.earthVisibility24h,
            labels: HOURS_LABELS,
            coveragePct: null
        };

    const groundAngle =
        typeof data.ground_angle_deg === 'number' && Number.isFinite(data.ground_angle_deg)
            ? data.ground_angle_deg
            : typeof data.ground_angle === 'number' && Number.isFinite(data.ground_angle)
                ? data.ground_angle
                : null;

    const lolaRoughnessDeg =
        typeof data.lola_roughness_deg === 'number' && Number.isFinite(data.lola_roughness_deg)
            ? data.lola_roughness_deg
            : null;

    const peakSunlight =
        typeof data.peak_sunlight === 'number' ? data.peak_sunlight : Math.max(...sunlight24h);

    const peakValue =
        typeof data.peak === 'number'
            ? data.peak
            : typeof data.peak_sun_angle === 'number'
                ? data.peak_sun_angle
                : Math.max(...sunlightAngle24h);

    return {
        score: validScore,
        terrainType: data.terrain_type ?? null,
        terrainClassId: typeof data.terrain_class_id === 'number' ? data.terrain_class_id : null,
        daytimeAvgSunAngle:
            typeof data.daytime_avg_sun_angle === 'number' ? data.daytime_avg_sun_angle : null,
        terrainElevationM:
            typeof data.terrain_elevation_m === 'number' ? data.terrain_elevation_m : null,
        groundAngle,
        lolaRoughnessDeg,
        visibilityWindows,
        visibilityCoveragePct: builtVisibility.coveragePct,
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

/**
 * Calls GET /sunlight-duration for a candidate lunar site across [startMs, endMs].
 */
export async function fetchSunlightDuration(
    lat: number,
    lon: number,
    startMs: number,
    endMs: number,
    stepMinutes = 60,
    signal?: AbortSignal
): Promise<MissionSunlightMetrics> {
    const safeEndMs = Math.max(endMs, startMs + 3600 * 1000);
    const startIso = new Date(startMs).toISOString();
    const endIso = new Date(safeEndMs).toISOString();
    const clampedStep = Math.max(1, Math.min(1440, Math.round(stepMinutes)));

    const params = new URLSearchParams({
        lat: lat.toString(),
        long: lon.toString(),
        start: startIso,
        end: endIso,
        step_minutes: clampedStep.toString()
    });

    const response = await fetch(`${API_BASE_URL}/sunlight-duration?${params.toString()}`, {
        signal
    });

    if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
            const errPayload = await response.json();
            if (typeof errPayload?.detail === 'string') {
                detail = errPayload.detail;
            }
        } catch {
            // Ignore non-JSON error body
        }
        throw new Error(detail);
    }

    const data: SunlightDurationResponse = await response.json();

    const fallbackMissionHours = (safeEndMs - startMs) / (3600 * 1000);
    const missionHours =
        firstFiniteNumber(data.total_duration_hours, data.interval_hours, data.total_hours) ??
        fallbackMissionHours;

    const resolvedStep = firstFiniteNumber(data.step_minutes) ?? clampedStep;
    const sampleCount = firstFiniteNumber(data.total_samples, data.sample_count);
    const sunlitSampleCount = firstFiniteNumber(data.sunlit_samples, data.sunlight_samples);

    const directHours = firstFiniteNumber(
        data.sunlight_duration_hours,
        data.average_sunlight_duration_hours,
        data.avg_sunlight_duration_hours,
        data.total_sunlight_hours,
        data.sunlight_hours,
        data.duration_hours
    );

    const directMinutes = firstFiniteNumber(
        data.sunlight_duration_minutes,
        data.sunlight_minutes,
        data.duration_minutes
    );

    const directSeconds = firstFiniteNumber(
        data.sunlight_duration_seconds,
        data.sunlight_seconds
    );

    const directPct = firstFiniteNumber(
        data.sunlight_percentage,
        data.sunlit_percentage,
        data.sunlight_percent
    );

    const directFraction = firstFiniteNumber(
        data.sunlight_fraction,
        data.sunlit_fraction,
        data.sunlight_ratio
    );

    let sunlitHours = 0;
    if (directHours !== null) {
        sunlitHours = directHours;
    } else if (directMinutes !== null) {
        sunlitHours = directMinutes / 60;
    } else if (directSeconds !== null) {
        sunlitHours = directSeconds / 3600;
    } else if (directPct !== null) {
        sunlitHours = (directPct / 100) * missionHours;
    } else if (directFraction !== null) {
        sunlitHours = directFraction * missionHours;
    } else if (sunlitSampleCount !== null) {
        sunlitHours = (sunlitSampleCount * resolvedStep) / 60;
    }

    const sunlitPercentage =
        directPct !== null
            ? directPct
            : directFraction !== null
                ? directFraction * 100
                : missionHours > 0
                    ? (sunlitHours / missionHours) * 100
                    : 0;

    return {
        startIso,
        endIso,
        missionHours: Number(missionHours.toFixed(2)),
        sunlitHours: Number(Math.max(0, sunlitHours).toFixed(2)),
        sunlitPercentage: Number(Math.max(0, Math.min(100, sunlitPercentage)).toFixed(1)),
        stepMinutes: resolvedStep,
        sampleCount,
        sunlitSampleCount
    };
}