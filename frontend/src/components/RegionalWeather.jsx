import { useEffect, useState } from 'react'
import './regional-weather.css'

const WEATHER_URL = 'https://api.open-meteo.com/v1/forecast'

function seasonFor(month, lat) {
  // Andhra Pradesh seasonal guide; local weather data takes precedence.
  if (month >= 3 && month <= 5) return 'Summer'
  if (month >= 6 && month <= 9) return 'Southwest monsoon'
  if (month >= 10 && month <= 12) return lat >= 16.5
    ? 'Northeast monsoon / post-monsoon'
    : 'Northeast monsoon'
  return 'Winter'
}

function describeWeather(code) {
  if (code === 0) return 'Clear sky'
  if ([1, 2, 3].includes(code)) return 'Partly cloudy'
  if ([45, 48].includes(code)) return 'Fog / reduced visibility'
  if ([51, 53, 55, 56, 57].includes(code)) return 'Drizzle'
  if ([61, 63, 65, 66, 67].includes(code)) return 'Rain'
  if ([71, 73, 75, 77, 85, 86].includes(code)) return 'Snow / ice conditions'
  if ([80, 81, 82].includes(code)) return 'Rain showers'
  if ([95, 96, 99].includes(code)) return 'Thunderstorm'
  return 'Conditions unavailable'
}

function riskFor(weather, season) {
  if (!weather) return {
    level: 'Awaiting data',
    detail: 'Weather has not loaded yet. Do not use this panel as a safety clearance.',
  }

  const rain = Number(weather.precipitation ?? 0)
  const wind = Number(weather.wind_speed_10m ?? 0)
  const temp = Number(weather.temperature_2m ?? 0)
  const code = Number(weather.weather_code ?? -1)
  const visibilityRisk = [45, 48, 51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99].includes(code)
  const heatRisk = temp >= 38
  const severeRisk = [65, 67, 82, 95, 96, 99].includes(code) || rain >= 7 || wind >= 50

  const factors = []
  if (visibilityRisk) factors.push('Rain, fog or storms may reduce visibility and increase braking distance.')
  if (rain >= 1) factors.push('Wet pavement can reduce tyre grip; check drainage and waterlogging-prone sections.')
  if (heatRisk) factors.push('High heat can increase driver fatigue and vehicle overheating risk.')
  if (wind >= 35) factors.push('Strong winds may affect two-wheelers and high-sided vehicles.')
  if (season.toLowerCase().includes('monsoon')) factors.push('During monsoon periods, monitor water accumulation, potholes and incident response access.')
  if (!factors.length) factors.push('No major weather trigger detected in the current snapshot. Continue normal monitoring.')

  return {
    level: severeRisk ? 'Elevated' : visibilityRisk || heatRisk || rain >= 1 || wind >= 35 ? 'Watch' : 'Routine',
    detail: factors.join(' '),
  }
}

