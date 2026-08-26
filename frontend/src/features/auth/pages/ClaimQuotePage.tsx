import { useEffect, useState } from 'react'
import { CheckCircle2, FileKey2, ShieldAlert } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import { ApiError, api } from '../../../lib/api'
import type { QuoteRequest } from '../../../types'
import { tw } from '../../../lib/tailwind-styles'

export function ClaimQuotePage() {
  const [searchParams] = useSearchParams()
  const [quote, setQuote] = useState<QuoteRequest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const quoteNumber = searchParams.get('quote')
  const token = searchParams.get('token')
  const invalidLink = !quoteNumber || !token
  const displayError = invalidLink
    ? 'This quote access link is incomplete or invalid.'
    : error

  useEffect(() => {
    if (invalidLink) return

    let active = true
    api.claimQuote(quoteNumber, token)
      .then((value) => {
        if (active) setQuote(value)
      })
      .catch((requestError) => {
        if (active) {
          setError(
            requestError instanceof ApiError
              ? requestError.message
              : 'This quote could not be connected to your account.',
          )
        }
      })
    return () => { active = false }
  }, [invalidLink, quoteNumber, token])

  return <main className={tw('password-reset-page')}>
    <Link className={tw('auth-brand dark')} to="/" aria-label="Digital PTT home">
      <img src="/digital-ptt-logo.svg" alt="Digital PTT" />
    </Link>
    <section className={tw('password-reset-card')}>
      {quote ? <>
        <span className={tw('password-reset-icon success')}><CheckCircle2 size={25} /></span>
        <p className={tw('eyebrow')}>QUOTE CONNECTED</p>
        <h1>Your quote is ready</h1>
        <p>Quote <strong>{quote.quote_number}</strong> is now connected to your account.</p>
        <Link className={tw('auth-submit')} to={`/account?tab=quotes&quote=${encodeURIComponent(quote.quote_number)}`}>Open quote</Link>
      </> : displayError ? <>
        <span className={tw('password-reset-icon error')}><ShieldAlert size={25} /></span>
        <p className={tw('eyebrow')}>QUOTE ACCESS</p>
        <h1>This link cannot be used</h1>
        <p>{displayError}</p>
        <Link className={tw('auth-submit')} to="/account?tab=quotes">Go to my quotes</Link>
      </> : <>
        <span className={tw('password-reset-icon')}><FileKey2 size={25} /></span>
        <p className={tw('eyebrow')}>QUOTE ACCESS</p>
        <h1>Connecting your quote</h1>
        <p>We are confirming that this quote belongs to your signed-in account.</p>
      </>}
    </section>
  </main>
}
