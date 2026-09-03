import type { Order, PaymentAttempt, QuoteRequest } from '../types'

export type SimpleStatus = 'draft' | 'pending' | 'processing' | 'completed' | 'cancelled'

const ORDER_STATUS: Record<Order['status'], SimpleStatus> = {
  draft: 'draft',
  pending: 'pending',
  backordered: 'processing',
  scheduled: 'processing',
  processing: 'processing',
  completed: 'completed',
  cancelled: 'cancelled',
}

const QUOTE_STATUS: Record<QuoteRequest['status'], SimpleStatus> = {
  new: 'pending',
  reviewing: 'processing',
  quote_approved: 'processing',
  invoice_sent: 'processing',
  awaiting_payment: 'pending',
  payment_confirmed: 'completed',
  payment_rejected: 'cancelled',
  cancelled: 'cancelled',
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
  draft: 'Draft',
  pending: 'Pending',
  processing: 'Processing',
  completed: 'Completed',
  cancelled: 'Cancelled',
}

export function orderStatusKey(status: Order['status']) {
  return ORDER_STATUS[status]
}

export function quoteStatusKey(status: QuoteRequest['status'], orderStatus?: QuoteRequest['order_status']) {
  void orderStatus
  return QUOTE_STATUS[status]
}

export function paymentStatusKey(status: PaymentAttempt['status']) {
  return PAYMENT_STATUS[status]
}

export function simpleStatusLabel(status: SimpleStatus) {
  return LABELS[status]
}

export function orderStatusLabel(status: Order['status'], source?: Order['source']) {
  if (status === 'pending' && source === 'quote') return 'Awaiting payment'
  if (status === 'backordered') return 'Awaiting stock'
  return simpleStatusLabel(orderStatusKey(status))
}

export function quoteStatusLabel(status: QuoteRequest['status'], orderStatus?: QuoteRequest['order_status']) {
  if (status === 'new') return 'Pending review'
  if (status === 'reviewing') return 'In review'
  if (status === 'quote_approved') return 'Quote approved'
  if (status === 'invoice_sent') return 'Invoice sent'
  if (status === 'awaiting_payment') return 'Awaiting payment'
  if (status === 'payment_confirmed') return 'Payment confirmed'
  if (status === 'payment_rejected') return 'Payment rejected'
  return simpleStatusLabel(quoteStatusKey(status, orderStatus))
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
