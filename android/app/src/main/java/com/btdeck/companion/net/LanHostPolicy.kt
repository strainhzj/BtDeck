package com.btdeck.companion.net

import com.btdeck.companion.util.Hosts

/**
 * 明文 HTTP 准入策略（计划 Phase 2：明文仅按用户选择的私有 LAN 主机放行，
 * 不做全局 cleartext）。
 *
 * 双层防线：
 * 1. 构建层（NSC）：默认 cleartext 全局禁止；LAN 明文需要显式的
 *    `-Pbtdeck.lanCleartext=true` 构建（平台限制 NSC 无法运行时改）；
 * 2. 应用层（本类）：无论 NSC 如何构建，http URL 必须同时满足
 *    "主机是私有 LAN 字面量" + "用户已为该 profile 显式确认明文风险"。
 *    公网主机即使 https 之外的任何 http 形态都拒绝。
 */
object LanHostPolicy {

    enum class Reason {
        MALFORMED_URL,
        SCHEME_NOT_ALLOWED,
        HTTP_PUBLIC_HOST,
        HTTP_LAN_WITHOUT_CONSENT,
    }

    sealed class Verdict {
        object Ok : Verdict()
        data class Reject(val reason: Reason, val host: String = "") : Verdict()

        val isOk: Boolean get() = this is Ok
    }

    /**
     * @param rawUrl 用户输入的服务器地址
     * @param cleartextConsent 该 profile 是否已记录明文风险确认
     */
    fun check(rawUrl: String, cleartextConsent: Boolean): Verdict {
        val parsed = Hosts.parse(rawUrl) ?: return Verdict.Reject(Reason.MALFORMED_URL)
        return checkParsed(parsed.scheme, parsed.host, cleartextConsent)
    }

    fun checkParsed(scheme: String, host: String, cleartextConsent: Boolean): Verdict {
        if (scheme == "https") return Verdict.Ok
        // scheme 只可能是 http/https（Hosts.parse 已过滤）
        return when {
            !Hosts.isPrivateLanHost(host) ->
                Verdict.Reject(Reason.HTTP_PUBLIC_HOST, host)
            !cleartextConsent ->
                Verdict.Reject(Reason.HTTP_LAN_WITHOUT_CONSENT, host)
            else -> Verdict.Ok
        }
    }

    /** 该 URL 是否需要展示明文风险确认（http + 私有主机）。 */
    fun needsCleartextConsent(rawUrl: String): Boolean {
        val parsed = Hosts.parse(rawUrl) ?: return false
        return parsed.scheme == "http" && Hosts.isPrivateLanHost(parsed.host)
    }
}
