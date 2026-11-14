<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import type { EarthEphemeris, SelectedSite } from './types';
    import {
        computeEarthPositionFromMoon,
        evaluateSiteAtTimestamp,
        getScoreHexColor
    } from './telemetry';

    export let sites: SelectedSite[] = [];
    export let highlightedSiteIds: number[] = [];
    export let rightInsetPx = 0;
    export let selectedTimeMs: number | null = null;
    export let isViewingEarth = false;
    export let onAddSite: (coords: { lat: number; lon: number; alt: number }) => void;
    export let onSelectSite: (siteId: number) => void;

    const MOON_RADIUS_M = 1737400;
    const EARTH_RADIUS_M = 6371000;
    const J2000_EPOCH_MS = Date.UTC(2000, 0, 1, 12, 0, 0);

    let viewer: any = null;
    let handler: any = null;
    let Cesium: any = null;
    let pointsCollection: any = null;
    let labelsCollection: any = null;
    let polylinesCollection: any = null;

    let earthPrimitive: any = null;
    let earthMaterial: any = null;
    let earthLabel: any = null;
    let subEarthPoint: any = null;
    let subEarthLabel: any = null;
    let earthEphemeris: EarthEphemeris | null = null;

    const primitivesBySiteId = new Map<number, { point: any; label: any }>();

    function getEarthCartesian(ephem: EarthEphemeris) {
        return Cesium.Cartesian3.fromDegrees(
            ephem.subEarthLonDeg,
            ephem.subEarthLatDeg,
            ephem.distanceM - MOON_RADIUS_M,
            Cesium.Ellipsoid.MOON
        );
    }

    function updateEarthInScene(timeMs: number) {
        if (!Cesium || !viewer || viewer.isDestroyed()) return;

        const ephem = computeEarthPositionFromMoon(timeMs);
        earthEphemeris = ephem;

        const earthPos = getEarthCartesian(ephem);

        // Sidereal Earth rotation (GMST: 360.985647° per solar day) + ~22° axial tilt in Moon frame
        const daysSinceJ2000 = (timeMs - J2000_EPOCH_MS) / 86400000;
        const gmstRad = Cesium.Math.toRadians((280.46061837 + 360.98564736629 * daysSinceJ2000) % 360);
        const tiltRad = Cesium.Math.toRadians(22.0);

        const spinRot = Cesium.Matrix3.fromRotationZ(gmstRad);
        const tiltRot = Cesium.Matrix3.fromRotationX(tiltRad);
        const earthRotMat = Cesium.Matrix3.multiply(tiltRot, spinRot, new Cesium.Matrix3());

        if (earthPrimitive) {
            earthPrimitive.modelMatrix = Cesium.Matrix4.fromRotationTranslation(
                earthRotMat,
                earthPos,
                new Cesium.Matrix4()
            );
        }

        if (earthMaterial) {
            const worldSunDir = Cesium.Cartesian3.fromDegrees(
                ephem.sunLonDeg,
                ephem.sunLatDeg,
                1000000,
                Cesium.Ellipsoid.MOON
            );
            Cesium.Cartesian3.normalize(worldSunDir, worldSunDir);

            // Transform world sun direction into Earth's rotating body frame so the terminator stays facing the Sun
            const invEarthRot = Cesium.Matrix3.transpose(earthRotMat, new Cesium.Matrix3());
            const localSunDir = Cesium.Matrix3.multiplyByVector(
                invEarthRot,
                worldSunDir,
                new Cesium.Cartesian3()
            );
            Cesium.Cartesian3.normalize(localSunDir, localSunDir);
            earthMaterial.uniforms.sunDirection = localSunDir;
        }

        if (earthLabel) {
            const labelPos = Cesium.Cartesian3.fromDegrees(
                ephem.subEarthLonDeg,
                ephem.subEarthLatDeg + 1.35,
                ephem.distanceM - MOON_RADIUS_M,
                Cesium.Ellipsoid.MOON
            );
            earthLabel.position = labelPos;
            earthLabel.text = `Earth • ${ephem.distanceKm.toLocaleString()} km\nSub-Earth: ${ephem.subEarthLatDeg.toFixed(1)}°, ${ephem.subEarthLonDeg.toFixed(1)}°`;
        }

        const subPos = Cesium.Cartesian3.fromDegrees(
            ephem.subEarthLonDeg,
            ephem.subEarthLatDeg,
            2500,
            Cesium.Ellipsoid.MOON
        );

        if (subEarthPoint) {
            subEarthPoint.position = subPos;
        }

        if (subEarthLabel) {
            subEarthLabel.position = subPos;
        }

        rebuildSightlines(timeMs, earthPos);
    }

    function rebuildSightlines(timeMs: number, earthPos: any) {
        if (!Cesium || !polylinesCollection) return;
        polylinesCollection.removeAll();

        const targetSites =
            highlightedSiteIds.length > 0
                ? sites.filter((s) => highlightedSiteIds.includes(s.id))
                : sites;

        for (const site of targetSites) {
            const evalData = evaluateSiteAtTimestamp(site, timeMs);
            if (!evalData.isEarthVisible) continue;

            const sitePos = Cesium.Cartesian3.fromDegrees(
                site.rawLon,
                site.rawLat,
                site.rawAlt,
                Cesium.Ellipsoid.MOON
            );

            polylinesCollection.add({
                positions: [sitePos, earthPos],
                width: 1.5,
                material: Cesium.Material.fromType('PolylineDash', {
                    color: Cesium.Color.fromCssColorString('#60a5fa').withAlpha(0.55),
                    dashLength: 16.0
                })
            });
        }
    }

    $: if (viewer && !viewer.isDestroyed() && Cesium && selectedTimeMs !== null) {
        viewer.clock.currentTime = Cesium.JulianDate.fromDate(new Date(selectedTimeMs));
        updateEarthInScene(selectedTimeMs);
    }

    $: if (Cesium && polylinesCollection && earthEphemeris && selectedTimeMs !== null && sites && highlightedSiteIds) {
        rebuildSightlines(selectedTimeMs, getEarthCartesian(earthEphemeris));
    }

    export function flyToSite(site: SelectedSite) {
        if (!viewer || !Cesium) return;
        isViewingEarth = false;

        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(
                site.rawLon,
                site.rawLat,
                Math.max(site.rawAlt + 150000, 50000),
                Cesium.Ellipsoid.MOON
            ),
            duration: 1.5
        });
    }

    export function flyToMoon() {
        if (!viewer || !Cesium) return;
        isViewingEarth = false;

        const targetLon = earthEphemeris?.subEarthLonDeg ?? 0;

        viewer.camera.flyTo({
            destination: Cesium.Cartesian3.fromDegrees(
                targetLon,
                10,
                4200000,
                Cesium.Ellipsoid.MOON
            ),
            duration: 1.5
        });
    }

    export function flyToEarth() {
        if (!viewer || !Cesium) return;
        isViewingEarth = true;

        const ephem =
            earthEphemeris ?? computeEarthPositionFromMoon(selectedTimeMs ?? Date.UTC(2026, 9, 1));
        const earthPos = getEarthCartesian(ephem);

        // Position camera above the northern limb so the Moon's curved horizon sits below Earth in the sky
        const camPos = Cesium.Cartesian3.fromDegrees(
            ephem.subEarthLonDeg,
            Math.min(82, ephem.subEarthLatDeg + 68),
            950000,
            Cesium.Ellipsoid.MOON
        );

        const direction = Cesium.Cartesian3.subtract(earthPos, camPos, new Cesium.Cartesian3());
        Cesium.Cartesian3.normalize(direction, direction);

        const up = Cesium.Cartesian3.normalize(camPos, new Cesium.Cartesian3());

        viewer.camera.flyTo({
            destination: camPos,
            orientation: { direction, up },
            duration: 1.6
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

        // Prevent Cesium's automatic frustum far plane from clipping Earth at ~384,400 km
        viewer.scene.preRender.addEventListener(() => {
            if (viewer && !viewer.isDestroyed() && viewer.camera?.frustum) {
                if (viewer.camera.frustum.far < 650000000) {
                    viewer.camera.frustum.far = 650000000;
                }
            }
        });

        try {
            const moonTileset = await Cesium.Cesium3DTileset.fromIonAssetId(2684829, {
                enableCollision: true
            });
            viewer.scene.primitives.add(moonTileset);
        } catch (error) {
            console.error('Failed to load Moon terrain tileset:', error);
        }

        // Procedural Earth shader with oceans, landmasses, cloud swirls, atmosphere, and solar phase
        earthMaterial = new Cesium.Material({
            fabric: {
                type: 'LunarSkyEarth',
                uniforms: {
                    sunDirection: new Cesium.Cartesian3(1, 0, 0)
                },
                source: `
                    float hash31(vec3 p) {
                        p = fract(p * 0.1031);
                        p += dot(p, p.yzx + 33.33);
                        return fract((p.x + p.y) * p.z);
                    }

                    float noise3D(vec3 p) {
                        vec3 i = floor(p);
                        vec3 f = fract(p);
                        f = f * f * (3.0 - 2.0 * f);
                        return mix(
                            mix(mix(hash31(i + vec3(0,0,0)), hash31(i + vec3(1,0,0)), f.x),
                                mix(hash31(i + vec3(0,1,0)), hash31(i + vec3(1,1,0)), f.x), f.y),
                            mix(mix(hash31(i + vec3(0,0,1)), hash31(i + vec3(1,0,1)), f.x),
                                mix(hash31(i + vec3(0,1,1)), hash31(i + vec3(1,1,1)), f.x), f.y),
                            f.z
                        );
                    }

                    float fbm(vec3 p) {
                        float v = 0.0;
                        float amp = 0.5;
                        for (int i = 0; i < 4; i++) {
                            v += amp * noise3D(p);
                            p *= 2.05;
                            amp *= 0.5;
                        }
                        return v;
                    }

                    czm_material czm_getMaterial(czm_materialInput materialInput) {
                        czm_material material = czm_getDefaultMaterial(materialInput);

                        float lon = (materialInput.st.x - 0.5) * 6.28318530718;
                        float lat = (materialInput.st.y - 0.5) * 3.14159265359;
                        vec3 unitSphere = vec3(
                            cos(lat) * cos(lon),
                            cos(lat) * sin(lon),
                            sin(lat)
                        );

                        float continent = fbm(unitSphere * 2.6 + vec3(1.4, -0.8, 0.5));
                        float clouds = fbm(unitSphere * 4.5 + vec3(-2.1, 1.7, 0.3));

                        vec3 oceanColor = vec3(0.05, 0.22, 0.58);
                        vec3 landColor = mix(vec3(0.14, 0.42, 0.20), vec3(0.58, 0.50, 0.32), smoothstep(0.52, 0.72, continent));
                        vec3 surface = mix(oceanColor, landColor, smoothstep(0.49, 0.53, continent));

                        // Polar ice caps
                        float polar = smoothstep(0.76, 0.90, abs(unitSphere.z));
                        surface = mix(surface, vec3(0.92, 0.95, 0.98), polar);

                        // Cloud layer
                        float cloudMask = smoothstep(0.54, 0.78, clouds);
                        surface = mix(surface, vec3(0.96, 0.98, 1.0), cloudMask * 0.85);

                        // Solar phase illumination
                        float ndotl = dot(unitSphere, normalize(sunDirection));
                        float dayFactor = smoothstep(-0.08, 0.14, ndotl);
                        vec3 litSurface = surface * (0.04 + 0.96 * dayFactor);

                        // Atmospheric Rayleigh limb glow
                        float viewDot = clamp(dot(normalize(materialInput.normalEC), vec3(0.0, 0.0, 1.0)), 0.0, 1.0);
                        float fresnel = pow(1.0 - viewDot, 3.0);
                        vec3 atmoColor = vec3(0.32, 0.65, 1.0) * fresnel * (0.12 + 0.88 * dayFactor);

                        material.diffuse = vec3(0.0);
                        material.emission = litSurface + atmoColor;
                        material.alpha = 1.0;
                        return material;
                    }
                `
            }
        });

        earthPrimitive = viewer.scene.primitives.add(
            new Cesium.Primitive({
                geometryInstances: new Cesium.GeometryInstance({
                    id: { isEarth: true },
                    geometry: new Cesium.EllipsoidGeometry({
                        radii: new Cesium.Cartesian3(
                            EARTH_RADIUS_M,
                            EARTH_RADIUS_M,
                            EARTH_RADIUS_M
                        ),
                        vertexFormat: Cesium.MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat
                    })
                }),
                appearance: new Cesium.MaterialAppearance({
                    material: earthMaterial,
                    translucent: false,
                    closed: true
                }),
                asynchronous: false
            })
        );

        polylinesCollection = viewer.scene.primitives.add(new Cesium.PolylineCollection());
        pointsCollection = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
        labelsCollection = viewer.scene.primitives.add(new Cesium.LabelCollection());

        earthLabel = labelsCollection.add({
            id: { isEarth: true },
            position: Cesium.Cartesian3.fromDegrees(0, 0, 384400000 - MOON_RADIUS_M, Cesium.Ellipsoid.MOON),
            text: 'Earth',
            font: '600 13px Rubik, sans-serif',
            fillColor: Cesium.Color.fromCssColorString('#93c5fd'),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -10)
        });

        subEarthPoint = pointsCollection.add({
            id: { isEarth: true },
            position: Cesium.Cartesian3.fromDegrees(0, 0, 2500, Cesium.Ellipsoid.MOON),
            pixelSize: 7,
            color: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.75),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 1.5
        });

        subEarthLabel = labelsCollection.add({
            id: { isEarth: true },
            position: Cesium.Cartesian3.fromDegrees(0, 0, 2500, Cesium.Ellipsoid.MOON),
            text: 'Sub-Earth Point',
            font: '11px Rubik, sans-serif',
            fillColor: Cesium.Color.fromCssColorString('#7dd3fc').withAlpha(0.85),
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.TOP,
            pixelOffset: new Cesium.Cartesian2(0, 8)
        });

        const initialTimeMs = selectedTimeMs ?? Date.UTC(2026, 9, 1, 0, 0);
        viewer.clock.currentTime = Cesium.JulianDate.fromDate(new Date(initialTimeMs));
        updateEarthInScene(initialTimeMs);

        handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);

        handler.setInputAction((movement: { position: any }) => {
            const pickedObject = viewer.scene.pick(movement.position);
            if (Cesium.defined(pickedObject)) {
                if (pickedObject.id?.isEarth) {
                    flyToEarth();
                    return;
                }
                if (pickedObject.id?.siteId !== undefined) {
                    isViewingEarth = false;
                    onSelectSite(pickedObject.id.siteId);
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

            isViewingEarth = false;
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

{#if earthEphemeris}
    <div class="earth-hud" title="Live selenocentric Earth coordinates for selected landing date">
        <span class="earth-dot"></span>
        <span>
            Earth: <strong>{earthEphemeris.subEarthLatDeg.toFixed(1)}°, {earthEphemeris.subEarthLonDeg.toFixed(1)}°</strong>
            · {earthEphemeris.distanceKm.toLocaleString()} km
        </span>
    </div>
{/if}

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

    .earth-hud {
        position: absolute;
        top: 62px;
        left: 20px;
        z-index: 10;
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        background-color: rgba(7, 7, 7, 0.78);
        backdrop-filter: blur(6px);
        border: 1px solid rgba(96, 165, 250, 0.28);
        border-radius: 999px;
        padding: 0.28rem 0.7rem;
        font-size: 0.72rem;
        color: rgba(234, 234, 234, 0.88);
        pointer-events: none;
    }

    .earth-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #93c5fd, #2563eb);
        box-shadow: 0 0 6px rgba(96, 165, 250, 0.8);
    }
</style>