package com.btdeck.companion.ui

import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
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
