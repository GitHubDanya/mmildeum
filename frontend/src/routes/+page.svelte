<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import {
        Chart,
        LineController,
        LineElement,
        PointElement,
        LinearScale,
        CategoryScale,
        Filler,
        Tooltip
    } from 'chart.js';

    Chart.register(
        LineController,
        LineElement,
        PointElement,
        LinearScale,
        CategoryScale,
        Filler,
        Tooltip
    );

    interface FetchDataResponse {
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

    interface SelectedSite {
        id: number;
        name: string;
        lat: string;
        lon: string;
        alt: string;
        rawLat: number;
        rawLon: number;
        rawAlt: number;
        point: any;
        label: any;
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

    interface SparkChartConfig {
        data: number[];
        color: string;
        unit: string;
        min: number;
        max: number;
        stepped?: boolean;
    }

    const HOURS_LABELS = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}h`);
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

    let viewer: any = null;
    let intervalId: ReturnType<typeof setInterval> | undefined = undefined;
    let handler: any = null;
    let Cesium: any = null;
    let pointsCollection: any = null;
    let labelsCollection: any = null;

    let selectedSites: SelectedSite[] = [];
    let activeSiteId: number | null = null;
    let nextSiteId = 1;

    $: activeSite = selectedSites.find((s) => s.id === activeSiteId) ?? null;

    $: if (Cesium && selectedSites) {
        selectedSites.forEach((site) => {
            if (site.point) {
                const isSelected = site.id === activeSiteId;
                site.point.pixelSize = isSelected ? 16 : 12;
                site.point.outlineWidth = isSelected ? 3 : 2;
            }
        });
    }

    function hexToRgba(hex: string, alpha: number): string {
        const clean = hex.replace('#', '');
        const bigint = parseInt(clean, 16);
        const r = (bigint >> 16) & 255;
        const g = (bigint >> 8) & 255;
        const b = bigint & 255;
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    // Svelte action for minimal, responsive Chart.js sparkline graphs
    function minimalChart(node: HTMLCanvasElement, config: SparkChartConfig) {
        const buildDataset = (cfg: SparkChartConfig) => ({
            data: cfg.data,
            borderColor: cfg.color,
            borderWidth: 1.75,
            pointRadius: 0,
            pointHoverRadius: 3.5,
            pointHoverBackgroundColor: cfg.color,
            pointHoverBorderColor: '#070707',
            pointHoverBorderWidth: 1.5,
            tension: cfg.stepped ? 0 : 0.35,
            stepped: cfg.stepped ? ('middle' as const) : false,
            fill: true,
            backgroundColor: (context: any) => {
                const { ctx, chartArea } = context.chart;
                if (!chartArea) return 'transparent';
                const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
                gradient.addColorStop(0, hexToRgba(cfg.color, 0.22));
                gradient.addColorStop(1, hexToRgba(cfg.color, 0.0));
                return gradient;
            }
        });

        const chart = new Chart(node, {
            type: 'line',
            data: {
                labels: HOURS_LABELS,
                datasets: [buildDataset(config)]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 250 },
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: true,
                        backgroundColor: '#0d0d0d',
                        titleColor: 'rgba(234, 234, 234, 0.65)',
                        bodyColor: '#ffffff',
                        borderColor: 'rgba(234, 234, 234, 0.2)',
                        borderWidth: 1,
                        padding: 8,
                        displayColors: false,
                        titleFont: { family: 'Rubik, sans-serif', size: 10, weight: 400 },
                        bodyFont: { family: 'Rubik, sans-serif', size: 12, weight: 600 },
                        callbacks: {
                            title: (items) => `${items[0]?.label ?? ''} UTC`,
                            label: (item) => `${Number(item.raw).toFixed(1)}${config.unit}`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: {
                            color: 'rgba(234, 234, 234, 0.45)',
                            font: { family: 'Rubik, sans-serif', size: 9 },
                            maxRotation: 0,
                            autoSkip: false,
                            callback: (_val, index) => (index % 6 === 0 || index === 23 ? HOURS_LABELS[index] : '')
                        }
                    },
                    y: {
                        min: config.min,
                        max: config.max,
                        border: { display: false },
                        grid: {
                            color: 'rgba(234, 234, 234, 0.07)'
                        },
                        ticks: {
                            color: 'rgba(234, 234, 234, 0.45)',
                            font: { family: 'Rubik, sans-serif', size: 9 },
                            maxTicksLimit: 3,
                            callback: (val) => `${val}${config.unit}`
                        }
                    }
                }
            }
        });

        return {
            update(newConfig: SparkChartConfig) {
                chart.data.datasets[0] = buildDataset(newConfig) as any;
                if (chart.options.scales?.y) {
                    chart.options.scales.y.min = newConfig.min;
                    chart.options.scales.y.max = newConfig.max;
                }
                chart.update();
            },
            destroy() {
                chart.destroy();
            }
        };
    }

    // Fallback 24h telemetry generator if backend only returns scalar values
    function buildFallbackSeries(lat: number, lon: number, avgSunAngle: number | null) {
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

    async function fetchSiteScore(siteId: number, lat: number, lon: number) {
        selectedSites = selectedSites.map((site) =>
            site.id === siteId ? { ...site, loadingScore: true, scoreError: false } : site
        );

        try {
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
                typeof data.peak_sunlight === 'number'
                    ? data.peak_sunlight
                    : Math.max(...sunlight24h);

            const peakValue =
                typeof data.peak === 'number'
                    ? data.peak
                    : typeof data.peak_sun_angle === 'number'
                        ? data.peak_sun_angle
                        : Math.max(...sunlightAngle24h);

            selectedSites = selectedSites.map((site) => {
                if (site.id !== siteId) return site;

                if (site.label) {
                    const scoreText =
                        validScore !== null ? `Score: ${validScore.toFixed(1)}` : 'Score: N/A';
                    site.label.text = `${site.name} (${scoreText})\nLat: ${site.lat}°, Lon: ${site.lon}°\nAlt: ${site.alt}m`;
                }

                if (site.point && Cesium && validScore !== null) {
                    site.point.color = Cesium.Color.fromCssColorString(getScoreHexColor(validScore));
                }

                return {
                    ...site,
                    score: validScore,
                    terrainType: data.terrain_type ?? null,
                    terrainClassId:
                        typeof data.terrain_class_id === 'number' ? data.terrain_class_id : null,
                    daytimeAvgSunAngle:
                        typeof data.daytime_avg_sun_angle === 'number'
                            ? data.daytime_avg_sun_angle
                            : null,
                    terrainElevationM:
                        typeof data.terrain_elevation_m === 'number'
                            ? data.terrain_elevation_m
                            : null,
                    groundAngle,
                    peakSunlight,
                    peakValue,
                    sunlight24h,
                    earthVisibility24h,
                    sunlightAngle24h,
                    isEstimatedSeries: !hasRealSeries,
                    loadingScore: false,
                    scoreError: false
                };
            });
        } catch (error) {
            console.error(`Failed to fetch data for site #${siteId}:`, error);
            selectedSites = selectedSites.map((site) =>
                site.id === siteId ? { ...site, loadingScore: false, scoreError: true } : site
            );
        }
    }

    function openSiteDetails(site: SelectedSite) {
        activeSiteId = site.id;
        flyToSite(site);
    }

    function closeSiteDetails() {
        activeSiteId = null;
    }

    function flyToSite(site: SelectedSite) {
        if (!viewer || !Cesium) return;

        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(
                site.rawLon,
                site.rawLat,
                Math.max(site.rawAlt + 150000, 50000)
            ),
            duration: 1.5
        });
    }

    function removeSite(id: number) {
        const siteToRemove = selectedSites.find((s) => s.id === id);
        if (!siteToRemove) return;

        if (pointsCollection && siteToRemove.point) {
            pointsCollection.remove(siteToRemove.point);
        }
        if (labelsCollection && siteToRemove.label) {
            labelsCollection.remove(siteToRemove.label);
        }

        if (activeSiteId === id) {
            activeSiteId = null;
        }

        selectedSites = selectedSites.filter((s) => s.id !== id);
    }

    function clearAllSites() {
        if (pointsCollection) pointsCollection.removeAll();
        if (labelsCollection) labelsCollection.removeAll();
        selectedSites = [];
        activeSiteId = null;
        nextSiteId = 1;
    }

    function getScoreClass(score: number): string {
        if (score < 25) return 'score-red';
        if (score < 50) return 'score-yellow';
        if (score < 75) return 'score-green';
        return 'score-blue';
    }

    function getScoreHexColor(score: number): string {
        if (score < 25) return '#f87171';
        if (score < 50) return '#facc15';
        if (score < 75) return '#4ade80';
        return '#60a5fa';
    }

    onMount(async () => {
        (window as any).CESIUM_BASE_URL = '/cesium/';

        Cesium = await import('cesium');
        await import('cesium/Build/Cesium/Widgets/widgets.css');

        Cesium.Ion.defaultAccessToken = import.meta.env.VITE_CESIUM_ION_TOKEN;
        Cesium.Ellipsoid.default = Cesium.Ellipsoid.MOON;

        viewer = new Cesium.Viewer('cesiumContainer', {
            baseLayer: false,
            terrain: new Cesium.Terrain(Promise.resolve(new Cesium.EllipsoidTerrainProvider())),
            animation: false,
            baseLayerPicker: false,
            fullscreenButton: false,
            vrButton: false,
            geocoder: false,
            homeButton: false,
            infoBox: false,
            sceneModePicker: false,
            selectionIndicator: false,
            timeline: false,
            navigationHelpButton: false,
            navigationInstructionsInitiallyVisible: false
        });

        viewer.scene.globe.show = false;

        try {
            const moonTileset = await Cesium.Cesium3DTileset.fromIonAssetId(2684829, {
                enableCollision: true
            });
            viewer.scene.primitives.add(moonTileset);
        } catch (error) {
            console.error('Failed to load Moon terrain tileset:', error);
        }

        pointsCollection = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
        labelsCollection = viewer.scene.primitives.add(new Cesium.LabelCollection());

        handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

        handler.setInputAction((movement: { position: any }) => {
            const pickedObject = viewer.scene.pick(movement.position);
            if (Cesium.defined(pickedObject) && pickedObject.id?.siteId !== undefined) {
                const existingSite = selectedSites.find((s) => s.id === pickedObject.id.siteId);
                if (existingSite) {
                    openSiteDetails(existingSite);
                    return;
                }
            }

            let cartesian: any = undefined;

            const ray = viewer.camera.getPickRay(movement.position);
            if (ray && typeof viewer.scene.pickFromRay === 'function') {
                const hit = viewer.scene.pickFromRay(ray);
                if (hit && Cesium.defined(hit.position)) {
                    cartesian = hit.position;
                }
            }

            if (!Cesium.defined(cartesian)) {
                const picked = viewer.scene.pickPosition(movement.position);
                if (Cesium.defined(picked)) {
                    const testCarto = Cesium.Cartographic.fromCartesian(picked, Cesium.Ellipsoid.MOON);
                    if (testCarto && Math.abs(testCarto.height) < 50000) {
                        cartesian = picked;
                    }
                }
            }

            if (!Cesium.defined(cartesian)) {
                cartesian = viewer.camera.pickEllipsoid(movement.position, Cesium.Ellipsoid.MOON);
            }

            if (!Cesium.defined(cartesian)) return;

            const cartographic = Cesium.Cartographic.fromCartesian(
                cartesian,
                Cesium.Ellipsoid.MOON
            );

            const latitude = Cesium.Math.toDegrees(cartographic.latitude);
            const longitude = Cesium.Math.toDegrees(cartographic.longitude);
            const height = cartographic.height;

            const id = nextSiteId++;
            const name = `Site #${id}`;
            const lat = latitude.toFixed(3);
            const lon = longitude.toFixed(3);
            const alt = height.toFixed(1);

            const coordText = `${name}\nLat: ${lat}°, Lon: ${lon}°\nAlt: ${alt}m`;

            const point = pointsCollection.add({
                id: { siteId: id },
                position: cartesian,
                pixelSize: 12,
                color: Cesium.Color.fromCssColorString('#eaeaea'),
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2,
                disableDepthTestDistance: Number.POSITIVE_INFINITY
            });

            const label = labelsCollection.add({
                id: { siteId: id },
                position: cartesian,
                text: coordText,
                font: '13px sans-serif',
                fillColor: Cesium.Color.WHITE,
                outlineColor: Cesium.Color.BLACK,
                outlineWidth: 2,
                style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                pixelOffset: new Cesium.Cartesian2(0, -14),
                disableDepthTestDistance: Number.POSITIVE_INFINITY
            });

            const fallback = buildFallbackSeries(latitude, longitude, null);

            const newSite: SelectedSite = {
                id,
                name,
                lat,
                lon,
                alt,
                rawLat: latitude,
                rawLon: longitude,
                rawAlt: height,
                point,
                label,
                score: null,
                terrainType: null,
                terrainClassId: null,
                daytimeAvgSunAngle: null,
                terrainElevationM: null,
                groundAngle: null,
                peakSunlight: null,
                peakValue: null,
                sunlight24h: fallback.sunlight24h,
                earthVisibility24h: fallback.earthVisibility24h,
                sunlightAngle24h: fallback.sunlightAngle24h,
                isEstimatedSeries: true,
                loadingScore: true,
                scoreError: false
            };

            selectedSites = [...selectedSites, newSite];
            fetchSiteScore(id, latitude, longitude);
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    });

    onDestroy(() => {
        if (intervalId !== undefined) clearInterval(intervalId);
        if (handler) handler.destroy();
        if (viewer && !viewer.isDestroyed()) viewer.destroy();
    });
</script>

<div id="cesiumContainer"></div>

<div class="menu" class:expanded={Boolean(activeSite)}>
    <h1 style="margin-top: 6vh;">Lunar Landing Site Navigator</h1>

    {#if activeSite}
        <div class="detail-panel">
            <!-- Top navigation & site identity header -->
            <div class="detail-nav">
                <button class="back-btn" on:click={closeSiteDetails}>
                    ← All Sites ({selectedSites.length})
                </button>

                <div class="detail-header-center">
                    <strong>{activeSite.name}</strong>
                    <span>{activeSite.lat}°, {activeSite.lon}°</span>
                </div>

                <div class="detail-nav-actions">
                    {#if activeSite.loadingScore}
                        <span class="score-badge loading">...</span>
                    {:else if activeSite.scoreError || typeof activeSite.score !== 'number'}
                        <span class="score-badge error">N/A</span>
                    {:else}
                        <span
                                class="score-badge {getScoreClass(activeSite.score)}"
                                title="Landing Suitability Score"
                        >
                            {activeSite.score.toFixed(1)}
                        </span>
                    {/if}

                    <button
                            class="btn btn-white"
                            on:click={() => activeSite && flyToSite(activeSite)}
                            title="Center camera on {activeSite.name}"
                    >
                        Focus
                    </button>

                    <button
                            class="remove-btn"
                            on:click={() => activeSite && removeSite(activeSite.id)}
                            aria-label="Remove {activeSite.name}"
                            title="Remove site"
                    >
                        ✕
                    </button>
                </div>
            </div>

            {#if activeSite.loadingScore}
                <div class="detail-status">Fetching lunar surface telemetry...</div>
            {:else if activeSite.scoreError}
                <div class="detail-status error-box">
                    <span>Failed to load telemetry from the API.</span>
                    <button
                            class="btn btn-white"
                            on:click={() =>
                            activeSite &&
                            fetchSiteScore(activeSite.id, activeSite.rawLat, activeSite.rawLon)}
                    >
                        Retry
                    </button>
                </div>
            {:else}
                <!-- Two-column layout matching wireframe: Graphs | Data points -->
                <div class="wireframe-columns">
                    <!-- Left Column: Graphs -->
                    <section class="wireframe-box">
                        <header class="wireframe-box-header">
                            <span>Graphs</span>
                            {#if activeSite.isEstimatedSeries}
                                <span class="est-pill" title="Derived from site coordinates until 24h array is provided by API">
                                    24h Model
                                </span>
                            {/if}
                        </header>

                        <div class="graphs-stack">
                            <div class="graph-card">
                                <div class="graph-meta">
                                    <span class="graph-title">Sunlight for 24hrs</span>
                                    <span class="graph-latest" style="color: #fde047;">
                                        {Math.max(...activeSite.sunlight24h).toFixed(0)}% max
                                    </span>
                                </div>
                                <div class="canvas-wrap">
                                    <canvas
                                            use:minimalChart={{
                                            data: activeSite.sunlight24h,
                                            color: '#fde047',
                                            unit: '%',
                                            min: 0,
                                            max: 100,
                                            stepped: true
                                        }}
                                    ></canvas>
                                </div>
                            </div>

                            <div class="graph-card">
                                <div class="graph-meta">
                                    <span class="graph-title">Earth Visibility for 24hrs</span>
                                    <span class="graph-latest" style="color: #60a5fa;">
                                        {Math.max(...activeSite.earthVisibility24h).toFixed(0)}% max
                                    </span>
                                </div>
                                <div class="canvas-wrap">
                                    <canvas
                                            use:minimalChart={{
                                            data: activeSite.earthVisibility24h,
                                            color: '#60a5fa',
                                            unit: '%',
                                            min: 0,
                                            max: 100
                                        }}
                                    ></canvas>
                                </div>
                            </div>

                            <div class="graph-card">
                                <div class="graph-meta">
                                    <span class="graph-title">Sunlight angle for 24hrs</span>
                                    <span class="graph-latest">
                                        {Math.max(...activeSite.sunlightAngle24h).toFixed(1)}° max
                                    </span>
                                </div>
                                <div class="canvas-wrap">
                                    <canvas
                                            use:minimalChart={{
                                            data: activeSite.sunlightAngle24h,
                                            color: '#eaeaea',
                                            unit: '°',
                                            min: 0,
                                            max: 90
                                        }}
                                    ></canvas>
                                </div>
                            </div>
                        </div>
                    </section>

                    <!-- Right Column: Data points -->
                    <section class="wireframe-box">
                        <header class="wireframe-box-header">
                            <span>Data points</span>
                        </header>

                        <div class="datapoints-stack">
                            <div class="datapoint-item">
                                <span class="dp-label">Terrain Type</span>
                                <span class="dp-value">{activeSite.terrainType ?? 'Unknown'}</span>
                            </div>

                            <div class="datapoint-item">
                                <span class="dp-label">Terrain Elevation</span>
                                <span class="dp-value">
                                    {activeSite.terrainElevationM !== null
                                        ? `${activeSite.terrainElevationM.toFixed(1)} m`
                                        : `${activeSite.alt} m`}
                                </span>
                            </div>

                            <div class="datapoint-item">
                                <span class="dp-label">Ground Angle</span>
                                <span class="dp-value">
                                    {activeSite.groundAngle !== null
                                        ? `${activeSite.groundAngle.toFixed(2)}°`
                                        : 'N/A'}
                                </span>
                            </div>

                            <div class="datapoint-item">
                                <span class="dp-label">Peak Sunlight</span>
                                <span class="dp-value">
                                    {activeSite.peakSunlight !== null
                                        ? `${activeSite.peakSunlight.toFixed(1)}%`
                                        : 'N/A'}
                                </span>
                            </div>

                            <div class="datapoint-item">
                                <span class="dp-label">Peak</span>
                                <span class="dp-value">
                                    {activeSite.peakValue !== null
                                        ? `${activeSite.peakValue.toFixed(1)}°`
                                        : 'N/A'}
                                </span>
                            </div>
                        </div>
                    </section>
                </div>
            {/if}
        </div>
    {:else if selectedSites.length > 0}
        <div class="sites-panel">
            <div class="sites-header">
                <span>Selected Sites ({selectedSites.length})</span>
                <button class="btn btn-white" on:click={clearAllSites}>Clear All</button>
            </div>

            <div class="sites-list">
                {#each selectedSites as site (site.id)}
                    <div class="site-card">
                        <button
                                class="site-info"
                                on:click={() => openSiteDetails(site)}
                                title="View details for {site.name}"
                        >
                            <strong>{site.name}</strong>
                            <span>Lat: {site.lat}° | Lon: {site.lon}° | Alt: {site.alt}m</span>
                            {#if site.terrainType}
                                <span class="terrain-tag">{site.terrainType}</span>
                            {/if}
                        </button>

                        <div class="site-actions">
                            {#if site.loadingScore}
                                <span class="score-badge loading">Scoring...</span>
                            {:else if site.scoreError || typeof site.score !== 'number'}
                                <span class="score-badge error">N/A</span>
                            {:else}
                                <span
                                        class="score-badge {getScoreClass(site.score)}"
                                        title="Landing Suitability Score"
                                >
                                    {site.score.toFixed(1)}
                                </span>
                            {/if}

                            <button
                                    class="remove-btn"
                                    on:click={() => removeSite(site.id)}
                                    aria-label="Remove {site.name}"
                                    title="Remove site"
                            >
                                ✕
                            </button>
                        </div>
                    </div>
                {/each}
            </div>
        </div>
    {:else}
        <p class="hint">Click anywhere on the lunar surface to add candidate landing sites.</p>
    {/if}
</div>

<div class="top-bar">
    <button class="btn btn-white">Our Scoring Algorithm</button>
</div>

<style>
    @font-face {
        font-family: "Rubik";
        src: url("/fonts/Rubik.ttf") format("truetype");
        font-weight: 400;
        font-style: normal;
        font-display: swap;
    }

    :global(body, html) {
        margin: 0 !important;
        color: #eaeaea;
        background-color: #000;
        font-family: "Rubik", sans-serif;
    }

    #cesiumContainer {
        width: 70vw;
        height: 100vh;
        margin: 0;
        padding: 0;
        overflow: hidden;
    }

    h1 {
        text-align: center;
        margin-bottom: 1.25rem;
    }

    .menu {
        position: absolute;
        box-sizing: border-box;
        height: 100%;
        right: 0;
        top: 0;
        width: 40vw;
        padding-left: 12vw;
        padding-right: 2rem;
        display: flex;
        flex-direction: column;
        background: linear-gradient(to right, rgba(7, 7, 7, 0) 0%, #070707 8vw);
        pointer-events: none;
        transition: width 0.25s ease, padding-left 0.25s ease;
    }

    .menu.expanded {
        width: 62vw;
        max-width: 960px;
        padding-left: 10vw;
    }

    .hint {
        text-align: center;
        opacity: 0.7;
        font-size: 0.9rem;
    }

    .sites-panel,
    .detail-panel {
        pointer-events: auto;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        max-height: 78vh;
    }

    .sites-header,
    .detail-nav {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.9rem;
        padding-bottom: 0.55rem;
        border-bottom: 1px solid rgba(234, 234, 234, 0.15);
    }

    .detail-header-center {
        display: flex;
        flex-direction: column;
        align-items: center;
        line-height: 1.2;
    }

    .detail-header-center strong {
        font-size: 0.92rem;
        color: #fff;
    }

    .detail-header-center span {
        font-size: 0.72rem;
        opacity: 0.65;
    }

    .detail-nav-actions {
        display: flex;
        align-items: center;
        gap: 0.4rem;
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

    /* Two-column Wireframe Container */
    .wireframe-columns {
        display: grid;
        grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
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
        padding: 0.55rem 0.75rem;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.02em;
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

    /* Left Column: Graphs */
    .graphs-stack {
        display: flex;
        flex-direction: column;
        gap: 0.6rem;
        padding: 0.65rem;
    }

    .graph-card {
        background-color: rgba(7, 7, 7, 0.55);
        border: 1px solid rgba(234, 234, 234, 0.1);
        border-radius: 8px;
        padding: 0.5rem 0.65rem 0.4rem;
        display: flex;
        flex-direction: column;
        gap: 0.35rem;
    }

    .graph-meta {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 0.4rem;
    }

    .graph-title {
        font-size: 0.75rem;
        color: rgba(234, 234, 234, 0.9);
    }

    .graph-latest {
        font-size: 0.7rem;
        font-weight: 500;
        opacity: 0.85;
    }

    .canvas-wrap {
        position: relative;
        width: 100%;
        height: 82px;
    }

    /* Right Column: Data Points */
    .datapoints-stack {
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 0.55rem;
        padding: 0.65rem;
        flex: 1;
    }

    .datapoint-item {
        background-color: rgba(7, 7, 7, 0.55);
        border: 1px solid rgba(234, 234, 234, 0.1);
        border-radius: 8px;
        padding: 0.6rem 0.7rem;
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
    }

    .dp-label {
        font-size: 0.68rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        opacity: 0.6;
    }

    .dp-value {
        font-size: 0.88rem;
        font-weight: 500;
        color: #fff;
        word-break: break-word;
    }

    .detail-status {
        font-size: 0.82rem;
        opacity: 0.8;
        padding: 0.85rem;
        border-radius: 8px;
        background-color: rgba(234, 234, 234, 0.06);
        text-align: center;
    }

    .detail-status.error-box {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.6rem;
        background-color: rgba(239, 68, 68, 0.12);
        border: 1px solid rgba(239, 68, 68, 0.25);
        color: #fca5a5;
        opacity: 1;
    }

    .sites-list {
        display: flex;
        flex-direction: column;
        gap: 0.5rem;
        overflow-y: auto;
        padding-right: 0.25rem;
    }

    .site-card {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        background-color: rgba(234, 234, 234, 0.08);
        border: 1px solid rgba(234, 234, 234, 0.12);
        border-radius: 10px;
        padding: 0.6rem 0.75rem;
        transition: background-color 0.15s ease;
    }

    .site-card:hover {
        background-color: rgba(234, 234, 234, 0.14);
    }

    .site-info {
        background: none;
        border: none;
        color: inherit;
        font-family: inherit;
        text-align: left;
        cursor: pointer;
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
        padding: 0;
        flex: 1;
    }

    .site-info strong {
        font-size: 0.85rem;
        color: #fff;
    }

    .site-info span {
        font-size: 0.75rem;
        opacity: 0.8;
    }

    .terrain-tag {
        font-size: 0.7rem !important;
        opacity: 0.6 !important;
    }

    .site-actions {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        flex-shrink: 0;
    }

    .score-badge {
        background-color: #eaeaea;
        color: #070707;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.2rem 0.55rem;
        border-radius: 999px;
        min-width: 2.5rem;
        text-align: center;
    }

    .score-badge.loading {
        background-color: rgba(234, 234, 234, 0.15);
        color: #eaeaea;
        font-weight: 400;
    }

    .score-badge.error {
        background-color: rgba(239, 68, 68, 0.2);
        color: #fca5a5;
    }

    .score-badge.score-red {
        background-color: rgba(239, 68, 68, 0.2);
        color: #fca5a5;
    }

    .score-badge.score-yellow {
        background-color: rgba(234, 179, 8, 0.2);
        color: #fde047;
    }

    .score-badge.score-green {
        background-color: rgba(34, 197, 94, 0.2);
        color: #86efac;
    }

    .score-badge.score-blue {
        background-color: rgba(59, 130, 246, 0.2);
        color: #93c5fd;
    }

    .remove-btn {
        background: none;
        border: none;
        color: #eaeaea;
        opacity: 0.6;
        cursor: pointer;
        font-size: 0.85rem;
        padding: 0.25rem 0.4rem;
        border-radius: 6px;
        transition: opacity 0.15s ease, background-color 0.15s ease;
    }

    .remove-btn:hover {
        opacity: 1;
        background-color: rgba(255, 255, 255, 0.1);
    }

    .top-bar {
        position: absolute;
        top: 20px;
        left: 20px;
        display: flex;
        flex-direction: row;
    }

    .btn {
        border-radius: 10px;
        box-shadow: none;
        padding: 0.25rem 0.75rem;
        font-size: 0.75rem;
        font-weight: 500;
        cursor: pointer;
        transition: opacity 0.15s ease;
        border: none;
    }

    .btn:hover {
        opacity: 0.85;
    }

    .btn:focus-visible {
        outline: 2px solid #eaeaea;
        outline-offset: 2px;
    }

    .btn-white {
        background-color: #eaeaea;
        color: #070707;
    }

    @media (max-width: 1150px) {
        .wireframe-columns {
            grid-template-columns: 1fr;
        }
    }
</style>