<script lang="ts">
    import { onMount, onDestroy } from 'svelte';

    // Explicitly type variables for TypeScript strict mode
    let viewer: any = null;
    let intervalId: ReturnType<typeof setInterval> | undefined = undefined;
    let handler: any = null; // <-- Add handler reference for cleanup
    let Cesium: any = null;

    // Helper to generate a random number within a min/max range
    function getRandomInRange(min: number, max: number): number {
        return Math.random() * (max - min) + min;
    }

    function flyToRandomSpot() {
        if (!viewer || !Cesium) return;

        // Random Moon Coordinates
        const randomLongitude = getRandomInRange(-180, 180);
        const randomLatitude = getRandomInRange(-90, 90);
        const randomHeight = getRandomInRange(1000000, 3000000);
        const randomHeading = getRandomInRange(0, 360);       // Random rotation/facing direction
        //const randomPitch = getRandomInRange(-90, -45);       // Top-down to angled view
        const randomPitch = getRandomInRange(-90, -89);

        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(randomLongitude, randomLatitude, randomHeight),
            orientation: {
                heading: Cesium.Math.toRadians(randomHeading),
                pitch: Cesium.Math.toRadians(randomPitch),
                roll: 0.0
            },
            duration: 4.0 // 4 second smooth flight animation
        });
    }

    onMount(async () => {
        window.CESIUM_BASE_URL = '/cesium/';

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

        // --- DETECT CLICKS & CONVERT TO LAT/LON ---
        handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

        handler.setInputAction((movement: { position: any }) => {
            // 1. Pick the exact 3D position on the Moon tileset surface
            let cartesian = viewer.scene.pickPosition(movement.position);

            // Fallback to the mathematical Moon ellipsoid if the click missed the 3D tiles
            if (!Cesium.defined(cartesian)) {
                cartesian = viewer.camera.pickEllipsoid(movement.position, Cesium.Ellipsoid.MOON);
            }

            if (Cesium.defined(cartesian)) {
                // 2. Convert 3D Cartesian (X, Y, Z) to Cartographic (radians) using the Moon ellipsoid
                const cartographic = Cesium.Cartographic.fromCartesian(
                    cartesian,
                    Cesium.Ellipsoid.MOON
                );

                // 3. Convert radians to degrees
                const latitude = Cesium.Math.toDegrees(cartographic.latitude);
                const longitude = Cesium.Math.toDegrees(cartographic.longitude);
                const height = cartographic.height; // Elevation in meters relative to Moon ellipsoid

                console.log(`Lat: ${latitude.toFixed(5)}°, Lon: ${longitude.toFixed(5)}°, Height: ${height.toFixed(1)}m`);
            }
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

        flyToRandomSpot();
        intervalId = setInterval(flyToRandomSpot, 5000);
    });

    onDestroy(() => {
        if (intervalId !== undefined) clearInterval(intervalId);
        if (handler) handler.destroy(); // <-- Prevent memory leaks on unmount
    });
</script>

<div id="cesiumContainer"></div>

<div class="menu">
    <h1 style="margin-top: 10vh;">Lunar Landing Site Navigator</h1>
    
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
        height: 100%;
        right: 0;
        top: 0;
        width: 35vw;
        padding-left: 10vw;
        background: linear-gradient(to right, rgba(7, 7, 7, 0) 0%, #070707 25%);
    }
</style>