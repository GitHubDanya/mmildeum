<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import type { SelectedSite } from './types';
    import { getScoreHexColor } from './telemetry';

    export let sites: SelectedSite[] = [];
    export let highlightedSiteIds: number[] = [];
    export let rightInsetPx = 0;
    export let onAddSite: (coords: { lat: number; lon: number; alt: number }) => void;
    export let onSelectSite: (siteId: number) => void;

    let viewer: any = null;
    let handler: any = null;
    let Cesium: any = null;
    let pointsCollection: any = null;
    let labelsCollection: any = null;

    const primitivesBySiteId = new Map<number, { point: any; label: any }>();

    export function flyToSite(site: SelectedSite) {
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

    $: if (Cesium && pointsCollection && labelsCollection && sites) {
        const currentIds = new Set(sites.map((s) => s.id));
        const highlightedSet = new Set(highlightedSiteIds);

        for (const [id, prims] of primitivesBySiteId.entries()) {
            if (!currentIds.has(id)) {
                pointsCollection.remove(prims.point);
                labelsCollection.remove(prims.label);
                primitivesBySiteId.delete(id);
            }
        }

        for (const site of sites) {
            let prims = primitivesBySiteId.get(site.id);

            if (!prims) {
                const cartesian = Cesium.Cartesian3.fromDegrees(
                    site.rawLon,
                    site.rawLat,
                    site.rawAlt,
                    Cesium.Ellipsoid.MOON
                );

                const point = pointsCollection.add({
                    id: { siteId: site.id },
                    position: cartesian,
                    pixelSize: 12,
                    color: Cesium.Color.fromCssColorString('#eaeaea'),
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 2,
                    disableDepthTestDistance: Number.POSITIVE_INFINITY
                });

                const label = labelsCollection.add({
                    id: { siteId: site.id },
                    position: cartesian,
                    text: `${site.name}\nLat: ${site.lat}°, Lon: ${site.lon}°\nAlt: ${site.alt}m`,
                    font: '13px sans-serif',
                    fillColor: Cesium.Color.WHITE,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    pixelOffset: new Cesium.Cartesian2(0, -14),
                    disableDepthTestDistance: Number.POSITIVE_INFINITY
                });

                prims = { point, label };
                primitivesBySiteId.set(site.id, prims);
            }

            const isHighlighted = highlightedSet.has(site.id);
            prims.point.pixelSize = isHighlighted ? 16 : 12;
            prims.point.outlineWidth = isHighlighted ? 3 : 2;

            if (site.score !== null) {
                prims.point.color = Cesium.Color.fromCssColorString(getScoreHexColor(site.score));
                prims.label.text = `${site.name} (Score: ${site.score.toFixed(1)})\nLat: ${site.lat}°, Lon: ${site.lon}°\nAlt: ${site.alt}m`;
            }
        }
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
                onSelectSite(pickedObject.id.siteId);
                return;
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

            onAddSite({
                lat: Cesium.Math.toDegrees(cartographic.latitude),
                lon: Cesium.Math.toDegrees(cartographic.longitude),
                alt: cartographic.height
            });
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    });

    onDestroy(() => {
        primitivesBySiteId.clear();
        if (handler) handler.destroy();
        if (viewer && !viewer.isDestroyed()) viewer.destroy();
    });
</script>

<div id="cesiumContainer" style="transform: translateX({-rightInsetPx / 2}px);"></div>

<style>
    #cesiumContainer {
        width: 100vw;
        height: 100vh;
        margin: 0;
        padding: 0;
        overflow: hidden;
        transition: transform 0.25s ease;
        will-change: transform;
    }
</style>