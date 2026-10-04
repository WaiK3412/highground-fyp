// Malaysian names carry patronymic particles and honorifics that are not
// initials: "Siti binti Rahman" is SR, "Encik Zulkifli bin Hassan" is ZH.
const SKIP = new Set(['bin', 'binti', 'bt', 'a/l', 'a/p', 's/o', 'd/o', 'encik', 'cik', 'puan', 'tuan', 'dr', 'dr.'])

export function initials(fullName = '') {
  const parts = fullName.split(/\s+/).filter((part) => part && !SKIP.has(part.toLowerCase()))
  if (parts.length === 0) return '?'
  const picked = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts
  return picked.map((part) => part[0].toUpperCase()).join('')
}
