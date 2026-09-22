/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/**
 * MCP service domain (settings panel; bilingual batch after the v1.0.7 merge).
 * Capability catalog copy (tool names/descriptions) comes from the backend GET
 * response and passes through verbatim (E03 semantics); not maintained here.
 */
export const mcp = {
  panel: {
    title: 'MCP Service',
    description: 'The MCP (Model Context Protocol) service lets external AI clients call controlled torrent queries, tagging, and task triggers after authentication. The service and every capability are off by default; disabled capabilities are undiscoverable by clients, and direct calls using a cached stale definition are rejected by the server.',
    loading: 'Loading...',
    loadFailed: 'Failed to load MCP configuration.',
    retry: 'Retry',
    forceDisabledTitle: 'The environment emergency switch has force-disabled the MCP service (BTDECK_MCP_FORCE_DISABLED=True)',
    forceDisabledDesc: 'The configuration below is not in effect for now; saving keeps the intended configuration, which takes effect again once the emergency measure is lifted.',
    globalSwitch: 'Global switch',
    stateOn: 'On',
    stateOff: 'Off',
    forceEffectiveOff: '(currently effective: off)',
    capabilityHint: 'After turning on the global switch, enable the capabilities you need individually; with no capability enabled the tool list stays empty.',
    neverSaved: 'Configuration has never been saved',
    revisionInfo: 'Current revision {revision} · {time}{by}',
    bySuffix: ' ({by})',
    discard: 'Discard changes',
    save: 'Save configuration'
  },
  risk: {
    high: 'High risk',
    write: 'Write',
    read: 'Read-only',
    noteHigh: 'High-risk capability: external side effects or task execution; calls require explicit confirmation and an idempotency key plus mandatory audit. Confirm you trust the caller before enabling.',
    noteWrite: 'Write operation: calls require explicit confirmation and an idempotency key, and are audit-logged.'
  },
  msg: {
    saved: 'MCP configuration saved',
    conflict: 'The configuration was modified in another session; the latest configuration has been reloaded — review it and retry',
    saveFailed: 'Failed to save MCP configuration; please try again later'
  }
}
