import type { Order, PaymentAttempt, QuoteRequest } from '../types'

export type SimpleStatus = 'pending' | 'processing' | 'completed' | 'cancelled'

const ORDER_STATUS: Record<Order['status'], SimpleStatus> = {
  pending: 'pending',
  scheduled: 'processing',
  processing: 'processing',
  completed: 'completed',
  cancelled: 'cancelled',
}

const QUOTE_STATUS: Record<QuoteRequest['status'], SimpleStatus> = {
  new: 'pending',
  reviewing: 'processing',
  quoted: 'processing',
  approved: 'completed',
  closed: 'cancelled',
}

const PAYMENT_STATUS: Record<PaymentAttempt['status'], SimpleStatus> = {
  pending: 'processing',
  succeeded: 'completed',
  failed: 'cancelled',
  cancelled: 'cancelled',
  expired: 'cancelled',
  refunded: 'cancelled',
}

const LABELS: Record<SimpleStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

export function orderStatusKey(status: Order['status']) {
  return ORDER_STATUS[status]
}

export function quoteStatusKey(status: QuoteRequest['status']) {
  return QUOTE_STATUS[status]
}

export function paymentStatusKey(status: PaymentAttempt['status']) {
  return PAYMENT_STATUS[status]
}

export function simpleStatusLabel(status: SimpleStatus) {
  return LABELS[status]
}

export function orderStatusLabel(status: Order['status']) {
  return simpleStatusLabel(orderStatusKey(status))
}

export function quoteStatusLabel(status: QuoteRequest['status']) {
  return simpleStatusLabel(quoteStatusKey(status))
}

export function paymentStatusLabel(status: PaymentAttempt['status']) {
  return simpleStatusLabel(paymentStatusKey(status))
}

export function orderSourceLabel(source: Order['source']) {
  return {
    quote: 'Quote',
    direct: 'Instant payment',
    admin: 'Admin order',
  }[source]
}
