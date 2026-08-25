import { toast } from 'sonner'
import type { Order, Product, Promotion, QuoteRequest, User } from '../../../types'

export type AdminReport =
  | { kind: 'orders'; rows: Order[] }
  | { kind: 'products'; rows: Product[] }
  | { kind: 'inventory'; rows: Product[] }
  | { kind: 'quotes'; rows: QuoteRequest[] }
  | { kind: 'customers'; rows: User[] }
  | { kind: 'promotions'; rows: Promotion[] }

type CellValue = string | number | boolean | Date | null
type CellFormat = 'currency' | 'date' | 'datetime' | 'integer' | 'percent'
type Column<Row> = {
  header: string
  width: number
  value: (row: Row) => CellValue
  format?: CellFormat | ((row: Row) => CellFormat)
}

const colors = {
  navy: '08264C', blue: '0869F7', paleBlue: 'EAF2FF', paleGray: 'F4F7FB',
  border: 'D8E0EC', text: '0C1930', muted: '64748B', white: 'FFFFFF',
}

const thinBorder = {
  top: { style: 'thin' as const, color: { argb: colors.border } },
  left: { style: 'thin' as const, color: { argb: colors.border } },
  bottom: { style: 'thin' as const, color: { argb: colors.border } },
  right: { style: 'thin' as const, color: { argb: colors.border } },
}

const yesNo = (value: boolean) => value ? 'Yes' : 'No'
const titleCase = (value: string) => value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const dateValue = (value: string | null) => value ? new Date(value) : null
const moneyValue = (value: string | null | undefined) => value === null || value === undefined ? null : Number(value)
const address = (user: User) => [user.profile.address_line_1, user.profile.address_line_2, user.profile.city, user.profile.state, user.profile.postal_code, user.profile.country].filter(Boolean).join(', ')

function orderColumns(): Column<Order>[] {
  return [
    { header: 'Order number', width: 21, value: (row) => row.order_number },
    { header: 'Source', width: 15, value: (row) => titleCase(row.source) },
    { header: 'Status', width: 14, value: (row) => titleCase(row.status) },
    { header: 'Created', width: 20, value: (row) => dateValue(row.created_at), format: 'datetime' },
    { header: 'Customer', width: 25, value: (row) => `${row.customer_first_name} ${row.customer_last_name}`.trim() },
    { header: 'Company', width: 23, value: (row) => row.company_name },
    { header: 'Email', width: 30, value: (row) => row.customer_email },
    { header: 'Phone', width: 18, value: (row) => row.customer_phone },
    { header: 'Items', width: 45, value: (row) => row.items.map((item) => `${item.quantity} x ${item.product_name} (${item.sku || 'No SKU'})`).join('\n') },
    { header: 'Subtotal', width: 15, value: (row) => moneyValue(row.subtotal), format: 'currency' },
    { header: 'Shipping', width: 14, value: (row) => moneyValue(row.shipping_fee), format: 'currency' },
    { header: 'Tax', width: 13, value: (row) => moneyValue(row.tax_amount), format: 'currency' },
    { header: 'Total', width: 15, value: (row) => moneyValue(row.total), format: 'currency' },
    { header: 'Shipping address', width: 42, value: (row) => [row.shipping_address, row.shipping_city, row.shipping_state, row.shipping_postal_code, row.shipping_country].filter(Boolean).join(', ') },
    { header: 'Quote', width: 20, value: (row) => row.quote_number },
    { header: 'Notes', width: 35, value: (row) => row.notes },
  ]
}

function productColumns(inventoryOnly = false): Column<Product>[] {
  const common: Column<Product>[] = [
    { header: 'Product', width: 30, value: (row) => row.name },
    { header: 'SKU', width: 17, value: (row) => row.sku },
    { header: 'Category', width: 22, value: (row) => row.category.name },
    { header: 'Brand', width: 20, value: (row) => row.brand },
    { header: 'Stock quantity', width: 15, value: (row) => row.is_stock_tracked === false ? 'Not tracked' : row.inventory_quantity },
    { header: 'Stock level', width: 16, value: (row) => row.is_stock_tracked === false ? 'Always available' : row.inventory_quantity === 0 ? 'Out of stock' : row.inventory_quantity <= 5 ? 'Low stock' : 'In stock' },
    { header: 'Status', width: 14, value: (row) => titleCase(row.status) },
    { header: 'Storefront active', width: 17, value: (row) => yesNo(row.is_active) },
    { header: 'Updated', width: 20, value: (row) => dateValue(row.updated_at), format: 'datetime' },
  ]
  if (inventoryOnly) return common
  return [
    ...common.slice(0, 4),
    { header: 'Price', width: 14, value: (row) => moneyValue(row.price), format: 'currency' },
    { header: 'Sale price', width: 14, value: (row) => moneyValue(row.sale_price), format: 'currency' },
    { header: 'Current price', width: 15, value: (row) => moneyValue(row.current_price), format: 'currency' },
    { header: 'Cost price', width: 14, value: (row) => moneyValue(row.cost_price), format: 'currency' },
    ...common.slice(4, 8),
    { header: 'Featured', width: 12, value: (row) => yesNo(row.is_featured) },
    { header: 'Description', width: 42, value: (row) => row.short_description || row.description },
    { header: 'Created', width: 20, value: (row) => dateValue(row.created_at), format: 'datetime' },
    common[8],
  ]
}