export default function RegionalWeather({
  coordinates = [80.60, 16.45],
  locationName = 'Selected corridor',
}) {
  const [weather, setWeather] = useState(null)
  const [forecast, setForecast] = useState(null)
  const [status, setStatus] = useState('loading')
  const [updatedAt, setUpdatedAt] = useState(null)
  const [now, setNow] = useState(() => new Date())

  const lng = Number(coordinates?.[0])
  const lat = Number(coordinates?.[1])

  useEffect(() => {
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return undefined

    let cancelled = false
    const controller = new AbortController()

    async function loadWeather() {
      setStatus('loading')
      try {
        const params = new URLSearchParams({
          latitude: String(lat),
          longitude: String(lng),
          current: [
            'temperature_2m', 'relative_humidity_2m', 'apparent_temperature',
            'is_day', 'precipitation', 'rain', 'showers', 'weather_code',
            'wind_speed_10m', 'wind_direction_10m',
          ].join(','),
          hourly: [
            'precipitation_probability', 'visibility', 'wind_speed_10m',
            'temperature_2m', 'weather_code',
          ].join(','),
          daily: [
            'weather_code', 'temperature_2m_max', 'temperature_2m_min',
            'precipitation_probability_max', 'rain_sum', 'wind_speed_10m_max',
          ].join(','),
          timezone: 'Asia/Kolkata',
          forecast_days: '3',
        })

        const response = await fetch(`${WEATHER_URL}?${params}`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`Weather service returned ${response.status}`)
        const data = await response.json()
        if (cancelled) return

        setWeather(data.current)
        setForecast(data.daily)
        setUpdatedAt(new Date())
        setNow(new Date())
        setStatus('ready')
      } catch (error) {
        if (!cancelled && error.name !== 'AbortError') setStatus('error')
      }
    }

    loadWeather()
    const refresh = setInterval(loadWeather, 10 * 60 * 1000)
    return () => {
      cancelled = true
      controller.abort()
      clearInterval(refresh)
    }
  }, [lat, lng])

  const season = seasonFor(now.getMonth() + 1, lat)
  const risk = riskFor(weather, season)
  const climate = lat >= 16.5 && lng >= 82.5
    ? 'coastal'
    : lat <= 16 && lng <= 79
      ? 'dry'
      : 'mixed'

  return (
    <aside className={`regional-weather climate-${climate}`} aria-live="polite">
      <div className="rw-topline">
        <span className="rw-kicker">FIELD CONDITIONS / 01</span>
        <span className={`rw-status ${status}`}>
          <i /> {status === 'ready' ? 'LIVE WEATHER' : status === 'error' ? 'FEED UNAVAILABLE' : 'CONNECTING'}
        </span>
      </div>

      <div className="rw-location">{locationName}</div>
      <div className="rw-coordinates">{lat.toFixed(4)}° N · {lng.toFixed(4)}° E</div>

      {status === 'error' && (
        <p className="rw-error">
          Could not reach the weather service. Check connectivity and retry by changing the map selection.
        </p>
      )}

      {weather && (
        <>
          <div className="rw-current">
            <div>
              <div className="rw-temp">{Math.round(weather.temperature_2m)}°</div>
              <div className="rw-condition">{describeWeather(weather.weather_code)}</div>
              <div className="rw-feels">Feels like {Math.round(weather.apparent_temperature)}°C</div>
            </div>
            <div className="rw-weather-symbol" aria-hidden="true">
              {Number(weather.weather_code) >= 51 ? '☂' : Number(weather.weather_code) >= 45 ? '〰' : Number(weather.temperature_2m) >= 34 ? '☼' : '◌'}
            </div>
          </div>

          <div className="rw-metrics">
            <div><span>Humidity</span><strong>{weather.relative_humidity_2m}%</strong></div>
            <div><span>Wind</span><strong>{Math.round(weather.wind_speed_10m)} km/h</strong></div>
            <div><span>Rain now</span><strong>{Number(weather.precipitation ?? 0).toFixed(1)} mm</strong></div>
          </div>

          <div className="rw-risk-head">
            <span className="rw-kicker">ROAD WEATHER ASSESSMENT</span>
            <strong className={`rw-risk rw-risk--${risk.level.toLowerCase().replace(' ', '-')}`}>
              {risk.level}
            </strong>
          </div>
          <p className="rw-risk-copy">{risk.detail}</p>

          <div className="rw-season">
            <span className="rw-kicker">SEASONAL CONTEXT</span>
            <strong>{season}</strong>
            <p>
              {season === 'Summer'
                ? 'Heat can raise fatigue and breakdown risk. Monitor surface distress and vehicle cooling.'
                : season.toLowerCase().includes('monsoon')
                  ? 'Rain periods can increase spray, reduce grip and expose drainage problems. Prioritise visibility and waterlogging checks.'
                  : season === 'Winter'
                    ? 'Early-morning haze may reduce visibility. Watch local fog reports before escalating risk.'
                    : 'Use the live conditions above alongside local road reports; seasonal labels alone do not establish road safety.'}
            </p>
          </div>

          {forecast?.time?.length > 0 && (
            <div className="rw-forecast">
              <span className="rw-kicker">NEXT 3 DAYS</span>
              {forecast.time.map((day, index) => (
                <div className="rw-day" key={day}>
                  <span>{new Date(`${day}T12:00:00`).toLocaleDateString('en-IN', { weekday: 'short', timeZone: 'Asia/Kolkata' })}</span>
                  <span>{describeWeather(forecast.weather_code[index])}</span>
                  <strong>{Math.round(forecast.temperature_2m_max[index])}° / {Math.round(forecast.temperature_2m_min[index])}°</strong>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <div className="rw-foot">
        <span>Source: Open-Meteo · Forecast, not roadside sensors</span>
        <span>{updatedAt ? `Updated ${updatedAt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}` : 'Waiting for first update'}</span>
      </div>
    </aside>
  )
}
