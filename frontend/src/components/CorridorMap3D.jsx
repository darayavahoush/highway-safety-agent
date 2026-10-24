import { useEffect, useRef, useState, useMemo, useCallback } from 'react'
import {
  Compass,
  Layers,
  RotateCcw,
  Navigation,
  AlertTriangle,
  Hospital as HospitalIcon,
  PhoneCall,
  Activity,
  Mountain,
  Eye,
  Info,
  Maximize2
} from 'lucide-react'
import RegionalWeather from './RegionalWeather.jsx'
import { AP_BOUNDARY } from '../data/apBoundary.js'
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'


// Turn a road polyline into a thin ground-hugging polygon so it can be raised in 3D.
function roadRibbon(coords, half) {
  const n = coords.length
  if (n < 2) return null
  const left = []
  const right = []
  for (let i = 0; i < n; i += 1) {
    const [lng, lat] = coords[i]
    const a = coords[Math.max(0, i - 1)]
    const b = coords[Math.min(n - 1, i + 1)]
    const k = Math.cos((lat * Math.PI) / 180) || 1
    const dx = (b[0] - a[0]) * k
    const dy = b[1] - a[1]
    const len = Math.hypot(dx, dy) || 1
    const nx = -dy / len
    const ny = dx / len
    left.push([lng + (nx * half) / k, lat + ny * half])
    right.push([lng - (nx * half) / k, lat - ny * half])
  }
  return [...left, ...right.reverse(), left[0]]
}

// A small square footprint, used for tall 3D beacon pillars.
function pillar(lng, lat, size = 0.003) {
  const k = Math.cos((lat * Math.PI) / 180) || 1
  const dx = size / k
  return [[lng - dx, lat - size], [lng + dx, lat - size], [lng + dx, lat + size], [lng - dx, lat + size], [lng - dx, lat - size]]
}

// Default Andhra Pradesh Highway Corridors & Designated Trauma Network
const DEFAULT_CORRIDORS = [
  {
    id: 'AP-NH16-CENTRAL',
    highway: 'NH-16',
    name: 'Amaravati - Vijayawada - Guntur Capital Region',
    districts: ['NTR', 'Guntur'],
    blackspots: 255, // 197 NTR + 58 Guntur (MoRTH/IITK Inventory)
    center: [80.60, 16.45],
    zoom: 11,
    coordinates: [
      [80.6480, 16.5186], // Kanakadurga Varadhi / Vijayawada
      [80.6210, 16.4820], // Tadepalle Bypass
      [80.5750, 16.4500], // Mangalagiri Bypass
      [80.5350, 16.4020], // Kaza Toll Plaza (KM 42.4)
      [80.4900, 16.3550], // Namburu Stretch
      [80.4431, 16.3007], // Guntur Outer Ring
    ],
  },
  {
    id: 'AP-NH44-SOUTH',
    highway: 'NH-44',
    name: 'Rayalaseema North-South Corridor (Kurnool - Anantapur)',
    districts: ['Kurnool', 'Anantapur'],
    blackspots: 87,
    center: [77.75, 15.20],
    zoom: 9,
    coordinates: [
      [78.0381, 15.8281], // Kurnool
      [77.8720, 15.4200], // Dhone
      [77.6350, 15.1100], // Gooty
      [77.6000, 14.6800], // Anantapur
    ],
  },
  {
    id: 'AP-NH16-NORTH',
    highway: 'NH-16',
    name: 'North Coastal Corridor (Visakhapatnam - Anakapalli)',
    districts: ['Visakhapatnam', 'Anakapalli'],
    blackspots: 164, // 131 Vizag + 33 Anakapalli
    center: [83.20, 17.75],
    zoom: 10,
    coordinates: [
      [83.0050, 17.6850], // Anakapalli
      [83.2120, 17.7250], // Gajuwaka / Steel Plant
      [83.3039, 17.7088], // Visakhapatnam City
      [83.4250, 17.9250], // Tagarapuvalasa
    ],
  },
]

const DEFAULT_HOSPITALS = [
  {
    id: 'aiims-mangalagiri',
    name: 'AIIMS Mangalagiri',
    type: 'Level 1 Apex Trauma Center (24/7)',
    contact: '08645-280021 / 108',
    coordinates: [80.5594, 16.4412],
    district: 'Guntur District',
    verified: true,
  },
  {
    id: 'ggh-guntur',
    name: 'GGH Guntur',
    type: 'Tertiary Trauma Care Center',
    contact: 'Dial 108',
    coordinates: [80.4431, 16.3007],
    district: 'Guntur City',
    verified: true,
  },
  {
    id: 'ggh-vijayawada',
    name: 'GGH Vijayawada (New Govt Hospital)',
    type: 'Trauma & Acute Emergency',
    contact: 'Dial 108',
    coordinates: [80.6480, 16.5186],
    district: 'NTR District',
    verified: true,
  },
  {
    id: 'kgh-vizag',
    name: 'King George Hospital (KGH)',
    type: 'Super Speciality Trauma Care',
    contact: 'Dial 108',
    coordinates: [83.3039, 17.7088],
    district: 'Visakhapatnam',
    verified: true,
  },
  {
    id: 'ggh-kurnool',
    name: 'GGH Kurnool',
    type: 'Regional Trauma Center',
    contact: 'Dial 108',
    coordinates: [78.0381, 15.8281],
    district: 'Kurnool',
    verified: true,
  },
]

