import { useMutation } from '@tanstack/react-query'
import { useForm, useWatch } from 'react-hook-form'
import { KeyRound, Save } from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '../../../contexts/AuthContext'
import { api } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'
import type { User } from '../../../types'

type ProfileValues = {
  first_name: string;
  last_name: string;
  phone_number: string;
  profile: {
    company_name: string;
    job_title: string;
    address_line_1: string;
    address_line_2: string;
    city: string;
    state: string;
    country: string;
    postal_code: string;
    use_different_shipping_address: boolean;
    shipping_address_line_1: string;
    shipping_address_line_2: string;
    shipping_city: string;
    shipping_state: string;
    shipping_country: string;
    shipping_postal_code: string;
  };
};
export function ProfileForm({ user }: { user: User }) {
  const auth = useAuth();
  const { register, handleSubmit, control } = useForm<ProfileValues>({
    defaultValues: {
      ...user,
      profile: {
        ...user.profile,
        use_different_shipping_address: user.profile.use_different_shipping_address ?? false,
      },
    },
  });
  const update = useMutation({
    mutationFn: auth.updateProfile,
    onSuccess: () => toast.success("Account details saved"),
    onError: () => toast.error("Could not save account details"),
  });
  const resetPassword = useMutation({
    mutationFn: () => api.resetPassword(user.email),
    onSuccess: () => toast.success('Password reset link sent. Check your email.'),
    onError: () => toast.error('Could not send a password reset link'),
  });
  const showAddress = !user.is_staff;
  const useDifferentShippingAddress = useWatch({
    control,
    name: 'profile.use_different_shipping_address',
  });

  return <>
    <section className={tw("account-panel profile-panel")}>
      <h2>Account settings</h2>
      <form onSubmit={handleSubmit((values) => update.mutate(values))}>
        <div className={tw("profile-row")}>
          <label>
            First name
            <input {...register("first_name")} />
          </label>
          <label>
            Last name
            <input {...register("last_name")} />
          </label>
          <label>
            Phone
            <input {...register("phone_number")} />
          </label>
          <label>
            Company
            <input {...register("profile.company_name")} />
          </label>
        </div>
        {showAddress ? <>
          <h3>Account address</h3>
          <label>
            Address
            <input {...register("profile.address_line_1")} />
          </label>
          <label>
            Address line 2<input {...register("profile.address_line_2")} />
          </label>
          <div className={tw("profile-row")}>
            <label>
              City
              <input {...register("profile.city")} />
            </label>
            <label>
              State
              <input {...register("profile.state")} />
            </label>
            <label>
              Postal code
              <input {...register("profile.postal_code")} />
            </label>
            <label>
              Country
              <input {...register("profile.country")} />
            </label>
          </div>
          <label className={tw('profile-shipping-toggle')}>
            <input type="checkbox" {...register('profile.use_different_shipping_address')} />
            Use a different shipping address
          </label>
          {useDifferentShippingAddress ? <div className={tw('profile-shipping-fields')}>
            <h3>Shipping address</h3>
            <label>
              Address
              <input {...register('profile.shipping_address_line_1')} />
            </label>
            <label>
              Address line 2<input {...register('profile.shipping_address_line_2')} />
            </label>
            <div className={tw('profile-row')}>
              <label>
                City
                <input {...register('profile.shipping_city')} />
              </label>
              <label>
                State
                <input {...register('profile.shipping_state')} />
              </label>
              <label>
                Postal code
                <input {...register('profile.shipping_postal_code')} />
              </label>
              <label>
                Country
                <input {...register('profile.shipping_country')} />
              </label>
            </div>
          </div> : null}
        </> : null}
        <button
          className={tw("save-profile")}
          type="submit"
          disabled={update.isPending}
        >
          <Save size={18} />
          {update.isPending ? "Saving..." : "Save changes"}
        </button>
      </form>
    </section>
    <section className={tw("account-panel password-reset-panel")}>
      <h2>Password</h2>
      <p>Send a password reset link to {user.email}.</p>
      <button
        className={tw("save-profile password-reset-button")}
        type="button"
        disabled={resetPassword.isPending}
        onClick={() => resetPassword.mutate()}
      >
        <KeyRound size={18} />
        {resetPassword.isPending ? 'Sending...' : 'Send reset link'}
      </button>
    </section>
  </>;
}
