const rawHideDownloadDocTypes = import.meta.env.VITE_HIDE_DOWNLOAD_DOC_TYPES ?? ''

export const HIDE_DOWNLOAD_DOC_TYPES = rawHideDownloadDocTypes
  .split(',')
  .map((type) => type.trim())
  .filter(Boolean)

export const shouldHideDownloadForType = (documentType?: string | null) => {
  if (!documentType) return false
  return HIDE_DOWNLOAD_DOC_TYPES.includes(documentType)
}