const DEFAULT_CAMERA = {
  id: 'CAM-AP-NH16-KM42',
  highway: 'NH-16',
  section: 'Vijayawada - Guntur Stretch (Kaza Toll)',
  chainage: 'KM 42.4',
  coordinates: [80.5350, 16.4020],
}

// Haversine straight-line distance helper (km)
function haversineKm([lon1, lat1], [lon2, lat2]) {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2)
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

// Return only explicit incident coordinates. Coordinate arrays use GeoJSON order:
// [longitude, latitude]. Camera coordinates are intentionally not a fallback.
function getIncidentCoordinates(incident) {
  if (!incident || typeof incident !== 'object') return null

  const candidates = [
    [incident.lng, incident.lat],
    [incident.longitude, incident.latitude],
    [incident.gps?.longitude, incident.gps?.latitude],
    [incident.gps?.lng, incident.gps?.lat],
    [incident.location?.longitude, incident.location?.latitude],
    [incident.location?.lng, incident.location?.lat],
  ]

  // Accept an explicit incident-level GeoJSON coordinate pair.
  if (Array.isArray(incident.coordinates) && incident.coordinates.length >= 2) {
    candidates.unshift([incident.coordinates[0], incident.coordinates[1]])
  }

  for (const pair of candidates) {
    if (pair[0] == null || pair[1] == null || pair[0] === '' || pair[1] === '') {
      continue
    }

    const lng = Number(pair[0])
    const lat = Number(pair[1])

    if (
      Number.isFinite(lng) &&
      Number.isFinite(lat) &&
      lng >= 76.5 && lng <= 85.5 &&
      lat >= 12 && lat <= 20
    ) {
      return [lng, lat]
    }
  }

  return null
}

