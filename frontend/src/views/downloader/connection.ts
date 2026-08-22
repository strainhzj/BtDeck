import { DownloaderFormData } from './types'

/**
 * Determines whether the connection test has enough credentials to start.
 * Existing downloaders may leave password blank so the backend can reuse the
 * encrypted password already stored for that downloader.
 */
export function hasCompleteConnectionInfo(
  formData: Pick<DownloaderFormData, 'host' | 'port' | 'username' | 'password'>,
  isEdit: boolean
): boolean {
  return Boolean(
    formData.host &&
    formData.port &&
    formData.username &&
    (isEdit || formData.password)
  )
}
