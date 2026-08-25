import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { CheckCircle2, Eye, EyeOff, LockKeyhole, Mail } from 'lucide-react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '../../../contexts/AuthContext'
import { ApiError } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import { ForgotPasswordPage } from './ForgotPasswordPage'

const loginSchema = z.object({
    email: z.email('Enter a valid email address'),
    password: z.string().min(8, 'Password must be at least 8 characters'),
});
type LoginForm = z.infer<typeof loginSchema>;
export function LoginPage() {
    const auth = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [showPassword, setShowPassword] = useState(false);
    const [forgotOpen, setForgotOpen] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const { register, handleSubmit, setError, formState: { errors } } = useForm<LoginForm>();
    if (auth.user) {
        const from = (location.state as { from?: string } | null)?.from;
        return <Navigate to={from || (auth.user.is_staff ? '/admin' : '/account')} replace/>;
    }
    const submit = handleSubmit(async (values) => {
        const parsed = loginSchema.safeParse(values);
        if (!parsed.success) {
            parsed.error.issues.forEach((issue) => setError(issue.path[0] as keyof LoginForm, { message: issue.message }));
            return;
        }
        setSubmitting(true);
        try {
            const user = await auth.login(values.email, values.password);
            const from = (location.state as {
                from?: string;
            } | null)?.from;
            navigate(from || (user.is_staff ? '/admin' : '/account'), { replace: true });
            toast.success(`Welcome back, ${user.first_name || user.email}`);
        }
        catch (error) {
            setError('password', { message: error instanceof ApiError ? error.message : 'Sign in failed' });
        }
        finally {
            setSubmitting(false);
        }
    });
    return (<main className={tw("auth-page")}>
      <section className={tw("auth-intro")}>
        <Link className={tw("auth-brand")} to="/" aria-label="Digital PTT home"><img src="/digital-ptt-logo.svg" alt="Digital PTT" /></Link>
        <div>
          <p className={tw("eyebrow lime")}>YOUR COMMUNICATION HUB</p>
          <h1>Manage orders, radios and support in one place.</h1>
          <p>Access product history, order updates and account details whenever your team needs them.</p>
          <ul>
            {['Track orders and delivery', 'Save shipping details', 'Manage your account'].map((item) => <li key={item}><CheckCircle2 size={20}/>{item}</li>)}
          </ul>
        </div>
        <small>&copy; 2026 Digital PTT</small>
      </section>
      <section className={tw("auth-form-side")}>
        <form onSubmit={submit}>
          <h2>Welcome back</h2>
          <p>Sign in to continue to your Digital PTT account.</p>
          <label>Email address<div><Mail size={19}/><input type="email" placeholder="name@company.com" {...register('email')}/></div><small>{errors.email?.message}</small></label>
          <label>Password<div><LockKeyhole size={19}/><input type={showPassword ? 'text' : 'password'} {...register('password')}/><button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff size={19}/> : <Eye size={19}/>}</button></div><small>{errors.password?.message}</small></label>
          <button className={tw("forgot-link")} type="button" onClick={() => setForgotOpen(true)}>Forgot password?</button>
          <button className={tw("auth-submit")} type="submit" disabled={submitting}>{submitting ? 'Signing in...' : 'Sign in'}</button>
          <p className={tw("auth-switch")}>New to Digital PTT? <Link to="/register">Create an account</Link></p>
        </form>
      </section>
      {forgotOpen ? <ForgotPasswordPage onClose={() => setForgotOpen(false)}/> : null}
    </main>);
}
