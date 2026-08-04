import { useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Save } from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '../../../contexts/AuthContext'
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
  };
};
export function ProfileForm({
  user,
  addressOnly = false,
}: {
  user: User;
  addressOnly?: boolean;
}) {
  const auth = useAuth();
  const { register, handleSubmit } = useForm<ProfileValues>({
    defaultValues: user,
  });
  const update = useMutation({
    mutationFn: auth.updateProfile,
    onSuccess: () => toast.success("Account details saved"),
    onError: () => toast.error("Could not save account details"),
  });
  return (
    <section className={tw("account-panel profile-panel")}>
      <h2>{addressOnly ? "Shipping address" : "Account settings"}</h2>
      <form
        onSubmit={handleSubmit((values) =>
          update.mutate(addressOnly ? { profile: values.profile } : values),
        )}
      >
        {!addressOnly ? (
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
        ) : null}
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
  );
}

