export interface FetchDataResponse {
    terrain_type: string | null;
    terrain_class_id: number | null;
    daytime_avg_sun_angle: number | null;
    terrain_elevation_m: number | null;
    ground_angle_deg?: number | null;
    ground_angle?: number | null;
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
    peakSunlight: number | null;
    peakValue: number | null;
    sunlight24h: number[];
    earthVisibility24h: number[];
    sunlightAngle24h: number[];
    isEstimatedSeries: boolean;
    loadingScore: boolean;
    scoreError: boolean;
}

export interface SparkChartConfig {
    data: number[];
    color: string;
    unit: string;
    min: number;
    max: number;
    stepped?: boolean;
    primaryLabel?: string;
    compareData?: number[];
    compareColor?: string;
    compareLabel?: string;
}