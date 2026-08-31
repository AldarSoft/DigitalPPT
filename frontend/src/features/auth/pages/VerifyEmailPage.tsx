import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../../lib/api'
import { useAuth } from '../../../contexts/AuthContext'
import { tw } from '../../../lib/tailwind-styles'

export function VerifyEmailPage() {
  const { verifyEmail } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [error, setError] = useState('')
  const token = params.get('token') || ''
  const visibleError = token ? error : 'This verification link is incomplete.'

  useEffect(() => {
    if (!token) return
    verifyEmail(token)
      .then((user) => navigate(user.is_staff ? '/admin' : '/account', { replace: true }))
      .catch((reason) => setError(reason instanceof ApiError ? reason.message : 'Email verification failed.'))
  }, [navigate, token, verifyEmail])

  return <main className={tw('route-message')}>
    <h1>{visibleError ? 'Email verification failed' : 'Verifying your email'}</h1>
    <p>{visibleError || 'Please wait while we finish setting up your account.'}</p>
    {visibleError ? <Link to="/login">Return to sign in</Link> : null}
  </main>
}
