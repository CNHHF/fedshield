/** 文件下载工具：把后端返回的 Blob 保存为本地文件 */

export function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob instanceof Blob ? blob : new Blob([blob]))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

/**
 * 从 axios 响应中解析文件名（优先取 Content-Disposition）并下载
 * @param {Object} response axios 原始响应（responseType: 'blob'）
 * @param {String} fallback 兜底文件名
 */
export function downloadResponse(response, fallback = 'export.csv') {
  const disposition =
    response.headers?.['content-disposition'] || response.headers?.['Content-Disposition'] || ''
  let filename = fallback
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition)
  const plainMatch = /filename="?([^";]+)"?/i.exec(disposition)
  if (utf8Match) {
    filename = decodeURIComponent(utf8Match[1])
  } else if (plainMatch) {
    filename = plainMatch[1]
  }
  downloadBlob(response.data, filename)
}

/** 把前端数据导出为 CSV（带 BOM，保证 Excel 中文不乱码） */
export function exportCsv(rows, columns, filename = 'export.csv') {
  const header = columns.map((item) => item.label).join(',')
  const body = rows
    .map((row) =>
      columns
        .map((column) => {
          const value = typeof column.prop === 'function' ? column.prop(row) : row[column.prop]
          const text = value === null || value === undefined ? '' : String(value)
          return `"${text.replace(/"/g, '""')}"`
        })
        .join(',')
    )
    .join('\n')
  downloadBlob(new Blob([`\uFEFF${header}\n${body}`], { type: 'text/csv;charset=utf-8' }), filename)
}
