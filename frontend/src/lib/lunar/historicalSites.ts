import type { HistoricalLandingSite } from './types';

/**
 * Verified selenographic coordinates of 28 soft lunar landing missions.
 * Primary Source: NASA NSSDCA & LROC (Lunar Reconnaissance Orbiter Camera)
 * Verified Lunar Landing Site Coordinates Catalog.
 */
export const HISTORICAL_LANDING_SITES_SOURCE =
    'NASA NSSDCA & LROC Verified Lunar Landing Site Coordinates';

export const HISTORICAL_LANDING_SITES: HistoricalLandingSite[] = [
    {
        id: 'luna-9',
        name: 'Luna 9',
        region: 'Oceanus Procellarum',
        agency: 'USSR',
        year: 1966,
        lat: 7.08,
        lon: -64.37,
        summary: 'First spacecraft to achieve a survivable soft landing on the Moon.'
    },
    {
        id: 'surveyor-1',
        name: 'Surveyor 1',
        region: 'Oceanus Procellarum (Flamsteed)',
        agency: 'USA / NASA',
        year: 1966,
        lat: -2.474,
        lon: -43.339,
        summary: 'First US soft lunar landing; validated radar-controlled terminal descent.'
    },
    {
        id: 'luna-13',
        name: 'Luna 13',
        region: 'Oceanus Procellarum',
        agency: 'USSR',
        year: 1966,
        lat: 18.87,
        lon: -62.05,
        summary: 'Conducted early regolith mechanical density and radiation measurements.'
    },
    {
        id: 'surveyor-3',
        name: 'Surveyor 3',
        region: 'Oceanus Procellarum',
        agency: 'USA / NASA',
        year: 1967,
        lat: -3.015,
        lon: -23.418,
        summary: 'Landed inside a shallow crater; later visited by the Apollo 12 crew.'
    },
    {
        id: 'surveyor-5',
        name: 'Surveyor 5',
        region: 'Mare Tranquillitatis',
        agency: 'USA / NASA',
        year: 1967,
        lat: 1.461,
        lon: 23.195,
        summary: 'Performed the first in-situ alpha-scattering chemical analysis of mare basalt.'
    },
    {
        id: 'surveyor-6',
        name: 'Surveyor 6',
        region: 'Sinus Medii',
        agency: 'USA / NASA',
        year: 1967,
        lat: 0.473,
        lon: -1.427,
        summary: 'Executed the first controlled liftoff and translation hop on the lunar surface.'
    },
    {
        id: 'surveyor-7',
        name: 'Surveyor 7',
        region: 'Tycho Crater Rim',
        agency: 'USA / NASA',
        year: 1968,
        lat: -40.893,
        lon: -11.442,
        summary: 'Highland ejecta landing north of Tycho crater.'
    },
    {
        id: 'apollo-11',
        name: 'Apollo 11',
        region: 'Mare Tranquillitatis',
        agency: 'USA / NASA',
        year: 1969,
        lat: 0.6741,
        lon: 23.473,
        isDefaultPreset: true,
        summary: 'Tranquility Base — first crewed lunar landing; flat equatorial mare baseline.'
    },
    {
        id: 'apollo-12',
        name: 'Apollo 12',
        region: 'Oceanus Procellarum',
        agency: 'USA / NASA',
        year: 1969,
        lat: -3.0124,
        lon: -23.4216,
        summary: 'Pinpoint landing 163 m from Surveyor 3 in eastern Oceanus Procellarum.'
    },
    {
        id: 'luna-16',
        name: 'Luna 16',
        region: 'Mare Fecunditatis',
        agency: 'USSR',
        year: 1970,
        lat: -0.5137,
        lon: 56.3638,
        summary: 'First robotic sample-return mission from the lunar surface.'
    },
    {
        id: 'luna-17',
        name: 'Luna 17 (Lunokhod 1)',
        region: 'Mare Imbrium',
        agency: 'USSR',
        year: 1970,
        lat: 38.2378,
        lon: -35.0017,
        summary: 'Deployed Lunokhod 1, the first remote-controlled planetary rover.'
    },
    {
        id: 'apollo-14',
        name: 'Apollo 14',
        region: 'Fra Mauro Highlands',
        agency: 'USA / NASA',
        year: 1971,
        lat: -3.6453,
        lon: -17.4714,
        summary: 'Sampled Imbrium basin ejecta blanket in the Fra Mauro formation.'
    },
    {
        id: 'apollo-15',
        name: 'Apollo 15',
        region: 'Hadley–Apennine',
        agency: 'USA / NASA',
        year: 1971,
        lat: 26.1322,
        lon: 3.6339,
        isDefaultPreset: true,
        summary: 'First J-mission with the Lunar Roving Vehicle beside Hadley Rille and Mons Hadley.'
    },
    {
        id: 'luna-20',
        name: 'Luna 20',
        region: 'Apollonius Highlands',
        agency: 'USSR',
        year: 1972,
        lat: 3.7863,
        lon: 56.6242,
        summary: 'Robotic core sample return from highland terrain north of Mare Fecunditatis.'
    },
    {
        id: 'apollo-16',
        name: 'Apollo 16',
        region: 'Descartes Highlands',
        agency: 'USA / NASA',
        year: 1972,
        lat: -8.973,
        lon: 15.5002,
        summary: 'Only Apollo mission to land in the rugged central lunar highlands.'
    },
    {
        id: 'apollo-17',
        name: 'Apollo 17',
        region: 'Taurus–Littrow Valley',
        agency: 'USA / NASA',
        year: 1972,
        lat: 20.1908,
        lon: 30.7717,
        isDefaultPreset: true,
        summary: 'Final Apollo crewed landing; deep highland-ringed valley on southeastern Mare Serenitatis.'
    },
    {
        id: 'luna-21',
        name: 'Luna 21 (Lunokhod 2)',
        region: 'Le Monnier Crater',
        agency: 'USSR',
        year: 1973,
        lat: 25.8323,
        lon: 30.4076,
        summary: 'Deployed Lunokhod 2 along the eastern margin of Mare Serenitatis.'
    },
    {
        id: 'luna-24',
        name: 'Luna 24',
        region: 'Mare Crisium',
        agency: 'USSR',
        year: 1976,
        lat: 12.7145,
        lon: 62.2129,
        summary: 'Deep-drill robotic sample return from southeastern Mare Crisium.'
    },
    {
        id: 'change-3',
        name: "Chang'e 3 (Yutu)",
        region: 'Mare Imbrium',
        agency: 'China / CNSA',
        year: 2013,
        lat: 44.1214,
        lon: -19.5116,
        summary: 'First soft landing on the Moon in 37 years; deployed the Yutu rover.'
    },
    {
        id: 'change-4',
        name: "Chang'e 4 (Yutu-2)",
        region: 'Von Kármán Crater (Far Side)',
        agency: 'China / CNSA',
        year: 2019,
        lat: -45.4561,
        lon: 177.5885,
        isDefaultPreset: true,
        summary: 'First soft landing on the lunar far side inside South Pole–Aitken basin (requires relay LOS).'
    },
    {
        id: 'change-5',
        name: "Chang'e 5",
        region: 'Mons Rümker',
        agency: 'China / CNSA',
        year: 2020,
        lat: 43.0576,
        lon: -51.9161,
        summary: 'Returned young mare basalt samples from northern Oceanus Procellarum.'
    },
    {
        id: 'chandrayaan-3',
        name: 'Chandrayaan-3 (Vikram)',
        region: 'Shiv Shakti Point (South Pole)',
        agency: 'India / ISRO',
        year: 2023,
        lat: -69.3733,
        lon: 32.3191,
        isDefaultPreset: true,
        summary: 'First soft landing in the lunar south polar region; deployed Pragyan rover.'
    },
    {
        id: 'slim',
        name: 'SLIM',
        region: 'Shioli Crater Rim',
        agency: 'Japan / JAXA',
        year: 2024,
        lat: -13.316,
        lon: 25.251,
        summary: 'Demonstrated sub-100m pinpoint vision-based landing on a sloped crater rim.'
    },
    {
        id: 'odysseus-im1',
        name: 'Odysseus (IM-1)',
        region: 'Malapert A (South Pole)',
        agency: 'USA / Intuitive Machines',
        year: 2024,
        lat: -80.13,
        lon: 1.44,
        summary: 'First commercial soft landing and southernmost touchdown at 80.13° S.'
    },
    {
        id: 'change-6',
        name: "Chang'e 6",
        region: 'Apollo Basin (Far Side)',
        agency: 'China / CNSA',
        year: 2024,
        lat: -41.6385,
        lon: -153.9852,
        summary: 'First robotic sample return from the lunar far side.'
    },
    {
        id: 'blue-ghost-m1',
        name: 'Blue Ghost M1',
        region: 'Mare Crisium',
        agency: 'USA / Firefly',
        year: 2025,
        lat: 18.562,
        lon: 61.81,
        summary: 'CLPS commercial lander operating across a full lunar day near Mons Latreille.'
    },
    {
        id: 'athena-im2',
        name: 'Athena (IM-2)',
        region: 'Mons Mouton (South Pole)',
        agency: 'USA / Intuitive Machines',
        year: 2025,
        lat: -84.79,
        lon: 29.19,
        summary: 'South polar plateau landing site evaluated for volatile prospecting.'
    },
    {
        id: 'resilience-m2',
        name: 'Resilience (Hakuto-R M2)',
        region: 'Mare Frigoris',
        agency: 'Japan / ispace',
        year: 2025,
        lat: 60.44,
        lon: -4.59,
        summary: 'High-latitude northern mare target in central Mare Frigoris.'
    }
];

export const DEFAULT_PRESET_LANDING_SITES: HistoricalLandingSite[] =
    HISTORICAL_LANDING_SITES.filter((s) => s.isDefaultPreset).slice(0, 5);

export function searchHistoricalLandingSites(
    query: string,
    sites: HistoricalLandingSite[] = HISTORICAL_LANDING_SITES
): HistoricalLandingSite[] {
    const trimmed = query.trim().toLowerCase();
    if (!trimmed) return sites;

    return sites.filter((site) => {
        const haystack =
            `${site.name} ${site.region} ${site.agency} ${site.year} ${site.lat.toFixed(2)} ${site.lon.toFixed(2)}`.toLowerCase();
        return haystack.includes(trimmed);
    });
}