package com.btdeck.companion.ui

import android.content.Intent
import android.content.res.ColorStateList
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.BaseAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ListView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.btdeck.companion.R
import com.btdeck.companion.data.HealthClient
import com.btdeck.companion.data.CredentialRecord
import com.btdeck.companion.data.CredentialVault
import com.btdeck.companion.data.ServerProfile
import com.btdeck.companion.data.ServerProfileStore
import com.btdeck.companion.net.LanHostPolicy
import com.btdeck.companion.server.LocalServerProfile
import com.btdeck.companion.server.LocalServerState
import com.btdeck.companion.util.Hosts
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputLayout
import kotlinx.coroutines.launch
import java.text.DateFormat
import java.util.Date

/**
 * 服务器地址管理（计划 Phase 2）：显示名 + URL + 最近健康状态 + 最后连接时间；
 * 添加时执行 URL/明文策略校验；支持测试连接、忘记服务器（长按）、重跑向导。
 */
class ServerListActivity : AppCompatActivity() {

    private lateinit var store: ServerProfileStore
    private lateinit var credentials: CredentialVault
    private lateinit var adapter: ProfileAdapter
    private val healthClient = HealthClient()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_server_list)
        supportActionBar?.setTitle(R.string.server_list_title)

        store = ServerProfileStore(this)
        credentials = CredentialVault(this)
        adapter = ProfileAdapter()
        val listView = findViewById<ListView>(R.id.server_list)
        listView.adapter = adapter
        listView.onItemClickListener = AdapterView.OnItemClickListener { _, _, position, _ ->
            adapter.profileAt(position)?.let(::openWeb)
        }
        listView.onItemLongClickListener = AdapterView.OnItemLongClickListener { _, _, position, _ ->
            adapter.profileAt(position)?.let(::showProfileActions)
            true
        }
        findViewById<Button>(R.id.btn_add_server).setOnClickListener { showAddDialog() }
    }

    override fun onResume() {
        super.onResume()
        adapter.reload()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menu.add(0, MENU_TEST_ALL, 0, R.string.test_connection)
        menu.add(0, MENU_RERUN_WIZARD, 1, R.string.rerun_wizard)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            MENU_TEST_ALL -> {
                (0 until adapter.count).forEach(adapter::testConnection)
                true
            }
            MENU_RERUN_WIZARD -> {
                startActivity(Intent(this, WizardActivity::class.java))
                finish()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    private fun openWeb(profile: ServerProfile) {
        // 本机服务端 profile：服务未运行时引导回向导启动（WebView 直开只会报不可达）
        if (LocalServerProfile.isLocal(profile) && !LocalServerState.snapshot.isRunning) {
            Toast.makeText(this, R.string.local_server_not_running, Toast.LENGTH_LONG).show()
            return
        }
        // 每次打开前再校验一次策略（NSC 构建变体或 profile 数据变化后的兜底）
        when (val verdict = LanHostPolicy.check(profile.baseUrl, profile.cleartextAllowed)) {
            is LanHostPolicy.Verdict.Ok -> startActivity(
                Intent(this, WebViewActivity::class.java)
                    .putExtra(WebViewActivity.EXTRA_PROFILE_ID, profile.id)
            )
            is LanHostPolicy.Verdict.Reject ->
                Toast.makeText(this, rejectMessage(verdict), Toast.LENGTH_LONG).show()
        }
    }

    private fun confirmForget(profile: ServerProfile) {
        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.forget_server)
            .setMessage("忘记 \"${profile.displayName}\"（${profile.baseUrl}）？\n将同时清除该服务器的本地记录与已信任的证书指纹。")
            .setPositiveButton(android.R.string.ok) { _, _ ->
                store.delete(profile.id)
                credentials.delete(profile.id)
                adapter.reload()
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    private fun showProfileActions(profile: ServerProfile) {
        val actions = arrayOf(
            getString(R.string.edit_server),
            getString(R.string.clear_saved_credentials),
            getString(R.string.forget_server),
        )
        MaterialAlertDialogBuilder(this)
            .setTitle(profile.displayName)
            .setItems(actions) { _, which ->
                if (which == 0) {
                    showAddDialog(profile)
                } else if (which == 1) {
                    credentials.delete(profile.id)
                    Toast.makeText(this, R.string.credentials_cleared, Toast.LENGTH_SHORT).show()
                } else {
                    confirmForget(profile)
                }
            }
            .setNegativeButton(android.R.string.cancel, null)
            .show()
    }

    // ============ 添加服务器对话框（URL 校验 + 明文风险确认） ============

    private fun showAddDialog(existing: ServerProfile? = null) {
        val view = layoutInflater.inflate(R.layout.dialog_add_server, null)
        val nameLayout = view.findViewById<TextInputLayout>(R.id.layout_name)
        val urlLayout = view.findViewById<TextInputLayout>(R.id.layout_url)
        val usernameLayout = view.findViewById<TextInputLayout>(R.id.layout_username)
        val nameInput = view.findViewById<EditText>(R.id.input_name)
        val urlInput = view.findViewById<EditText>(R.id.input_url)
        val usernameInput = view.findViewById<EditText>(R.id.input_username)
        val passwordInput = view.findViewById<EditText>(R.id.input_password)
        val clearSaved = view.findViewById<CheckBox>(R.id.check_clear_saved)
        val consent = view.findViewById<CheckBox>(R.id.check_consent)

        nameInput.setText(existing?.displayName.orEmpty())
        urlInput.setText(existing?.baseUrl.orEmpty())
        usernameInput.setText(existing?.username.orEmpty())
        clearSaved.visibility = if (existing == null) View.GONE else View.VISIBLE
        consent.isChecked = existing?.cleartextAllowed == true

        urlInput.addTextChangedListener(object : android.text.TextWatcher {
            override fun afterTextChanged(s: android.text.Editable?) {
                consent.visibility =
                    if (LanHostPolicy.needsCleartextConsent(s?.toString() ?: "")) View.VISIBLE else View.GONE
            }
            override fun beforeTextChanged(p0: CharSequence?, p1: Int, p2: Int, p3: Int) = Unit
            override fun onTextChanged(p0: CharSequence?, p1: Int, p2: Int, p3: Int) = Unit
        })
        consent.visibility =
            if (LanHostPolicy.needsCleartextConsent(urlInput.text.toString())) View.VISIBLE else View.GONE

        // 输入变化即清除该字段校验错误（对齐旧版 EditText.error 的自动消失行为）
        clearErrorOnType(nameInput, nameLayout)
        clearErrorOnType(urlInput, urlLayout)
        clearErrorOnType(usernameInput, usernameLayout)

        MaterialAlertDialogBuilder(this)
            .setTitle(if (existing == null) R.string.add_server else R.string.edit_server)
            .setView(view)
            .setPositiveButton(android.R.string.ok, null)
            .setNegativeButton(android.R.string.cancel, null)
            .create()
            .apply {
                setOnShowListener {
                    getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                        val name = nameInput.text.toString().trim()
                        val url = urlInput.text.toString().trim()
                        val username = usernameInput.text.toString().trim()
                        val password = passwordInput.text.toString()
                        val parsed = Hosts.parse(url)
                        when {
                            name.isEmpty() -> nameLayout.error = "请输入显示名称"
                            password.isNotEmpty() && username.isEmpty() ->
                                usernameLayout.error = "填写密码时必须输入用户名"
                            parsed == null -> urlLayout.error = "地址无效（仅支持 http/https）"
                            else -> {
                                val consentGranted = consent.isChecked
                                when (val verdict =
                                    LanHostPolicy.checkParsed(parsed.scheme, parsed.host, consentGranted)) {
                                    is LanHostPolicy.Verdict.Ok -> {
                                        val profile = existing ?: ServerProfile(
                                            displayName = name,
                                            baseUrl = parsed.baseUrl,
                                            username = username,
                                            cleartextAllowed = consentGranted && parsed.scheme == "http",
                                        )
                                        val urlChanged = existing != null && profile.baseUrl != parsed.baseUrl
                                        profile.displayName = name
                                        profile.baseUrl = parsed.baseUrl
                                        profile.username = username
                                        profile.cleartextAllowed = consentGranted && parsed.scheme == "http"
                                        if (urlChanged) profile.trustedCertFingerprints.clear()
                                        store.upsert(profile)
                                        when {
                                            clearSaved.isChecked || username.isEmpty() ->
                                                credentials.delete(profile.id)
                                            password.isNotEmpty() ->
                                                credentials.save(profile.id, CredentialRecord(username, password))
                                            urlChanged -> credentials.delete(profile.id)
                                            existing != null -> {
                                                credentials.get(profile.id)?.let {
                                                    credentials.save(profile.id, CredentialRecord(username, it.password))
                                                }
                                            }
                                        }
                                        adapter.reload()
                                        dismiss()
                                    }
                                    is LanHostPolicy.Verdict.Reject ->
                                        urlLayout.error = rejectMessage(verdict)
                                }
                            }
                        }
                    }
                }
            }
            .show()
    }

    private fun clearErrorOnType(input: EditText, layout: TextInputLayout) {
        input.addTextChangedListener(object : android.text.TextWatcher {
            override fun afterTextChanged(s: android.text.Editable?) {
                layout.error = null
            }
            override fun beforeTextChanged(p0: CharSequence?, p1: Int, p2: Int, p3: Int) = Unit
            override fun onTextChanged(p0: CharSequence?, p1: Int, p2: Int, p3: Int) = Unit
        })
    }

    private fun rejectMessage(verdict: LanHostPolicy.Verdict.Reject): String = when (verdict.reason) {
        LanHostPolicy.Reason.MALFORMED_URL -> "地址无效（仅支持 http/https）"
        LanHostPolicy.Reason.SCHEME_NOT_ALLOWED -> "仅支持 http/https"
        LanHostPolicy.Reason.HTTP_PUBLIC_HOST ->
            "明文 HTTP 仅允许私有局域网地址（如 192.168.x.x、10.x.x.x、*.local）；公网地址请使用 HTTPS"
        LanHostPolicy.Reason.HTTP_LAN_WITHOUT_CONSENT ->
            "私有地址使用明文 HTTP 需先勾选风险确认"
    }

    // ============ 列表 ============

    private inner class ProfileAdapter : BaseAdapter() {
        private val profiles = mutableListOf<ServerProfile>()

        fun reload() {
            profiles.clear()
            profiles.addAll(store.loadAll())
            notifyDataSetChanged()
        }

        fun profileAt(position: Int): ServerProfile? = profiles.getOrNull(position)

        override fun getCount(): Int = profiles.size

        override fun getItem(position: Int): ServerProfile = profiles[position]

        override fun getItemId(position: Int): Long = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val view = convertView ?: layoutInflater.inflate(R.layout.row_server, parent, false)
            val profile = profiles[position]
            view.findViewById<TextView>(R.id.row_name).text = profile.displayName
            view.findViewById<TextView>(R.id.row_url).text = profile.baseUrl

            // 健康状态语义色（同前端 --color-success/warning/error），圆点与文案同色
            val healthColor = view.context.getColor(HealthUi.colorRes(profile.healthState))
            view.findViewById<TextView>(R.id.row_health).apply {
                text = HealthUi.label(profile.healthState)
                setTextColor(healthColor)
            }
            view.findViewById<View>(R.id.row_health_dot).backgroundTintList =
                ColorStateList.valueOf(healthColor)

            val meta = StringBuilder()
            profile.serverVersion?.let { meta.append("v").append(it).append(" · ") }
            meta.append("健康: ").append(relativeTime(profile.lastHealthCheckedAt))
            meta.append(" · 连接: ").append(relativeTime(profile.lastConnectedAt))
            view.findViewById<TextView>(R.id.row_meta).text = meta.toString()
            return view
        }

        fun testConnection(position: Int) {
            val profile = profileAt(position) ?: return
            lifecycleScope.launch {
                val report = healthClient.check(profile.baseUrl, profile.trustedCertFingerprints.toSet())
                profile.healthState = report.state
                profile.serverVersion = report.version
                profile.lastHealthCheckedAt = System.currentTimeMillis()
                store.upsert(profile)
                reload()
                Toast.makeText(
                    this@ServerListActivity,
                    "${profile.displayName}: ${report.detail}", Toast.LENGTH_SHORT
                ).show()
            }
        }
    }

    private fun relativeTime(epochMs: Long): String =
        if (epochMs <= 0) "从未"
        else DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(Date(epochMs))

    companion object {
        private const val MENU_TEST_ALL = 1
        private const val MENU_RERUN_WIZARD = 2
    }
}
