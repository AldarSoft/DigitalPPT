import { toast } from 'sonner'

export function exportCsv(filename: string, rows: object[]) {
    if (!rows.length) {
        toast('There is no data to export yet');
        return;
    }
    const data = rows.map((row) => {
        const record = row as Record<string, unknown>;
        return Object.fromEntries(Object.entries(record).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value)));
    });
    const headers = Object.keys(data[0]);
    const csv = [headers.join(','), ...data.map((row) => headers.map((header) => `"${String(row[header] ?? '').replaceAll('"', '""')}"`).join(','))].join('\n');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
}

