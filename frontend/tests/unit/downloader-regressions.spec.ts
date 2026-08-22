import { hasCompleteConnectionInfo } from '@/views/downloader/connection'
import { generateExternalPathFromRules } from '@/views/downloader/path-mapping-rules'

describe('downloader settings behavior regressions', () => {
  it.each([
    { name: 'edited downloader with stored password', isEdit: true, password: '', expected: true },
    { name: 'new downloader with password', isEdit: false, password: 'secret', expected: true },
    { name: 'new downloader without password', isEdit: false, password: '', expected: false },
    { name: 'edited downloader with port zero', isEdit: true, password: '', port: 0, expected: false },
    { name: 'missing host', isEdit: true, password: '', host: '', expected: false },
    { name: 'missing username', isEdit: true, password: '', username: '', expected: false }
  ])('keeps connection guard semantics for $name', ({ isEdit, password, port, host, username, expected }) => {
    expect(hasCompleteConnectionInfo({
      host: host ?? '192.168.5.51',
      port: port ?? 19591,
      username: username ?? 'huangzj',
      password
    }, isEdit)).toBe(expected)
  })
})

describe('path mapping rule regressions', () => {
  it('uses the longest matching source prefix and preserves the relative path', () => {
    const rules = [
      '/Downloads{#**#}/mnt/downloads',
      '/Downloads/hpan/bangumi{#**#}/Downloads/bangumi'
    ].join('\n')

    expect(generateExternalPathFromRules(
      '/Downloads/hpan/bangumi/91Days/',
      rules
    )).toBe('/Downloads/bangumi/91Days/')
  })

  it('supports CRLF rule text and returns null for unmatched paths', () => {
    expect(generateExternalPathFromRules(
      '/Downloads/hpan/bangumi/91Days/',
      '/Downloads/hpan/bangumi{#**#}/Downloads/bangumi\r\n'
    )).toBe('/Downloads/bangumi/91Days/')
    expect(generateExternalPathFromRules(
      '/unmatched/path/',
      '/Downloads/hpan/bangumi{#**#}/Downloads/bangumi'
    )).toBeNull()
  })
})
