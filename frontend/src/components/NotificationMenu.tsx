import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { tw } from '../lib/tailwind-styles'
import type { UserNotification } from '../types'

export function NotificationMenu({ userId, variant }: { userId: number; variant: 'admin' | 'public' }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLElement>(null)
  const queryKey = ['notifications', userId]
  const notificationsQuery = useQuery({
    queryKey,
    queryFn: api.notifications,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  })
  const markRead = useMutation({
    mutationFn: (id: number) => api.readNotification(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  })

  useEffect(() => {
    if (!open) return
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', closeOnOutsideClick)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  const openNotification = async (notification: UserNotification) => {
    if (!notification.is_read) await markRead.mutateAsync(notification.id)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['quote'] }),
      queryClient.invalidateQueries({ queryKey: ['quotes', 'mine', 'detail'] }),
      queryClient.invalidateQueries({ queryKey: ['quotes', 'mine'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-quotes', 'detail'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-quotes', 'list'] }),
      queryClient.invalidateQueries({ queryKey: ['orders', 'mine'] }),
      queryClient.invalidateQueries({ queryKey: ['admin-orders'] }),
    ])
    setOpen(false)
    navigate(notification.url)
  }

  const unread = notificationsQuery.data?.unread_count ?? 0
  return (
    <section className={variant === 'admin' ? 'relative ml-auto' : 'relative'} ref={menuRef}>
      <button
        className={variant === 'public' ? tw('icon-button') : 'relative inline-flex size-9 items-center justify-center rounded-control border-0 bg-surface-raised text-text-subtle'}
        type="button"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <Bell size={20} />
        {unread ? <span className="absolute -right-1 -top-1 inline-flex min-w-5 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-extrabold leading-5 text-white">{unread > 99 ? '99+' : unread}</span> : null}
      </button>
      {open ? <div className="absolute right-0 top-11 z-50 w-[min(360px,calc(100vw-2rem))] overflow-hidden rounded-panel border border-border bg-white text-ink shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-4 py-3"><strong className="text-sm">Notifications</strong><span className="text-xs text-text-soft">{unread} unread</span></div>
        <div className="max-h-96 overflow-y-auto">
          {notificationsQuery.isLoading ? <p className="p-4 text-sm text-text-soft">Loading notifications...</p> : notificationsQuery.data?.notifications.length ? notificationsQuery.data.notifications.map((notification) => <button className={`grid w-full gap-1 border-0 border-b border-border px-4 py-3 text-left hover:bg-surface-raised ${notification.is_read ? 'bg-white' : 'bg-brand-soft'}`} type="button" key={notification.id} onClick={() => void openNotification(notification)}>
            <span className="flex items-start gap-2 text-sm font-bold text-ink">{!notification.is_read ? <i className="mt-1.5 size-2 shrink-0 rounded-full bg-brand" /> : null}{notification.title}</span>
            <span className="line-clamp-2 text-xs text-text-subtle">{notification.message}</span>
            <time className="text-[10px] text-text-soft">{new Date(notification.created_at).toLocaleString()}</time>
          </button>) : <p className="p-5 text-center text-sm text-text-soft">No notifications yet.</p>}
        </div>
      </div> : null}
    </section>
  )
}
