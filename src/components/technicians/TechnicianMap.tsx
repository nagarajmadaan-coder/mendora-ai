import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { MapPoint, TechnicianMatch } from '../../lib/api'

/*
  Map of technicians (merged feature), using OpenStreetMap tiles.
  Every marker is an APPROXIMATE AREA CENTRE — never a technician's or customer's real address.
*/

const escapeHtml = (text: string) =>
  text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c)

export default function TechnicianMap({ results, searchPoint }: { results: TechnicianMatch[]; searchPoint: MapPoint | null }) {
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!box.current) return
    const map = L.map(box.current, { scrollWheelZoom: false })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
    }).addTo(map)

    const points: L.LatLngExpression[] = []
    for (const r of results) {
      if (!r.map_point) continue
      const p: L.LatLngExpression = [r.map_point.lat, r.map_point.lon]
      points.push(p)
      const sample = r.technician.is_sample ? '<br><em>Demo sample — not a real technician</em>' : ''
      const dist = r.approx_distance_km != null ? `<br>About ${r.approx_distance_km} km between area centres` : ''
      L.circleMarker(p, { radius: 9, color: '#0f766e', weight: 2, fillColor: '#14b8a6', fillOpacity: 0.85 })
        .addTo(map)
        .bindPopup(`<strong>${escapeHtml(r.technician.display_name)}</strong><br>${escapeHtml(r.map_point.label)} (approximate area centre)${dist}${sample}`)
    }
    if (searchPoint) {
      const p: L.LatLngExpression = [searchPoint.lat, searchPoint.lon]
      points.push(p)
      L.circleMarker(p, { radius: 8, color: '#0b1b33', weight: 3, fillColor: '#ffffff', fillOpacity: 1 })
        .addTo(map)
        .bindPopup(`<strong>Your area</strong><br>${escapeHtml(searchPoint.label)} (approximate centre)`)
    }
    if (points.length > 1) map.fitBounds(L.latLngBounds(points), { padding: [40, 40], maxZoom: 13 })
    else map.setView(points[0] ?? [20.59, 78.96], points.length ? 12 : 4)
    return () => {
      map.remove()
    }
  }, [results, searchPoint])

  const missing = results.filter((r) => !r.map_point).length
  return (
    <div>
      <div ref={box} className="h-80 w-full overflow-hidden rounded-2xl border border-navy-900/10 bg-navy-50 sm:h-96" role="region" aria-label="Map of technicians (approximate area centres)" />
      <p className="mt-2 text-xs leading-relaxed text-navy-600">
        Markers show <strong>approximate area centres</strong>, not real addresses. Green = technician, white = your area.
        {missing > 0 && ` ${missing} technician${missing > 1 ? 's' : ''} not shown: their areas aren’t on MENDORA’s map list yet.`}
      </p>
    </div>
  )
}
