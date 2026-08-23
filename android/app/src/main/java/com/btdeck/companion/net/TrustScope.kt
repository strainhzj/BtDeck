package com.btdeck.companion.net

import android.net.http.SslCertificate
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

/**
 * 自签证书信任范围（计划 Phase 2：自签证书必须由用户显式信任并记录范围，
 * 禁止无条件 handler.proceed()）。
 *
 * 作用域语义：指纹记录在单个 ServerProfile 上（= 信任绑定到"这一个服务器
 * 地址"），更换服务器地址后旧指纹不生效；证书轮换需用户再次确认。
 */
object TrustScope {

    private const val BUNDLE_X509_KEY = "x509-certificate"

    /** 计算 SslCertificate 的 SHA-256 指纹（十六进制冒号分隔）；无 X509 载荷返回 null。 */
    fun sha256Fingerprint(certificate: SslCertificate): String? {
        val bundle = SslCertificate.saveState(certificate) ?: return null
        val encoded = bundle.getByteArray(BUNDLE_X509_KEY) ?: return null
        val factory = CertificateFactory.getInstance("X.509")
        val x509 = factory.generateCertificate(encoded.inputStream()) as? X509Certificate ?: return null
        val digest = MessageDigest.getInstance("SHA-256").digest(x509.encoded)
        return digest.joinToString(":") { byte -> "%02X".format(byte) }
    }
}
