export interface VisibilityWindow {
    start: string;
    end: string;
}

export interface WindowStats {
    fraction: number;
    maxOutageHours: number;
}

export interface RescorePayload {
    sunlight_windows: VisibilityWindow[];
    visibility_windows: VisibilityWindow[];
    normalized_metrics?: {
        slope_suitability?: number | null;
    } | null;
    scoring?: {
        normalized_metrics?: {
            slope_suitability?: number | null;
        } | null;
    } | null;
}

export interface RescoreResult {
    score: number;
    metrics: {
        sun: WindowStats;
        earth: WindowStats;
    };
    normalized: [number, number, number, number, number];
}

export interface ScoringMetrics {
    sunlight_fraction: number;
    longest_darkness_hours: number;
    earth_visibility_fraction: number;
    longest_earth_blackout_hours: number;
    slope_p95_degrees: number | null;
}

export interface ScoringBlock {
    score: number;
    feasible: boolean | null;
    failed_constraints: string[];
    normalized_metrics: {
        sunlight: number;
        darkness_endurance: number;
        earth_visibility: number;
        communication_endurance: number;
        slope_suitability: number;
    };
    model_version?: string;
    data_quality?: string;
    missing_metrics?: string[];
    unavailable_sources?: string[];
    metadata?: {
        period_start?: string;
        period_stop?: string;
        time_step_minutes?: number;
        sample_count?: number;
        footprint_radius_m?: number;
        slope_sample_count?: number;
        horizon_data_quality?: string;
        data_sources?: string[];
    };
}

export interface MissionSunlightMetrics {
    startIso: string;
    endIso: string;
    missionHours: number;
    sunlitHours: number;
    sunlitPercentage: number;
    stepMinutes: number;
    sampleCount: number | null;
    sunlitSampleCount: number | null;
    isFallback?: boolean;
}

export interface FetchDataResponse {
    mission_start?: string | null;
    mission_end?: string | null;
    step_minutes?: number | null;
    sunlight_windows?: VisibilityWindow[] | null;
    visibility_windows?: VisibilityWindow[] | null;
    terrain_elevation_m?: number | null;
    ground_angle_deg?: number | null;
    ground_angle?: number | null;
    lola_roughness_deg?: number | null;
    score?: number | null;
    scoring_metrics?: Partial<ScoringMetrics> | null;
    scoring?: Partial<ScoringBlock> | null;
    daytime_avg_sun_angle?: number | null;
    terrain_type?: string | null;
    terrain_class_id?: number | null;
    peak_sunlight?: number | null;
    peak?: number | null;
    peak_sun_angle?: number | null;
    sunlight_24h?: number[] | null;
    earth_visibility_24h?: number[] | null;
    sunlight_angle_24h?: number[] | null;
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
    rescoreResult: RescoreResult | null;
    scoringMetrics: ScoringMetrics | null;
    scoringBlock: ScoringBlock | null;
    terrainType: string | null;
    terrainClassId: number | null;
    daytimeAvgSunAngle: number | null;
    terrainElevationM: number | null;
    groundAngle: number | null;
    lolaRoughnessDeg: number | null;
    slopeSuitability: number;
    /** Active mission interval windows [selectedTimeMs, selectedTimeMs + missionDuration] */
    visibilityWindows: VisibilityWindow[];
    sunlightWindows: VisibilityWindow[];
    /** Full timeline block windows so the timeline track & recommendations never become partial */
    timelineVisibilityWindows: VisibilityWindow[];
    timelineSunlightWindows: VisibilityWindow[];
    hasTimelineBlockData: boolean;
    hasRealSunlightWindows: boolean;
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
    updatingTelemetry: boolean;
    scoreError: boolean;
    missionSunlight: MissionSunlightMetrics | null;
    loadingMissionSunlight: boolean;
    missionSunlightError: string | null;
}

export interface EarthEphemeris {
    subEarthLatDeg: number;
    subEarthLonDeg: number;
    distanceKm: number;
    distanceM: number;
    sunLonDeg: number;
    sunLatDeg: number;
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