function quoteColumns(): Column<QuoteRequest>[] {
  return [
    { header: 'Quote number', width: 21, value: (row) => row.quote_number },
    { header: 'Status', width: 16, value: (row) => titleCase(row.status) },
    { header: 'Submitted', width: 20, value: (row) => dateValue(row.created_at), format: 'datetime' },
    { header: 'Contact', width: 24, value: (row) => row.requester_contact_person },
    { header: 'Company', width: 23, value: (row) => row.requester_company_name },
    { header: 'Email', width: 30, value: (row) => row.requester_email },
    { header: 'Phone', width: 18, value: (row) => row.requester_phone },
    { header: 'Requested items', width: 45, value: (row) => row.items.map((item) => `${item.quantity} x ${item.product_name} (${item.sku || 'No SKU'})`).join('\n') },
    { header: 'Subtotal', width: 15, value: (row) => moneyValue(row.quoted_subtotal), format: 'currency' },
    { header: 'Shipping', width: 14, value: (row) => moneyValue(row.quoted_shipping), format: 'currency' },
    { header: 'Total', width: 15, value: (row) => moneyValue(row.quoted_total), format: 'currency' },
    { header: 'Invoice number', width: 21, value: (row) => row.invoice_number },
    { header: 'Linked order', width: 21, value: (row) => row.order_number },
    { header: 'Messages', width: 45, value: (row) => row.messages.map((message) => `${titleCase(message.sender_role)}: ${message.body}`).join('\n') },
    { header: 'Notes', width: 35, value: (row) => row.notes },
  ]
}

function customerColumns(): Column<User>[] {
  return [
    { header: 'Customer', width: 25, value: (row) => `${row.first_name} ${row.last_name}`.trim() || row.username },
    { header: 'Email', width: 30, value: (row) => row.email },
    { header: 'Phone', width: 18, value: (row) => row.phone_number },
    { header: 'Company', width: 24, value: (row) => row.profile.company_name },
    { header: 'Job title', width: 22, value: (row) => row.profile.job_title },
    { header: 'Address', width: 42, value: address },
    { header: 'Customer account', width: 18, value: (row) => yesNo(row.is_customer) },
    { header: 'Staff account', width: 16, value: (row) => yesNo(row.is_staff) },
    { header: 'Active', width: 12, value: (row) => yesNo(row.is_active) },
    { header: 'Joined', width: 20, value: (row) => dateValue(row.date_joined), format: 'datetime' },
  ]
}

function promotionColumns(): Column<Promotion>[] {
  return [
    { header: 'Code', width: 18, value: (row) => row.code },
    { header: 'Campaign', width: 28, value: (row) => row.title },
    { header: 'Description', width: 40, value: (row) => row.description },
    { header: 'Status', width: 15, value: (row) => titleCase(row.status) },
    { header: 'Discount type', width: 17, value: (row) => titleCase(row.discount_type) },
    { header: 'Discount value', width: 17, value: (row) => Number(row.discount_value), format: (row) => row.discount_type === 'percentage' ? 'percent' : 'currency' },
    { header: 'Starts', width: 20, value: (row) => dateValue(row.starts_at), format: 'datetime' },
    { header: 'Ends', width: 20, value: (row) => dateValue(row.ends_at), format: 'datetime' },
    { header: 'Usage limit', width: 14, value: (row) => row.usage_limit, format: 'integer' },
    { header: 'Redeemed', width: 13, value: (row) => row.times_redeemed, format: 'integer' },
    { header: 'Active', width: 12, value: (row) => yesNo(row.is_active) },
  ]
}

