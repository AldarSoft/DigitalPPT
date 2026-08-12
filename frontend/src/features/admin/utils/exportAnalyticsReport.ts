import type { Order } from '../../../types'

type ReportFilters = { search: string; status: string }

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

function fittedRowHeight(values: unknown[], widths: number[]) {
  const wrappedLines = values.map((value, index) => {
    const availableCharacters = Math.max(1, (widths[index] ?? 12) - 2)
    return String(value ?? '').split(/\r?\n/).reduce(
      (lineCount, line) => lineCount + Math.max(1, Math.ceil(line.length / availableCharacters)),
      0,
    )
  })
  return Math.min(409, Math.max(32, Math.max(...wrappedLines) * 15 + 8))
}

export async function exportAnalyticsReport(orders: Order[], filters: ReportFilters) {
  const ExcelJS = (await import('exceljs')).default
  const workbook = new ExcelJS.Workbook()
  const generatedAt = new Date()
  const completed = orders.filter((order) => order.status === 'completed')
  const revenue = completed.reduce((total, order) => total + Number(order.total), 0)
  const average = completed.length ? revenue / completed.length : 0
  const completionRate = orders.length ? completed.length / orders.length : 0

  workbook.creator = 'Digital PTT'
  workbook.created = generatedAt
  workbook.modified = generatedAt
  workbook.subject = 'Digital PTT business analytics report'

  const summary = workbook.addWorksheet('Summary', {
    views: [{ state: 'frozen', ySplit: 4 }],
    pageSetup: { orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
  })
  summary.columns = [
    { key: 'a', width: 24 }, { key: 'b', width: 18 }, { key: 'c', width: 4 },
    { key: 'd', width: 24 }, { key: 'e', width: 18 }, { key: 'f', width: 4 },
  ]
  summary.mergeCells('A1:F2')
  summary.getCell('A1').value = 'Digital PTT Business Analytics'
  summary.getCell('A1').font = { bold: true, size: 22, color: { argb: colors.white } }
  summary.getCell('A1').fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.navy } }
  summary.getCell('A1').alignment = { vertical: 'middle', horizontal: 'left' }
  summary.getRow(1).height = 28
  summary.getRow(2).height = 16
  summary.mergeCells('A3:F3')
  const filterLabel = [
    filters.status ? `Status: ${filters.status}` : 'All statuses',
    filters.search ? `Search: ${filters.search}` : null,
  ].filter(Boolean).join(' | ')
  summary.getCell('A3').value = `Generated ${generatedAt.toLocaleString()} | ${filterLabel}`
  summary.getCell('A3').font = { size: 10, color: { argb: colors.muted } }

  const metrics: Array<[string, number, string, number]> = [
    ['Completed revenue', revenue, 'Total orders', orders.length],
    ['Completion rate', completionRate, 'Average completed order', average],
  ]
  metrics.forEach((metric, index) => {
    const row = 5 + index * 3
    summary.getCell(`A${row}`).value = metric[0]
    summary.getCell(`A${row + 1}`).value = metric[1]
    summary.getCell(`D${row}`).value = metric[2]
    summary.getCell(`D${row + 1}`).value = metric[3]
    const labelCells = [`A${row}`, `D${row}`]
    const valueCells = [`A${row + 1}`, `D${row + 1}`]
    labelCells.forEach((address) => {
      summary.getCell(address).font = { bold: true, size: 10, color: { argb: colors.muted } }
      summary.getCell(address).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.paleBlue } }
      summary.getCell(address).border = thinBorder
    })
    valueCells.forEach((address) => {
      summary.getCell(address).font = { bold: true, size: 18, color: { argb: colors.text } }
      summary.getCell(address).border = thinBorder
    })
  })
  summary.getCell('A6').numFmt = '$#,##0.00'
  summary.getCell('D6').numFmt = '#,##0'
  summary.getCell('A9').numFmt = '0.0%'
  summary.getCell('D9').numFmt = '$#,##0.00'

  summary.getCell('A12').value = 'Order status breakdown'
  summary.getCell('A12').font = { bold: true, size: 14, color: { argb: colors.text } }
  summary.addRow([])
  const statusHeader = summary.addRow(['Status', 'Orders'])
  statusHeader.eachCell((cell) => {
    cell.font = { bold: true, color: { argb: colors.white } }
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.blue } }
    cell.border = thinBorder
  })
  const statuses: Order['status'][] = ['pending', 'scheduled', 'processing', 'completed', 'cancelled']
  statuses.forEach((status) => {
    const label = status[0].toUpperCase() + status.slice(1)
    const row = summary.addRow([label, orders.filter((order) => order.status === status).length])
    row.eachCell((cell) => { cell.border = thinBorder })
    row.getCell(2).numFmt = '#,##0'
  })

  const ordersSheet = workbook.addWorksheet('Orders', {
    views: [{ state: 'frozen', ySplit: 1 }],
    pageSetup: { orientation: 'landscape', fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
  })
  ordersSheet.columns = [
    { header: 'Order number', key: 'orderNumber', width: 21 },
    { header: 'Date', key: 'date', width: 13 },
    { header: 'Customer', key: 'customer', width: 24 },
    { header: 'Company', key: 'company', width: 22 },
    { header: 'Email', key: 'email', width: 30 },
    { header: 'Status', key: 'status', width: 14 },
    { header: 'Items', key: 'items', width: 42 },
    { header: 'Subtotal', key: 'subtotal', width: 14 },
    { header: 'Total', key: 'total', width: 14 },
    { header: 'Shipping address', key: 'shipping', width: 40 },
    { header: 'Notes', key: 'notes', width: 32 },
  ]
  ordersSheet.autoFilter = { from: 'A1', to: 'K1' }
  const header = ordersSheet.getRow(1)
  header.height = 28
  header.eachCell((cell) => {
    cell.font = { bold: true, color: { argb: colors.white } }
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.navy } }
    cell.alignment = { vertical: 'middle', horizontal: 'left' }
    cell.border = thinBorder
  })

  orders.forEach((order, index) => {
    const shipping = [order.shipping_address, order.shipping_city, order.shipping_state,
      order.shipping_postal_code, order.shipping_country].filter(Boolean).join(', ')
    const items = order.items.map((item) => `${item.quantity} x ${item.product_name} (${item.sku})`).join('; ')
    const values = {
      orderNumber: order.order_number,
      date: new Date(order.created_at),
      customer: `${order.customer_first_name} ${order.customer_last_name}`.trim(),
      company: order.company_name,
      email: order.customer_email,
      status: order.status[0].toUpperCase() + order.status.slice(1),
      items,
      subtotal: Number(order.subtotal),
      total: Number(order.total),
      shipping,
      notes: order.notes,
    }
    const row = ordersSheet.addRow(values)
    row.height = fittedRowHeight(
      [values.orderNumber, values.date.toISOString().slice(0, 10), values.customer,
        values.company, values.email, values.status, values.items, values.subtotal,
        values.total, values.shipping, values.notes],
      ordersSheet.columns.map((column) => column.width ?? 12),
    )
    row.eachCell((cell) => {
      cell.border = thinBorder
      cell.alignment = { vertical: 'middle', wrapText: true }
      if (index % 2 === 1)
        cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: colors.paleGray } }
    })
    row.getCell(2).numFmt = 'yyyy-mm-dd'
    row.getCell(8).numFmt = '$#,##0.00'
    row.getCell(9).numFmt = '$#,##0.00'
  })

  const buffer = await workbook.xlsx.writeBuffer()
  const blob = new Blob([new Uint8Array(buffer)], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `digital-ptt-analytics-${generatedAt.toISOString().slice(0, 10)}.xlsx`
  link.click()
  URL.revokeObjectURL(link.href)
}
