import { useEffect, useState } from 'react'
import { CheckCircle2, FileKey2, ShieldAlert } from 'lucide-react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { useAuth } from '../../../contexts/AuthContext'
import { ApiError, api } from '../../../lib/api'
import type { QuoteRequest } from '../../../types'
import { tw } from '../../../lib/tailwind-styles'

export function ClaimQuotePage() {
  const auth = useAuth()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const [quote, setQuote] = useState<QuoteRequest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [claimEmail, setClaimEmail] = useState<string | null>(null)
  const [claimAccessError, setClaimAccessError] = useState<string | null>(null)
  const quoteNumber = searchParams.get('quote')
  const token = searchParams.get('token')
  const invalidLink = !quoteNumber || !token
  const returnToClaim = `${location.pathname}${location.search}`
  const displayError = invalidLink
    ? 'This quote access link is incomplete or invalid.'
    : error ?? claimAccessError

  useEffect(() => {
    if (invalidLink || !auth.ready || auth.user) return

    let active = true
    api.quoteClaimAccess(quoteNumber, token)
      .then((value) => {
        if (active) setClaimEmail(value.requester_email)
      })
      .catch((requestError) => {
        if (active) {
          setClaimAccessError(
            requestError instanceof ApiError
              ? requestError.message
              : 'This quote access link is invalid or expired.',
          )
        }
      })
    return () => { active = false }
  }, [auth.ready, auth.user, invalidLink, quoteNumber, token])

  useEffect(() => {
    if (invalidLink || !auth.ready || !auth.user) return

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
  }, [auth.ready, auth.user, invalidLink, quoteNumber, token])

  return <main className={tw('password-reset-page')}>
    <Link className={tw('auth-brand dark')} to="/" aria-label="Digital PTT home">
      <img src="/digital-ptt-logo.svg" alt="Digital PTT" />
    </Link>
    <section className={tw('password-reset-card')}>
      {!auth.ready ? <>
        <span className={tw('password-reset-icon')}><FileKey2 size={25} /></span>
        <p className={tw('eyebrow')}>QUOTE ACCESS</p>
        <h1>Checking account access</h1>
      </> : !auth.user && !displayError && claimEmail ? <>
        <span className={tw('password-reset-icon')}><FileKey2 size={25} /></span>
        <p className={tw('eyebrow')}>QUOTE ACCESS</p>
        <h1>Sign in or create an account</h1>
        <p>Use the email address that received this quote link. After you sign in, we will securely connect the quote to your account.</p>
        <div className="mt-6 grid gap-3">
          <Link className={tw('auth-submit')} to="/login" state={{ from: returnToClaim, quoteEmail: claimEmail }}>Sign in</Link>
          <Link className="inline-flex min-h-12 items-center justify-center rounded-control border border-border-input bg-white px-4 text-sm font-extrabold text-brand hover:border-brand" to="/register" state={{ from: returnToClaim, quoteEmail: claimEmail }}>Create account</Link>
        </div>
      </> : quote ? <>
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
        <h1>{auth.user ? 'Connecting your quote' : 'Checking secure quote access'}</h1>
        <p>{auth.user ? 'We are confirming that this quote belongs to your signed-in account.' : 'We are confirming the email address protected by this quote link.'}</p>
      </>}
    </section>
  </main>
}