function reportDefinition(report: AdminReport) {
  switch (report.kind) {
    case 'orders': return { title: 'Order Report', sheet: 'Orders', columns: orderColumns(), rows: report.rows }
    case 'products': return { title: 'Product Catalog', sheet: 'Products', columns: productColumns(), rows: report.rows }
    case 'inventory': return { title: 'Inventory Report', sheet: 'Inventory', columns: productColumns(true), rows: report.rows }
    case 'quotes': return { title: 'Quote Report', sheet: 'Quotes', columns: quoteColumns(), rows: report.rows }
    case 'customers': return { title: 'Customer Report', sheet: 'Customers', columns: customerColumns(), rows: report.rows }
    case 'promotions': return { title: 'Promotion Report', sheet: 'Promotions', columns: promotionColumns(), rows: report.rows }
  }
}

function fittedRowHeight(values: CellValue[], widths: number[]) {
  const lines = values.map((value, index) => String(value ?? '').split(/\r?\n/).reduce(
    (count, line) => count + Math.max(1, Math.ceil(line.length / Math.max(1, (widths[index] ?? 12) - 2))), 0,
  ))
  return Math.min(180, Math.max(27, Math.max(...lines) * 15 + 8))
}

export async function exportAdminReport(report: AdminReport) {
  const definition = reportDefinition(report)
  if (!definition.rows.length) {
    toast('There is no data to export yet')
    return
  }

  try {
    const ExcelJS = (await import('exceljs')).default
    const workbook = new ExcelJS.Workbook()
    const generatedAt = new Date()
    workbook.creator = 'Digital PTT'
    workbook.created = generatedAt
    workbook.modified = generatedAt
    workbook.subject = `Digital PTT ${definition.title}`

    const sheet = workbook.addWorksheet(definition.sheet, {
      views: [{ state: 'frozen', ySplit: 4 }],
      pageSetup: { orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
    })
    sheet.columns = definition.columns.map((column, index) => ({ key: `column${index}`, width: column.width }))
    sheet.mergeCells(1, 1, 2, definition.columns.length)
    const title = sheet.getCell(1, 1)
    title.value = `Digital PTT ${definition.title}`
    title.font = { bold: true, size: 22, color: { argb: colors.white } }
    title.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.navy } }
    title.alignment = { vertical: 'middle', horizontal: 'left' }
    sheet.getRow(1).height = 28
    sheet.getRow(2).height = 16
    sheet.mergeCells(3, 1, 3, definition.columns.length)
    const metadata = sheet.getCell(3, 1)
    metadata.value = `Generated ${generatedAt.toLocaleString()} | ${definition.rows.length.toLocaleString()} records`
    metadata.font = { size: 10, color: { argb: colors.muted } }
    metadata.alignment = { vertical: 'middle' }
    sheet.getRow(3).height = 24

    const header = sheet.getRow(4)
    header.values = definition.columns.map((column) => column.header)
    header.height = 30
    header.eachCell((cell) => {
      cell.font = { bold: true, color: { argb: colors.white } }
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.blue } }
      cell.alignment = { vertical: 'middle', horizontal: 'left', wrapText: true }
      cell.border = thinBorder
    })
    sheet.autoFilter = { from: { row: 4, column: 1 }, to: { row: 4, column: definition.columns.length } }

    const columns = definition.columns as Column<never>[]
    const rows = definition.rows as never[]
    rows.forEach((record, index) => {
      const values = columns.map((column) => column.value(record))
      const row = sheet.addRow(values)
      row.height = fittedRowHeight(values, columns.map((column) => column.width))
      row.eachCell({ includeEmpty: true }, (cell, columnIndex) => {
        cell.border = thinBorder
        cell.alignment = { vertical: 'middle', wrapText: true }
        if (index % 2 === 1) cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.paleGray } }
        const formatDefinition = columns[columnIndex - 1]?.format
        const format = typeof formatDefinition === 'function'
          ? formatDefinition(record)
          : formatDefinition
        if (format === 'currency') cell.numFmt = '$#,##0.00'
        if (format === 'integer') cell.numFmt = '#,##0'
        if (format === 'date') cell.numFmt = 'yyyy-mm-dd'
        if (format === 'datetime') cell.numFmt = 'yyyy-mm-dd hh:mm'
        if (format === 'percent') {
          if (typeof cell.value === 'number') cell.value = cell.value / 100
          cell.numFmt = '0.##%'
        }
      })
    })

    const buffer = await workbook.xlsx.writeBuffer()
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([new Uint8Array(buffer)], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
    link.download = `digital-ptt-${report.kind}-${generatedAt.toISOString().slice(0, 10)}.xlsx`
    link.click()
    URL.revokeObjectURL(link.href)
    toast.success(`${definition.title} exported`)
  } catch {
    toast.error('Could not prepare the Excel report')
  }
}
