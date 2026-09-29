// Mirrors the server's pin rule in cases/api.py (MAX_PIN_DISTANCE_METRES), so
// the form can explain a refusal before sending. The server still decides.
export const MAX_PIN_DISTANCE_METRES = 5000

const EARTH_RADIUS_METRES = 6371000

// Great-circle distance, the same formula as cases/duplicates.haversine_metres.
export function distanceMetres(lat1, lng1, lat2, lng2) {
  const rad = (deg) => (deg * Math.PI) / 180
  const dPhi = rad(lat2 - lat1)
  const dLambda = rad(lng2 - lng1)
  const h =
    Math.sin(dPhi / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLambda / 2) ** 2
  return 2 * EARTH_RADIUS_METRES * Math.asin(Math.min(1, Math.sqrt(h)))
}

// Why a pin cannot belong to this village, or null if it can.
export function pinProblem(village, latitude, longitude) {
  const metres = distanceMetres(latitude, longitude, Number(village.latitude), Number(village.longitude))
  if (metres <= MAX_PIN_DISTANCE_METRES) return null
  return `That spot is ${(metres / 1000).toFixed(1)} km from the centre of ${village.name}. Check the village you chose, or place the pin on your home.`
}
