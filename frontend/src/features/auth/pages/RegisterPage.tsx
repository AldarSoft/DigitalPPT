import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { useAuth } from '../../../contexts/AuthContext'
import { ApiError } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'

const registrationSchema = z.object({
    first_name: z.string().min(2, 'First name is required'),
    last_name: z.string().min(2, 'Last name is required'),
    email: z.email('Enter a valid email'),
    phone_number: z.string().optional(),
    password: z.string().min(8, 'Use at least 8 characters'),
    confirm_password: z.string().min(8),
}).refine((data) => data.password === data.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
});
type RegistrationForm = z.infer<typeof registrationSchema>;
export function RegisterPage() {
    const auth = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [submitting, setSubmitting] = useState(false);
    const { register, handleSubmit, setError, formState: { errors } } = useForm<RegistrationForm>();
    const from = (location.state as { from?: string } | null)?.from;
    if (auth.user)
        return <Navigate to={from || "/account"} replace/>;
    const submit = handleSubmit(async (values) => {
        const parsed = registrationSchema.safeParse(values);
        if (!parsed.success) {
            parsed.error.issues.forEach((issue) => setError(issue.path[0] as keyof RegistrationForm, { message: issue.message }));
            return;
        }
        setSubmitting(true);
        try {
            await auth.register(parsed.data);
            toast.success('Your account is ready');
            navigate(from || '/account', { replace: true });
        }
        catch (error) {
            toast.error(error instanceof ApiError ? error.message : 'Could not create account');
        }
        finally {
            setSubmitting(false);
        }
    });
    return (<main className={tw("register-page")}>
      <Link className={tw("auth-brand dark")} to="/" aria-label="Digital PTT home"><img src="/digital-ptt-logo.svg" alt="Digital PTT" /></Link>
      <form onSubmit={submit}>
        <p className={tw("eyebrow")}>CREATE ACCOUNT</p>
        <h1>Set up your customer workspace</h1>
        <p>Track orders and keep shipping details ready for your next purchase.</p>
        <div className={tw("register-grid")}>
          <label>First name<input {...register('first_name')}/><small>{errors.first_name?.message}</small></label>
          <label>Last name<input {...register('last_name')}/><small>{errors.last_name?.message}</small></label>
          <label className={tw("wide")}>Email<input type="email" {...register('email')}/><small>{errors.email?.message}</small></label>
          <label className={tw("wide")}>Phone<input {...register('phone_number')}/><small>{errors.phone_number?.message}</small></label>
          <label>Password<input type="password" {...register('password')}/><small>{errors.password?.message}</small></label>
          <label>Confirm password<input type="password" {...register('confirm_password')}/><small>{errors.confirm_password?.message}</small></label>
        </div>
        <button className={tw("auth-submit")} type="submit" disabled={submitting}>{submitting ? 'Creating account...' : 'Create account'}</button>
        <p className={tw("auth-switch")}>Already have an account? <Link to="/login" state={location.state}>Sign in</Link></p>
      </form>
    </main>);
}
