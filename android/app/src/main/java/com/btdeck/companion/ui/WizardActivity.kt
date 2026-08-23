package com.btdeck.companion.ui

import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.btdeck.companion.BuildConfig
import com.btdeck.companion.R

/**
 * 首启向导（计划 Phase 2）：模式二选一，支持重新选择。
 * - 伴侣模式：连接已有服务器（MVP 交付）；
 * - 服务端模式：本机 Python 服务端（Phase 3 交付，当前给明确的"未提供"状态，
 *   不留假入口）。
 */
class WizardActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_wizard)

        // 构建标识：明文 LAN 需专用构建变体，误装严格版会遇到
        // ERR_CLEARTEXT_NOT_PERMITTED——在向导页直接可见当前构建能力
        findViewById<TextView>(R.id.wizard_subtitle).text =
            if (BuildConfig.LAN_CLEARTEXT_BUILD) {
                getString(R.string.wizard_subtitle) + "（LAN 明文构建）"
            } else {
                getString(R.string.wizard_subtitle) + "（严格 HTTPS/回环构建：局域网 http 需 LAN 明文构建版）"
            }

        findViewById<android.view.View>(R.id.card_companion).setOnClickListener {
            startActivity(Intent(this, ServerListActivity::class.java))
        }

        findViewById<android.view.View>(R.id.card_local).setOnClickListener {
            AlertDialog.Builder(this)
                .setTitle(R.string.wizard_local_title)
                .setMessage("本机服务端模式将在后续版本提供（Phase 3）。当前版本请使用\"连接已有服务器\"。")
                .setPositiveButton(android.R.string.ok, null)
                .show()
        }
    }
}
