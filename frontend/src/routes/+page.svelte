<script lang="ts">
    import { onMount, onDestroy } from 'svelte';

    interface FetchDataResponse {
        terrain_type: string | null;
        terrain_class_id: number | null;
        daytime_avg_sun_angle: number | null;
        terrain_elevation_m: number | null;
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
        loadingScore: boolean;
        scoreError: boolean;
    }

    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

    let viewer: any = null;
    let intervalId: ReturnType<typeof setInterval> | undefined = undefined;
    let handler: any = null;
    let Cesium: any = null;
    let pointsCollection: any = null;
    let labelsCollection: any = null;

    let selectedSites: SelectedSite[] = [];
    let nextSiteId = 1;

    function getRandomInRange(min: number, max: number): number {
        return Math.random() * (max - min) + min;
    }

    function flyToRandomSpot() {
        if (!viewer || !Cesium) return;

        const randomLongitude = getRandomInRange(-180, 180);
        const randomLatitude = getRandomInRange(-90, 90);
        const randomHeight = getRandomInRange(1000000, 3000000);
        const randomHeading = getRandomInRange(0, 360);
        const randomPitch = getRandomInRange(-90, -89);

        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(randomLongitude, randomLatitude, randomHeight),
            orientation: {
                heading: Cesium.Math.toRadians(randomHeading),
                pitch: Cesium.Math.toRadians(randomPitch),
                roll: 0.0
            },
            duration: 4.0
        });
    }

    async function fetchSiteScore(siteId: number, lat: number, lon: number) {
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
                typeof data.score === 'number' && Number.isFinite(data.score)
                    ? data.score
                    : null;

            selectedSites = selectedSites.map((site) => {
                if (site.id !== siteId) return site;

                if (site.label) {
                    const scoreText = validScore !== null ? `Score: ${validScore.toFixed(1)}` : 'Score: N/A';
                    site.label.text = `${site.name} (${scoreText})\nLat: ${site.lat}°, Lon: ${site.lon}°\nAlt: ${site.alt}m`;
                }

                if (site.point && Cesium && validScore !== null) {
                    site.point.color = Cesium.Color.fromCssColorString(getScoreHexColor(validScore));
                }

                return {
                    ...site,
                    score: validScore,
                    terrainType: data.terrain_type,
                    loadingScore: false,
                    scoreError: validScore === null
                };
            });
        } catch (error) {
            console.error(`Failed to fetch data for site #${siteId}:`, error);
            selectedSites = selectedSites.map((site) =>
                site.id === siteId
                    ? { ...site, loadingScore: false, scoreError: true }
                    : site
            );
        }
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

        selectedSites = selectedSites.filter((s) => s.id !== id);
    }

    function clearAllSites() {
        if (pointsCollection) pointsCollection.removeAll();
        if (labelsCollection) labelsCollection.removeAll();
        selectedSites = [];
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
                position: cartesian,
                pixelSize: 12,
                color: Cesium.Color.fromCssColorString('#eaeaea'),
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2,
                disableDepthTestDistance: Number.POSITIVE_INFINITY
            });

            const label = labelsCollection.add({
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

<div class="menu">
    <h1 style="margin-top: 10vh;">Lunar Landing Site Navigator</h1>

    {#if selectedSites.length > 0}
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
                                on:click={() => flyToSite(site)}
                                title="Fly to {site.name}"
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
                                <span class="score-badge {getScoreClass(site.score)}" title="Landing Suitability Score">
                                    {site.score.toFixed(1)}
                                </span>
                            {/if}

                            <button
                                    class="remove-btn"
                                    on:click={() => removeSite(site.id)}
                                    aria-label="Remove {site.name}"
                                    title="Remove site">
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
        background: linear-gradient(to right, rgba(7, 7, 7, 0) 0%, #070707 25%);
        pointer-events: none;
    }

    .hint {
        text-align: center;
        opacity: 0.7;
        font-size: 0.9rem;
    }

    .sites-panel {
        pointer-events: auto;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        max-height: 70vh;
    }

    .sites-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        font-size: 0.9rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(234, 234, 234, 0.15);
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

    .btn-black {
        background-color: #070707;
        color: #eaeaea;
    }
</style>