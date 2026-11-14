export interface VisibilityWindow {
    start: string;
    end: string;
}

export interface FetchDataResponse {
    daytime_avg_sun_angle: number | null;
    terrain_elevation_m: number | null;
    ground_angle_deg?: number | null;
    ground_angle?: number | null;
    lola_roughness_deg?: number | null;
    visibility_windows?: VisibilityWindow[] | null;
    terrain_type?: string | null;
    terrain_class_id?: number | null;
    peak_sunlight?: number | null;
    peak?: number | null;
    peak_sun_angle?: number | null;
    sunlight_24h?: number[] | null;
    earth_visibility_24h?: number[] | null;
    sunlight_angle_24h?: number[] | null;
    score?: number | null;
}

export interface SelectedSite {
    id: number;
    name: string;
    lat: string;
    lon: string;
    alt: string;
    rawLat: number;
    rawLon: number;
    rawAlt: number;
    score: number | null;
    terrainType: string | null;
    terrainClassId: number | null;
    daytimeAvgSunAngle: number | null;
    terrainElevationM: number | null;
    groundAngle: number | null;
    lolaRoughnessDeg: number | null;
    visibilityWindows: VisibilityWindow[];
    visibilityCoveragePct: number | null;
    visibilitySeries: number[];
    visibilityLabels: string[];
    hasRealVisibility: boolean;
    peakSunlight: number | null;
    peakValue: number | null;
    sunlight24h: number[];
    sunlightAngle24h: number[];
    isEstimatedSunSeries: boolean;
    loadingScore: boolean;
    scoreError: boolean;
}

export interface DateEvaluation {
    isEarthVisible: boolean;
    hasVisibilityData: boolean;
    sunAngleDeg: number;
    isDaylight: boolean;
    suitabilityScore: number;
    status: 'Optimal' | 'Marginal' | 'No-Go';
}

export interface RecommendedDateWindow {
    startMs: number;
    endMs: number;
    peakMs: number;
    label: string;
    avgScore: number;
    isJointOverlap: boolean;
}

export interface EarthEphemeris {
    subEarthLatDeg: number;
    subEarthLonDeg: number;
    distanceKm: number;
    distanceM: number;
    sunLonDeg: number;
    sunLatDeg: number;
}

export interface SparkChartConfig {
    data: number[];
    labels?: string[];
    color: string;
    unit: string;
    min: number;
    max: number;
    stepped?: boolean;
    activeIndex?: number | null;
    primaryLabel?: string;
    compareData?: number[];
    compareColor?: string;
    compareLabel?: string;
}