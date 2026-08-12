import { Check, Clock3 } from 'lucide-react'
import { tw } from '../lib/tailwind-styles'

type TimelineStep = {
  value: string
  label: string
}

export function StatusTimeline({
  noun,
  currentStatus,
  initialStatus,
  createdAt,
  updatedAt,
  steps,
}: {
  noun: string
  currentStatus: string
  initialStatus: string
  createdAt: string
  updatedAt: string
  steps: readonly TimelineStep[]
}) {
  const currentIndex = steps.findIndex((step) => step.value === currentStatus)
  const updated = new Date(updatedAt).getTime() - new Date(createdAt).getTime() > 1000
  const isTerminalException = currentIndex === -1

  return (
    <section className={tw('status-timeline')} aria-label={`${noun} status timeline`}>
      <h3>Timeline</h3>
      <div className={tw('status-progress')}>
        {steps.map((step, index) => {
          const reached = !isTerminalException && index <= currentIndex
          const current = step.value === currentStatus
          return (
            <div className={tw(reached ? 'reached' : '', current ? 'current' : '')} key={step.value}>
              <span>{reached ? <Check size={13} /> : index + 1}</span>
              <small>{step.label}</small>
            </div>
          )
        })}
        {isTerminalException ? (
          <div className={tw('reached current exception')}>
            <span><Check size={13} /></span>
            <small>{currentStatus}</small>
          </div>
        ) : null}
      </div>
      <ol className={tw('activity-log')}>
        <li>
          <Clock3 size={16} />
          <div><strong>{noun} created</strong><time dateTime={createdAt}>{formatDateTime(createdAt)}</time></div>
        </li>
        {updated && currentStatus !== initialStatus ? (
          <li>
            <Check size={16} />
            <div><strong>Status changed to {labelFor(steps, currentStatus)}</strong><time dateTime={updatedAt}>{formatDateTime(updatedAt)}</time></div>
          </li>
        ) : null}
      </ol>
    </section>
  )
}

function labelFor(steps: readonly TimelineStep[], status: string) {
  return steps.find((step) => step.value === status)?.label ?? status
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
