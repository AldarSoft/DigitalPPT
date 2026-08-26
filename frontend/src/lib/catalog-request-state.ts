export type CatalogRequestState = 'loading' | 'ready' | 'unavailable'
export type ProductRequestState = 'loading' | 'ready' | 'not-found' | 'unavailable'

export function catalogRequestState({
  hasData,
  isError,
  isLoading,
}: {
  hasData: boolean
  isError: boolean
  isLoading: boolean
}): CatalogRequestState {
  if (hasData) return 'ready'
  if (isError) return 'unavailable'
  return isLoading ? 'loading' : 'ready'
}

export function productRequestState({
  hasData,
  isLoading,
  status,
}: {
  hasData: boolean
  isLoading: boolean
  status?: number
}): ProductRequestState {
  if (hasData) return 'ready'
  if (isLoading) return 'loading'
  return status === 404 ? 'not-found' : 'unavailable'
}
