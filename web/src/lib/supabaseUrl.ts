export function resolveSupabaseUrl(rawUrl: string, origin: string): string {
  if (/^https?:\/\//i.test(rawUrl)) {
    return rawUrl
  }

  return new URL(rawUrl, origin).toString()
}
