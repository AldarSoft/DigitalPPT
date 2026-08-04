import { useState } from 'react'
import { toast } from 'sonner'
import { api } from '../../../lib/api'
import { tw } from '../../../lib/tailwind-styles'

export function ForgotPasswordPage({ onClose }: {
    onClose: () => void;
}) {
    const [email, setEmail] = useState('');
    const [sent, setSent] = useState(false);
    return (<div className={tw("modal-backdrop")} role="presentation" onMouseDown={onClose}>
      <form className={tw("auth-modal")} onMouseDown={(event) => event.stopPropagation()} onSubmit={async (event) => {
            event.preventDefault();
            try {
                await api.resetPassword(email);
                setSent(true);
            }
            catch {
                toast.error('Could not request a reset link');
            }
        }}>
        <h2>Reset password</h2>
        {sent ? <p>Check your inbox. If that account exists, a reset link has been sent.</p> : (<>
            <p>Enter your account email and we will send reset instructions.</p>
            <label>Email<input type="email" value={email} required onChange={(event) => setEmail(event.target.value)}/></label>
            <button className={tw("auth-submit")} type="submit">Send reset link</button>
          </>)}
        <button className={tw("modal-close")} type="button" onClick={onClose}>Close</button>
      </form>
    </div>);
}

