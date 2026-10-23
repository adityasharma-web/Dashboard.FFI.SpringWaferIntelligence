import { useEffect, useState } from 'react'

/* Hash routing keeps the single-origin deployed shape working (FastAPI only
   serves index.html at "/"), so pages are "#/" (wafer map) and "#/layouts". */
export type Route = 'map' | 'layouts'

export const ROUTE_HASH: Record<Route, string> = { map: '#/', layouts: '#/layouts' }

export function routeFromHash(hash: string): Route {
  return hash.replace(/^#\/?/, '').split('?')[0] === 'layouts' ? 'layouts' : 'map'
}

export function navigate(route: Route): void {
  window.location.hash = ROUTE_HASH[route]
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => routeFromHash(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(routeFromHash(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}
