import type { FetchDataResponse, SelectedSite } from './types';

export const HOURS_LABELS = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}h`);
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

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

export function buildFallbackSeries(lat: number, lon: number, avgSunAngle: number | null) {
    const latFactor = Math.max(0.15, Math.cos((lat * Math.PI) / 180));
    const basePeakAngle =
        avgSunAngle !== null ? Math.min(88, avgSunAngle * 1.45) : 65 * latFactor;

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
    const hasRealSeries =
        Array.isArray(data.sunlight_24h) &&
        data.sunlight_24h.length === 24 &&
        Array.isArray(data.earth_visibility_24h) &&
        data.earth_visibility_24h.length === 24 &&
        Array.isArray(data.sunlight_angle_24h) &&
        data.sunlight_angle_24h.length === 24;

    const sunlight24h = hasRealSeries ? data.sunlight_24h! : fallback.sunlight24h;
    const earthVisibility24h = hasRealSeries
        ? data.earth_visibility_24h!
        : fallback.earthVisibility24h;
    const sunlightAngle24h = hasRealSeries
        ? data.sunlight_angle_24h!
        : fallback.sunlightAngle24h;

    const groundAngle =
        typeof data.ground_angle_deg === 'number'
            ? data.ground_angle_deg
            : typeof data.ground_angle === 'number'
                ? data.ground_angle
                : null;

    const peakSunlight =
        typeof data.peak_sunlight === 'number' ? data.peak_sunlight : Math.max(...sunlight24h);

    const peakValue =
        typeof data.peak === 'number'
            ? data.peak
            : typeof data.peak_sun_angle === 'number'
                ? data.peak_sun_angle
                : Math.max(...sunlightAngle24h);

    const terrainRoughnessM =
        typeof data.terrain_roughness_m === 'number' && Number.isFinite(data.terrain_roughness_m)
            ? data.terrain_roughness_m
            : null;

    const terrainRoughnessMetadata = data.terrain_roughness_metadata ?? null;

    return {
        score: validScore,
        terrainType: data.terrain_type ?? null,
        terrainClassId: typeof data.terrain_class_id === 'number' ? data.terrain_class_id : null,
        daytimeAvgSunAngle:
            typeof data.daytime_avg_sun_angle === 'number' ? data.daytime_avg_sun_angle : null,
        terrainElevationM:
            typeof data.terrain_elevation_m === 'number' ? data.terrain_elevation_m : null,
        groundAngle,
        terrainRoughnessM:
            typeof data.terrain_roughness_m === 'number' &&
            Number.isFinite(data.terrain_roughness_m)
                ? data.terrain_roughness_m
                : null,
        terrainRoughnessMetadata: data.terrain_roughness_metadata ?? null,
        peakSunlight,
        peakValue,
        sunlight24h,
        earthVisibility24h,
        sunlightAngle24h,
        isEstimatedSeries: !hasRealSeries
    };
}