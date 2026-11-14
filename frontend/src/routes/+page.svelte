<script lang="ts">
    import { onMount, onDestroy } from 'svelte';

    let viewer: any = null;
    let intervalId: ReturnType<typeof setInterval> | undefined = undefined;
    let handler: any = null;
    let Cesium: any = null;
    let pointPrimitive: any = null;
    let labelPrimitive: any = null;
    let selectedCoords: { lat: string; lon: string; alt: string } | null = null;

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

        // Primitive collections render directly in the scene every frame
        const points = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
        const labels = viewer.scene.primitives.add(new Cesium.LabelCollection());

        handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

        handler.setInputAction((movement: { position: any }) => {
            let cartesian: any = undefined;

            // Direct raycast against the Moon 3D tileset (bypasses depth buffer issues)
            const ray = viewer.camera.getPickRay(movement.position);
            if (ray && typeof viewer.scene.pickFromRay === 'function') {
                const hit = viewer.scene.pickFromRay(ray);
                if (hit && Cesium.defined(hit.position)) {
                    cartesian = hit.position;
                }
            }

            // Fallback to depth-buffer pick, rejecting bogus far-plane readings (> 50km)
            if (!Cesium.defined(cartesian)) {
                const picked = viewer.scene.pickPosition(movement.position);
                if (Cesium.defined(picked)) {
                    const testCarto = Cesium.Cartographic.fromCartesian(picked, Cesium.Ellipsoid.MOON);
                    if (testCarto && Math.abs(testCarto.height) < 50000) {
                        cartesian = picked;
                    }
                }
            }

            // Final fallback to the mathematical Moon ellipsoid
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

            selectedCoords = {
                lat: latitude.toFixed(3),
                lon: longitude.toFixed(3),
                alt: height.toFixed(1)
            };

            const coordText = `Lat: ${selectedCoords.lat}°, Lon: ${selectedCoords.lon}°\nAlt: ${selectedCoords.alt}m`;

            if (pointPrimitive && labelPrimitive) {
                pointPrimitive.position = cartesian;
                labelPrimitive.position = cartesian;
                labelPrimitive.text = coordText;
            } else {
                pointPrimitive = points.add({
                    position: cartesian,
                    pixelSize: 12,
                    color: Cesium.Color.RED,
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 2,
                    disableDepthTestDistance: Number.POSITIVE_INFINITY
                });

                labelPrimitive = labels.add({
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
            }
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
    {#if selectedCoords}
        <p style="text-align: center;">
            Lat: {selectedCoords.lat}° | Lon: {selectedCoords.lon}° | Alt: {selectedCoords.alt}m
        </p>
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
        padding-left: 10vw;
        background: linear-gradient(to right, rgba(7, 7, 7, 0) 0%, #070707 25%);
        pointer-events: none;
    }
    
    .top-bar {
        position: absolute;
        top: 20px;
        left: 20px;
        width: 100%;
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