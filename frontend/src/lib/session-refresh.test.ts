import assert from 'node:assert/strict'
import test from 'node:test'

import { createRefreshCoordinator } from './session-refresh.ts'

test('shares one refresh request between concurrent callers and recovers afterwards', async () => {
  let refreshCalls = 0
  let resolveRefresh: ((token: string) => void) | undefined
  const refresh = createRefreshCoordinator(() => {
    refreshCalls += 1
    return new Promise<string>((resolve) => {
      resolveRefresh = resolve
    })
  })

  const first = refresh()
  const second = refresh()

  assert.equal(refreshCalls, 1)
  resolveRefresh?.('access-token-1')
  assert.deepEqual(await Promise.all([first, second]), ['access-token-1', 'access-token-1'])

  const next = refresh()
  assert.equal(refreshCalls, 2)
  resolveRefresh?.('access-token-2')
  assert.equal(await next, 'access-token-2')
})

test('allows a later refresh after a failed refresh attempt', async () => {
  let refreshCalls = 0
  const refresh = createRefreshCoordinator(async () => {
    refreshCalls += 1
    if (refreshCalls === 1) throw new Error('expired refresh session')
    return 'access-token-2'
  })

  await assert.rejects(() => refresh(), /expired refresh session/)
  assert.equal(await refresh(), 'access-token-2')
  assert.equal(refreshCalls, 2)
})
