import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { CheckCircle2, Eye, EyeOff, KeyRound, LockKeyhole, ShieldAlert } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, api } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'

const resetPasswordSchema = z.object({
  new_password: z.string().min(8, 'Use at least 8 characters'),
  confirm_password: z.string().min(1, 'Confirm your new password'),
}).refine((values) => values.new_password === values.confirm_password, {
  path: ['confirm_password'],
  message: 'Passwords do not match',
})

type ResetPasswordForm = z.infer<typeof resetPasswordSchema>

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [complete, setComplete] = useState(false)
  const uid = searchParams.get('uid')
  const token = searchParams.get('token')
  const isAccountSetup = searchParams.get('setup') === '1'
  const hasValidLinkShape = Boolean(uid && token)
  const { register, handleSubmit, setError, formState: { errors } } = useForm<ResetPasswordForm>()

  const title = isAccountSetup ? 'Set up your password' : 'Reset your password'
  const description = isAccountSetup
    ? 'Choose a password to activate your Digital PTT account.'
    : 'Choose a new password for your Digital PTT account.'

  const submit = handleSubmit(async (values) => {
    const parsed = resetPasswordSchema.safeParse(values)
    if (!parsed.success) {
      parsed.error.issues.forEach((issue) => {
        setError(issue.path[0] as keyof ResetPasswordForm, { message: issue.message })
      })
      return
    }

    if (!uid || !token) return

    setSubmitting(true)
    setSubmitError(null)
    try {
      await api.confirmPasswordReset({
        uid,
        token,
        new_password: parsed.data.new_password,
        confirm_password: parsed.data.confirm_password,
      })
      setComplete(true)
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : 'Your password could not be updated. Try again.')
    } finally {
      setSubmitting(false)
    }
  })

  return <main className={tw('password-reset-page')}>
    <Link className={tw('auth-brand dark')} to="/" aria-label="Digital PTT home">
      <img src="/digital-ptt-logo.svg" alt="Digital PTT" />
    </Link>
    <section className={tw('password-reset-card')}>
      {complete ? <>
        <span className={tw('password-reset-icon success')}><CheckCircle2 size={25} /></span>
        <p className={tw('eyebrow')}>PASSWORD UPDATED</p>
        <h1>{isAccountSetup ? 'Your account is ready' : 'Password reset complete'}</h1>
        <p>You can now sign in with your new password.</p>
        <Link className={tw('auth-submit')} to="/login">Sign in</Link>
      </> : !hasValidLinkShape ? <>
        <span className={tw('password-reset-icon error')}><ShieldAlert size={25} /></span>
        <p className={tw('eyebrow')}>INVALID LINK</p>
        <h1>This link cannot be used</h1>
        <p>The password link is incomplete, expired, or has already been used. Request a new reset link to continue.</p>
        <Link className={tw('auth-submit')} to="/login">Return to sign in</Link>
      </> : <>
        <span className={tw('password-reset-icon')}><KeyRound size={25} /></span>
        <p className={tw('eyebrow')}>{isAccountSetup ? 'ACCOUNT SETUP' : 'PASSWORD RESET'}</p>
        <h1>{title}</h1>
        <p>{description}</p>
        <form onSubmit={submit} noValidate>
          <label>
            New password
            <div>
              <LockKeyhole size={18} />
              <input type={showPassword ? 'text' : 'password'} autoComplete="new-password" {...register('new_password')} />
              <button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((value) => !value)}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            <small>{errors.new_password?.message}</small>
          </label>
          <label>
            Confirm new password
            <div>
              <LockKeyhole size={18} />
              <input type={showPassword ? 'text' : 'password'} autoComplete="new-password" {...register('confirm_password')} />
            </div>
            <small>{errors.confirm_password?.message}</small>
          </label>
          {submitError ? <p className={tw('password-reset-error')} role="alert">{submitError}</p> : null}
          <button className={tw('auth-submit')} type="submit" disabled={submitting}>
            {submitting ? 'Updating password...' : isAccountSetup ? 'Activate account' : 'Update password'}
          </button>
        </form>
        <Link className={tw('password-reset-back')} to="/login">Back to sign in</Link>
      </>}
    </section>
  </main>
}
