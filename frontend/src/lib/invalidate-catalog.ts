import type { QueryClient } from '@tanstack/react-query'

export function invalidateCatalog(client: QueryClient) {
  return client.invalidateQueries({ predicate: ({ queryKey }) => /product|categor/.test(String(queryKey[0])) })
}