export default function CorridorMap3D({

  incidents = [],
  selectedIncident = null,
  onSelectIncident,
  camera = null,
  onCorridorInfo,
}) {
  const maplibreglShared = useRef(null)
  const mapContainerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef([])
  const orbitIntervalRef = useRef(null)

  const [activeCorridorId, setActiveCorridorId] = useState('AP-NH16-NORTH')
  const [styleMode, setStyleMode] = useState('bright') // 'dark' | 'bright'
  const [terrainEnabled, setTerrainEnabled] = useState(true)
  const [terrainStatus, setTerrainStatus] = useState('loading')
  const [terrainError, setTerrainError] = useState('')
  const [terrainRetry, setTerrainRetry] = useState(0)
  const [isOrbiting, setIsOrbiting] = useState(false)
  const [mapLoaded, setMapLoaded] = useState(false)
  const [webGlFailed, setWebGlFailed] = useState(false)
  const [hospitals] = useState(DEFAULT_HOSPITALS)
  const [traumaRoute, setTraumaRoute] = useState(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [weatherPoint, setWeatherPoint] = useState({
    coordinates: DEFAULT_CORRIDORS[0].center,
    name: 'Amaravati · Vijayawada · Guntur',
  })

  const activeCorridor = useMemo(
    () => DEFAULT_CORRIDORS.find((c) => c.id === activeCorridorId) || DEFAULT_CORRIDORS[0],
    [activeCorridorId]
  )

  // Keep the sitewide intelligence rail in sync with the map's selected corridor,
  // clicked weather point, and terrain toggle.
  useEffect(() => {
    onCorridorInfo?.({
      id: activeCorridor.id,
      highway: activeCorridor.highway,
      name: activeCorridor.name,
      districts: activeCorridor.districts,
      blackspots: activeCorridor.blackspots,
      center: activeCorridor.center,
      zoom: activeCorridor.zoom,
      weatherCoordinates: weatherPoint.coordinates,
      weatherName: weatherPoint.name,
      terrainEnabled,
      terrainStatus,
      terrainError,
    })
  }, [activeCorridor, weatherPoint, terrainEnabled, terrainStatus, terrainError, onCorridorInfo])

  const sentryCamera = useMemo(() => {
    if (camera && camera.lng && camera.lat) {
      return {
        id: camera.id || 'CAM-AP-NH16-KM42',
        highway: camera.highway || 'NH-16',
        section: `${camera.towards || 'Visakhapatnam'} Corridor`,
        chainage: `KM ${camera.km || '42.4'}`,
        coordinates: [camera.lng, camera.lat],
      }
    }
    return DEFAULT_CAMERA
  }, [camera])

  // Style URLs
  const currentStyleUrl = useMemo(() => {
    return styleMode === 'dark'
      ? 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
      : 'https://tiles.openfreemap.org/styles/bright'
  }, [styleMode])

  // Find nearest hospital for selected or target coordinates
  const findNearestHospital = useCallback(
    (coords) => {
      if (!coords || coords.length < 2) return hospitals[0]
      let bestHosp = hospitals[0]
      let minDist = Infinity
      hospitals.forEach((hosp) => {
        const d = haversineKm(coords, hosp.coordinates)
        if (d < minDist) {
          minDist = d
          bestHosp = hosp
        }
      })
      return { hospital: bestHosp, distanceKm: minDist }
    },
    [hospitals]
  )

  // Fetch or calculate trauma route from incident to hospital
  const calculateTraumaRoute = useCallback(
    async (incCoords, targetHospital) => {
      if (!incCoords || !targetHospital) return
      setRouteLoading(true)
      const straightDist = haversineKm(incCoords, targetHospital.coordinates)
      const fallbackEtaMins = Math.max(3, Math.round((straightDist / 60) * 60))

      try {
        const url = `https://router.project-osrm.org/route/v1/driving/${incCoords[0]},${incCoords[1]};${targetHospital.coordinates[0]},${targetHospital.coordinates[1]}?overview=full&geometries=geojson`
        const res = await fetch(url)
        if (res.ok) {
          const data = await res.json()
          if (data.routes && data.routes.length > 0) {
            const r = data.routes[0]
            const distKm = (r.distance / 1000).toFixed(1)
            const durationMin = Math.round(r.duration / 60)
            setTraumaRoute({
              type: 'osrm',
              geometry: r.geometry,
              distanceKm: distKm,
              durationMin: durationMin,
              hospital: targetHospital,
            })
            setRouteLoading(false)
            return
          }
        }
      } catch (err) {
        // Fallback to straight line estimate if network or OSRM unavailable
      }

      setTraumaRoute({
        type: 'estimate',
        geometry: {
          type: 'LineString',
          coordinates: [incCoords, targetHospital.coordinates],
        },
        distanceKm: straightDist.toFixed(1),
        durationMin: fallbackEtaMins,
        hospital: targetHospital,
      })
      setRouteLoading(false)
    },
    []
  )

  // Initialize MapLibre GL
  useEffect(() => {
    setMapLoaded(false)
    setTerrainStatus('loading')
    let mapInstance = null

    async function initMap() {
      try {
        const module = await import('maplibre-gl')
        maplibreglShared.current = module.default ?? module
        maplibreglShared.current.setWorkerUrl(maplibreWorkerUrl)

        if (
          typeof maplibreglShared.current.supported === 'function' &&
          !maplibreglShared.current.supported()
        ) {
          setWebGlFailed(true)
          return
        }

        mapInstance = new maplibreglShared.current.Map({
          container: mapContainerRef.current,
          style: currentStyleUrl,
          center: activeCorridor.center,
          zoom: activeCorridor.zoom,
          pitch: terrainEnabled ? 66 : 0,
          bearing: -18,
          maxPitch: 78,
          minZoom: 5.6,
          maxBounds: [[AP_BOUNDARY.bounds[0] - 1.6, AP_BOUNDARY.bounds[1] - 1.4], [AP_BOUNDARY.bounds[2] + 1.6, AP_BOUNDARY.bounds[3] + 1.4]],
          antialias: true,
          attributionControl: { compact: true },
        })

        mapInstance.addControl(new maplibreglShared.current.NavigationControl({ visualizePitch: true }), 'top-right')

        mapInstance.on('load', () => {
          setMapLoaded(true)
        })

        mapInstance.on('error', () => {
          // If tile loading completely fails, show fallback schematic
        })

        mapRef.current = mapInstance
      } catch (err) {
        console.warn('MapLibre GL failed to initialize:', err)
        setWebGlFailed(true)
      }
    }

    initMap()

    const timeout = setTimeout(() => {
      if (!mapRef.current) setWebGlFailed(true)
    }, 8000)

    return () => {
      clearTimeout(timeout)
      if (orbitIntervalRef.current) clearInterval(orbitIntervalRef.current)
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [currentStyleUrl])

  // Click any open map area to inspect weather at that coordinate.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return

    const handleWeatherPoint = (event) => {
      const lng = Number(event.lngLat.lng.toFixed(4))
      const lat = Number(event.lngLat.lat.toFixed(4))
      setWeatherPoint({
        coordinates: [lng, lat],
        name: `Selected map point · ${activeCorridor.highway}`,
      })
    }

    map.on('click', handleWeatherPoint)
    return () => map.off('click', handleWeatherPoint)
  }, [mapLoaded, activeCorridor])

  // Keep DEM installation, hillshade, terrain mesh, camera pitch, and status in sync.
  // AWS Terrarium is a global, no-key raster DEM; no demo-only Alpine coverage is used.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return undefined

    const sourceId = 'terrain-source'
    const hillshadeId = 'terrain-hillshade'
    let disposed = false

    const onTerrainError = (event) => {
      const sourceIdFromError = event?.sourceId || event?.source?.id
      if (sourceIdFromError !== sourceId) return
      if (disposed) return
      setTerrainStatus('unavailable')
      setTerrainError(event?.error?.message || 'Elevation tiles could not be loaded. Check network access and retry.')
    }
    map.on('error', onTerrainError)

    try {
      if (!terrainEnabled) {
        map.setTerrain(null)
        if (map.getLayer(hillshadeId)) map.removeLayer(hillshadeId)
        if (Math.abs(map.getPitch()) > 1) map.easeTo({ pitch: 0, duration: 450 })
        setTerrainStatus('off')
        setTerrainError('')
      } else {
        setTerrainStatus('loading')
        setTerrainError('')
        if (!map.getSource(sourceId)) {
          map.addSource(sourceId, {
            type: 'raster-dem',
            tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
            encoding: 'terrarium',
            tileSize: 256,
            minzoom: 0,
            maxzoom: 15,
            attribution: 'Elevation: AWS Open Data / Terrain Tiles (Terrarium)',
          })
        }

        // Hillshade makes subtle elevation visible even before strong terrain relief loads.
        if (!map.getLayer(hillshadeId)) {
          const firstSymbol = map.getStyle()?.layers?.find((layer) => layer.type === 'symbol')?.id
          map.addLayer({
            id: hillshadeId,
            type: 'hillshade',
            source: sourceId,
            paint: {
              'hillshade-exaggeration': 0.85,
              'hillshade-shadow-color': '#142637',
              'hillshade-highlight-color': '#c7d8e6',
              'hillshade-accent-color': '#526a7c',
              'hillshade-illumination-direction': 335,
            },
          }, firstSymbol)
        }
        map.setTerrain({ source: sourceId, exaggeration: 3.4 })
        if (map.getPitch() < 58) map.easeTo({ pitch: 64, bearing: -18, duration: 650 })

        // Extruded buildings when the basemap carries building footprints.
        const styleSources = map.getStyle()?.sources || {}
        const vecSource = styleSources.openmaptiles ? 'openmaptiles' : Object.keys(styleSources).find((k) => styleSources[k].type === 'vector')
        if (vecSource && !map.getLayer('hrap-3d-buildings')) {
          try {
            map.addLayer({
              id: 'hrap-3d-buildings', type: 'fill-extrusion', source: vecSource, 'source-layer': 'building', minzoom: 13,
              paint: {
                'fill-extrusion-color': '#d6c3ad',
                'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 12],
                'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
                'fill-extrusion-opacity': 0.85,
              },
            })
          } catch (e) { /* basemap has no building layer; skip */ }
        }

        // Report active only after the terrain API accepted the configuration.
        setTerrainStatus('active')
      }
    } catch (error) {
      console.warn('[HRAP] 3D terrain setup failed:', error)
      const busy = /not done loading|style is not|not loaded/i.test(error?.message || '')
      if (busy && terrainRetry < 5) {
        // The basemap was still busy: try again as soon as it is idle.
        map.once('idle', () => { if (!disposed) setTerrainRetry((n) => n + 1) })
      } else {
        setTerrainStatus('unavailable')
        setTerrainError(error?.message || 'The terrain renderer could not be activated.')
      }
    }

    return () => {
      disposed = true
      map.off('error', onTerrainError)
    }
  }, [terrainEnabled, mapLoaded, currentStyleUrl, terrainRetry])

  // Andhra Pradesh only: black out everything outside the state, outline AP, faint district lines.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return
    try {
      if (!map.getSource('ap-mask-src')) {
        const world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]]
        const geom = AP_BOUNDARY.state.geometry
        const polys = geom.type === 'MultiPolygon' ? geom.coordinates : [geom.coordinates]
        const holes = polys.map((poly) => poly[0])
        map.addSource('ap-mask-src', {
          type: 'geojson',
          data: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [world, ...holes] } },
        })
        map.addSource('ap-outline-src', { type: 'geojson', data: AP_BOUNDARY.state })
        map.addSource('ap-districts-src', { type: 'geojson', data: AP_BOUNDARY.districts })
        map.addLayer({ id: 'ap-mask', type: 'fill', source: 'ap-mask-src', paint: { 'fill-color': '#04070d', 'fill-opacity': 1 } })
        map.addLayer({ id: 'ap-districts', type: 'line', source: 'ap-districts-src', paint: { 'line-color': '#ffffff', 'line-opacity': 0.28, 'line-width': 0.8 } })
        map.addLayer({ id: 'ap-outline-glow', type: 'line', source: 'ap-outline-src', paint: { 'line-color': '#ffb454', 'line-width': 8, 'line-opacity': 0.28, 'line-blur': 5 } })
        map.addLayer({ id: 'ap-outline', type: 'line', source: 'ap-outline-src', paint: { 'line-color': '#ffd08a', 'line-width': 2, 'line-opacity': 0.95 } })
      }
    } catch (err) {
      console.warn('[HRAP] AP mask setup failed:', err)
    }
  }, [mapLoaded, currentStyleUrl])

  // Draw Corridors, Camera, and Trauma Routes on Map
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return

    // 1. Draw Highway Corridor Lines
    const corridorGeoJson = {
      type: 'FeatureCollection',
      features: DEFAULT_CORRIDORS.map((c) => ({
        type: 'Feature',
        properties: {
          id: c.id,
          name: c.name,
          highway: c.highway,
          blackspots: c.blackspots,
          isActive: c.id === activeCorridorId,
        },
        geometry: {
          type: 'LineString',
          coordinates: c.coordinates,
        },
      })),
    }

    if (map.getSource('corridors-src')) {
      map.getSource('corridors-src').setData(corridorGeoJson)
    } else {
      map.addSource('corridors-src', {
        type: 'geojson',
        data: corridorGeoJson,
      })

      // Corridor glow casing
      map.addLayer({
        id: 'corridor-glow',
        type: 'line',
        source: 'corridors-src',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': ['case', ['get', 'isActive'], '#ef4444', '#38bdf8'],
          'line-width': ['case', ['get', 'isActive'], 10, 5],
          'line-opacity': 0.35,
          'line-blur': 4,
        },
      })

      // Corridor core line
      map.addLayer({
        id: 'corridor-core',
        type: 'line',
        source: 'corridors-src',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': ['case', ['get', 'isActive'], '#f59e0b', '#0284c7'],
          'line-width': ['case', ['get', 'isActive'], 4, 2.5],
          'line-opacity': 0.95,
        },
      })
    }

    // 1b. Raise the roads in 3D so highways stand up from the terrain.
    try {
      const ribbons = {
        type: 'FeatureCollection',
        features: DEFAULT_CORRIDORS.map((c) => {
          const isActive = c.id === activeCorridorId
          const ring = roadRibbon(c.coordinates, isActive ? 0.0022 : 0.0014)
          return ring ? { type: 'Feature', properties: { isActive }, geometry: { type: 'Polygon', coordinates: [ring] } } : null
        }).filter(Boolean),
      }
      if (map.getSource('corridors-3d-src')) {
        map.getSource('corridors-3d-src').setData(ribbons)
      } else {
        map.addSource('corridors-3d-src', { type: 'geojson', data: ribbons })
        map.addLayer({
          id: 'corridor-3d',
          type: 'fill-extrusion',
          source: 'corridors-3d-src',
          paint: {
            'fill-extrusion-color': ['case', ['get', 'isActive'], '#ffb347', '#38a6ff'],
            'fill-extrusion-height': ['case', ['get', 'isActive'], 320, 190],
            'fill-extrusion-base': 0,
            'fill-extrusion-opacity': 0.92,
          },
        })
      }
    } catch (err) {
      console.warn('[HRAP] 3D road layer failed:', err)
    }

    // 2. Draw Trauma Care Route
    if (traumaRoute && traumaRoute.geometry) {
      const routeGeoJson = {
        type: 'Feature',
        geometry: traumaRoute.geometry,
      }
      if (map.getSource('trauma-route-src')) {
        map.getSource('trauma-route-src').setData(routeGeoJson)
      } else {
        map.addSource('trauma-route-src', {
          type: 'geojson',
          data: routeGeoJson,
        })
        map.addLayer({
          id: 'trauma-route-glow',
          type: 'line',
          source: 'trauma-route-src',
          paint: {
            'line-color': '#10b981',
            'line-width': 8,
            'line-opacity': 0.45,
            'line-blur': 3,
          },
        })
        map.addLayer({
          id: 'trauma-route-core',
          type: 'line',
          source: 'trauma-route-src',
          paint: {
            'line-color': '#34d399',
            'line-width': 3.5,
            'line-dasharray': [2, 1],
            'line-opacity': 1.0,
          },
        })
      }
    } else if (map.getLayer('trauma-route-core')) {
      map.removeLayer('trauma-route-core')
      map.removeLayer('trauma-route-glow')
      map.removeSource('trauma-route-src')
    }
  }, [mapLoaded, activeCorridorId, traumaRoute])

  // Place HTML Markers for Sentry Camera, Hospitals, and Incidents
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapLoaded) return

    // Clean up previous markers
    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []

    Promise.resolve().then(() => {

      // 1. Sentry Camera Marker
      const camEl = document.createElement('div')
      camEl.className = 'corridor-marker corridor-marker--camera'
      camEl.innerHTML = `
        <div class="cam-beacon" title="${sentryCamera.id}: ${sentryCamera.section}">
          <div class="cam-pulse"></div>
          <div class="cam-icon">📹</div>
          <span class="marker-tag">Sentry: ${sentryCamera.chainage}</span>
        </div>
      `
      camEl.onclick = () => {
        map.flyTo({ center: sentryCamera.coordinates, zoom: 14, pitch: 0 })
      }
      const camMarker = new maplibreglShared.current.Marker({ element: camEl })
        .setLngLat(sentryCamera.coordinates)
        .addTo(map)
      markersRef.current.push(camMarker)

      // 2. Tertiary Trauma Hospital Markers
      hospitals.forEach((hosp) => {
        const hospEl = document.createElement('div')
        hospEl.className = 'corridor-marker corridor-marker--hospital'
        hospEl.innerHTML = `
          <div class="hosp-beacon" title="${hosp.name} (${hosp.type})">
            <div class="hosp-icon">🏥</div>
            <span class="marker-tag">${hosp.name.split(' ')[0]} Trauma</span>
          </div>
        `
        hospEl.onclick = () => {
          map.flyTo({ center: hosp.coordinates, zoom: 14, pitch: 50 })
        }
        const hospMarker = new maplibreglShared.current.Marker({ element: hospEl })
          .setLngLat(hosp.coordinates)
          .addTo(map)
        markersRef.current.push(hospMarker)
      })

      // 3. Active Incident Markers.
      // Never infer incident GPS from a camera position or tracking ID.
      incidents.forEach((inc) => {
        const incCoords = getIncidentCoordinates(inc)

        // Without verified incident coordinates, keep the incident in the
        // queue but do not place a misleading map marker or route to a hospital.
        if (!incCoords) return

        const isSelected = selectedIncident && selectedIncident.id === inc.id
        const pClass = inc.severity === 'P0' ? 'p0' : inc.severity === 'P1' ? 'p1' : 'p2'

        const incEl = document.createElement('div')
        incEl.className = `corridor-marker corridor-marker--incident ${pClass} ${isSelected ? 'is-selected' : ''}`
        incEl.innerHTML = `
          <div class="incident-beacon ${pClass}">
            <div class="beacon-ripple"></div>
            <div class="beacon-dot">
              ${inc.severity === 'P0' ? '⚠️' : inc.severity === 'P1' ? '⚡' : 'ℹ️'}
            </div>
            <span class="incident-tag">${inc.severity} #${inc.id.slice(-4)}</span>
          </div>
        `
        incEl.onclick = () => {
          if (onSelectIncident) onSelectIncident(inc.id)
          map.flyTo({ center: incCoords, zoom: 14.5, pitch: 0 })
          const nearest = findNearestHospital(incCoords)
          calculateTraumaRoute(incCoords, nearest.hospital)
        }

        const incMarker = new maplibreglShared.current.Marker({ element: incEl })
          .setLngLat(incCoords)
          .addTo(map)
        markersRef.current.push(incMarker)
      })

      // 4. Tall 3D beacon pillars so cameras, hospitals and incidents stand out from the terrain.
      try {
        const items = [{ c: sentryCamera.coordinates, color: '#22d3ee', h: 700 }]
        hospitals.forEach((h) => items.push({ c: h.coordinates, color: '#34d399', h: 900 }))
        incidents.forEach((inc) => {
          const ic = getIncidentCoordinates(inc)
          if (!ic) return
          items.push({
            c: ic,
            color: inc.severity === 'P0' ? '#ef4444' : inc.severity === 'P1' ? '#f59e0b' : '#60a5fa',
            h: inc.severity === 'P0' ? 1500 : inc.severity === 'P1' ? 1100 : 800,
          })
        })
        const data = {
          type: 'FeatureCollection',
          features: items
            .filter((it) => Array.isArray(it.c) && it.c.length >= 2)
            .map((it) => ({ type: 'Feature', properties: { color: it.color, h: it.h }, geometry: { type: 'Polygon', coordinates: [pillar(it.c[0], it.c[1])] } })),
        }
        if (map.getSource('beacons-src')) {
          map.getSource('beacons-src').setData(data)
        } else {
          map.addSource('beacons-src', { type: 'geojson', data })
          map.addLayer({
            id: 'beacons-3d',
            type: 'fill-extrusion',
            source: 'beacons-src',
            paint: {
              'fill-extrusion-color': ['get', 'color'],
              'fill-extrusion-height': ['get', 'h'],
              'fill-extrusion-base': 0,
              'fill-extrusion-opacity': 0.85,
            },
          })
        }
      } catch (err) {
        console.warn('[HRAP] 3D beacon layer failed:', err)
      }
    })
  }, [
    mapLoaded,
    incidents,
    selectedIncident,
    sentryCamera,
    hospitals,
    onSelectIncident,
    findNearestHospital,
    calculateTraumaRoute,
  ])

  // Fly to a selected incident only when its own GPS is available.
  useEffect(() => {
    if (!selectedIncident || !mapRef.current) return

    const incCoords = getIncidentCoordinates(selectedIncident)
    if (!incCoords) {
      setTraumaRoute(null)
      setRouteLoading(false)
      return
    }

    mapRef.current.flyTo({ center: incCoords, zoom: 14, pitch: 0 })
    const nearest = findNearestHospital(incCoords)
    calculateTraumaRoute(incCoords, nearest.hospital)
  }, [selectedIncident, findNearestHospital, calculateTraumaRoute])

  // Orbit rotation loop
  useEffect(() => {
    if (isOrbiting) {
      orbitIntervalRef.current = setInterval(() => {
        if (!mapRef.current) return
        const currBearing = mapRef.current.getBearing()
        mapRef.current.setBearing(currBearing + 0.3)
      }, 50)
    } else {
      if (orbitIntervalRef.current) clearInterval(orbitIntervalRef.current)
    }
    return () => {
      if (orbitIntervalRef.current) clearInterval(orbitIntervalRef.current)
    }
  }, [isOrbiting])

  // Reset view to active corridor
  const handleResetView = () => {
    if (!mapRef.current) return
    mapRef.current.flyTo({
      center: activeCorridor.center,
      zoom: activeCorridor.zoom,
      pitch: 55,
      bearing: -15,
    })
  }

  // Corridor switch handler
  const handleCorridorChange = (id) => {
    setActiveCorridorId(id)
    const target = DEFAULT_CORRIDORS.find((c) => c.id === id)
    if (target && mapRef.current) {
      mapRef.current.flyTo({
        center: target.center,
        zoom: target.zoom,
        pitch: 55,
        bearing: -15,
      })
    }
  }

  return (
    <div className="corridor-map-wrapper">
      {/* HUD Top Controls Bar */}
      <div className="corridor-hud-controls">
        <div className="hud-group">
          <select
            className="corridor-select"
            value={activeCorridorId}
            onChange={(e) => handleCorridorChange(e.target.value)}
            aria-label="Select Andhra Pradesh Highway Corridor"
          >
            {DEFAULT_CORRIDORS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.highway} · {c.name} ({c.blackspots} Blackspots)
              </option>
            ))}
          </select>
        </div>

        <div className="hud-group">
          <button
            type="button"
            className={`hud-btn ${styleMode === 'bright' ? 'is-active' : ''}`}
            onClick={() => setStyleMode(styleMode === 'dark' ? 'bright' : 'dark')}
            title="Switch between the colour map and the night map"
          >
            <Layers size={13} />
            <span>{styleMode === 'dark' ? 'Night map' : 'Colour map'}</span>
          </button>

          <button
            type="button"
            className={`hud-btn ${terrainEnabled ? 'is-active' : ''} ${terrainStatus === 'unavailable' ? 'terrain-unavailable' : ''}`}
            onClick={() => setTerrainEnabled(!terrainEnabled)}
            aria-pressed={terrainEnabled}
            title={terrainError || 'Toggle 3D terrain elevation and hillshade'}
          >
            <Mountain size={13} />
            <span>{terrainStatus === 'unavailable' ? 'Hills unavailable' : terrainStatus === 'loading' ? 'Loading hills…' : terrainEnabled ? '3D hills · ON' : '3D hills · OFF'}</span>
          </button>

          <button
            type="button"
            className={`hud-btn ${isOrbiting ? 'is-active' : ''}`}
            onClick={() => setIsOrbiting(!isOrbiting)}
            title="Slowly rotate around the road"
          >
            <Compass size={13} className={isOrbiting ? 'spin-slow' : ''} />
            <span>Rotate</span>
          </button>

          <button
            type="button"
            className="hud-btn"
            onClick={handleResetView}
            title="Back to the starting view"
          >
            <RotateCcw size={13} />
          </button>
        </div>
      </div>

      {/* Map and persistent intelligence sidebar */}
      <div className="corridor-map-stage">
        {terrainEnabled && terrainStatus === 'unavailable' && (
          <div className="ap-map-warn" role="status">
            3D hills could not load{terrainError ? `: ${terrainError}` : '.'} The map is still usable.
          </div>
        )}
        <details className="ap-map-legend">
          <summary>Map key</summary>
          <div><i style={{ background: '#f59e0b' }} /> Road you picked (raised)</div>
          <div><i style={{ background: '#0284c7' }} /> Other highways</div>
          <div><i style={{ background: '#10b981' }} /> Fastest way to a hospital</div>
          <div><i style={{ background: '#ef4444' }} /> Tall red pillar: critical incident</div>
          <p>Drag to move · Scroll to zoom · Right-drag to tilt</p>
        </details>
        {/* Main Map Canvas or WebGL Fallback */}
        {!webGlFailed ? (
        <div ref={mapContainerRef} className="corridor-map-canvas" />
      ) : (
        /* SVG Offline Schematic Fallback */
        <div className="corridor-schematic-fallback">
          <div className="schematic-badge">
            <Info size={14} />
            <span>2D Tactical Schematic (WebGL Unavailable)</span>
          </div>
          <svg className="schematic-svg" viewBox="0 0 800 450">
            {/* Background Grid */}
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid)" />

            {/* Highway Corridor Line */}
            <path
              d="M 80 340 Q 300 280, 480 180 T 720 90"
              fill="none"
              stroke="#0284c7"
              strokeWidth="10"
              strokeLinecap="round"
              opacity="0.4"
            />
            <path
              d="M 80 340 Q 300 280, 480 180 T 720 90"
              fill="none"
              stroke="#38bdf8"
              strokeWidth="4"
              strokeLinecap="round"
            />

            {/* Sentry Camera Point */}
            <g transform="translate(420, 205)">
              <circle r="14" fill="rgba(56, 189, 248, 0.2)" />
              <circle r="7" fill="#38bdf8" />
              <text x="18" y="4" fill="#f0f4f8" fontSize="11" fontWeight="600">
                CAM-AP-NH16-KM42 (Vijayawada-Guntur)
              </text>
            </g>

            {/* AIIMS Mangalagiri */}
            <g transform="translate(480, 150)">
              <rect x="-10" y="-10" width="20" height="20" rx="4" fill="#ef4444" />
              <text x="16" y="4" fill="#fca5a5" fontSize="11" fontWeight="600">
                AIIMS Mangalagiri Trauma (24/7)
              </text>
            </g>

            {/* Active Incident Beacons */}
            {incidents.map((inc, i) => {
              const x = 390 + i * 45
              const y = 220 - i * 20
              return (
                <g
                  key={inc.id}
                  transform={`translate(${x}, ${y})`}
                  className="schematic-inc-node"
                  onClick={() => onSelectIncident && onSelectIncident(inc.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <circle r="12" fill={inc.severity === 'P0' ? '#ef4444' : '#f59e0b'} opacity="0.3" />
                  <circle r="6" fill={inc.severity === 'P0' ? '#ef4444' : '#f59e0b'} />
                  <text x="12" y="4" fill="#fff" fontSize="10" fontWeight="700">
                    {inc.severity} #{inc.id.slice(-4)}
                  </text>
                </g>
              )
            })}
          </svg>
        </div>
      )}
      </div>

      {/* Persistent weather and road-risk intelligence sidebar */}
      <aside className="corridor-intel-sidebar">
        <div className="corridor-intel-heading">
          <span className="corridor-intel-eyebrow">REGIONAL INTELLIGENCE</span>
          <h2>Weather &amp; Road Risk</h2>
          <p>Live conditions and seasonal risk for the selected map location.</p>
        </div>

        <div className="regional-weather-dock">
          <RegionalWeather
            coordinates={weatherPoint.coordinates}
            locationName={weatherPoint.name}
          />
        </div>

        <div className="corridor-intel-note">
          <span className="corridor-intel-live-dot" />
          <div>
            <strong>Location-aware briefing</strong>
            <p>Select a point on the map to update the local weather and risk assessment.</p>
          </div>
        </div>
      </aside>

      {/* Trauma Route & Blackspot Tactical Banner */}
      <div className="corridor-tactical-card">
        <div className="tactical-card-header">
          <div className="card-title">
            <Activity size={14} className="pulse-red" />
            <span>AP Golden Hour Trauma Routing</span>
          </div>
          <span className="corridor-stat-pill">
            {activeCorridor.districts.join(' & ')} · {activeCorridor.blackspots} MoRTH Blackspots
          </span>
        </div>

        {selectedIncident ? (
          <div className="tactical-card-body">
            <div className="incident-context">
              <span className={`pill pill--${selectedIncident.severity.toLowerCase()}`}>
                {selectedIncident.severity}
              </span>
              <span className="inc-type">{selectedIncident.type.replace(/_/g, ' ')}</span>
              <span className="inc-loc">
                {selectedIncident.lat != null && selectedIncident.lng != null
                  ? `GPS ${Number(selectedIncident.lat).toFixed(5)}, ${Number(selectedIncident.lng).toFixed(5)}`
                  : selectedIncident.latitude != null && selectedIncident.longitude != null
                    ? `GPS ${Number(selectedIncident.latitude).toFixed(5)}, ${Number(selectedIncident.longitude).toFixed(5)}`
                    : selectedIncident.km != null
                      ? `KM ${selectedIncident.km}`
                      : selectedIncident.camera?.km != null
                        ? `Camera KM ${selectedIncident.camera.km} · incident GPS unavailable`
                        : 'Incident GPS unavailable'}
                {' · '}{selectedIncident.lane || 'Lane unverified'}
              </span>
            </div>

            {traumaRoute && (
              <div className="trauma-routing-result">
                <div className="routing-stat-row">
                  <div className="routing-col">
                    <span className="stat-label">Designated Trauma Care</span>
                    <strong className="stat-val text-emerald">
                      {traumaRoute.hospital.name}
                    </strong>
                    <span className="stat-sub">{traumaRoute.hospital.type}</span>
                  </div>
                  <div className="routing-col text-right">
                    <span className="stat-label">Trauma Transit Time</span>
                    <strong className="stat-val text-amber">
                      ~{traumaRoute.durationMin} mins
                    </strong>
                    <span className="stat-sub">
                      {traumaRoute.distanceKm} km · {traumaRoute.type === 'osrm' ? 'OSRM Driving Route' : 'Haversine Est.'}
                    </span>
                  </div>
                </div>

                <div className="ambulance-dispatch-strip">
                  <div className="hotline">
                    <PhoneCall size={12} />
                    <span>Ambulance Hotline: <b>{traumaRoute.hospital.contact}</b></span>
                  </div>
                  <span className="golden-hour-target">
                    Target: &lt;15 min Golden Hour
                  </span>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="tactical-card-empty">
            <Navigation size={14} />
            <span>Select an incident from the queue or click a map beacon to view trauma routing to AIIMS Mangalagiri.</span>
          </div>
        )}
      </div>
    </div>
  )
}
