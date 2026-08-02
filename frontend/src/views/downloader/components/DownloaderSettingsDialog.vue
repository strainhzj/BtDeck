<template>
  <el-dialog
    :visible.sync="visible"
    :before-close="handleClose"
    :close-on-click-modal="false"
    :show-close="false"
    append-to-body
    width="94%"
    top="0"
    custom-class="downloader-settings-dialog"
    @opened="handleDialogOpened"
  >
    <template slot="title">
      <div class="workspace-header">
        <div class="workspace-header__identity">
          <span class="workspace-header__mark">
            <LucideIcon :name="isEdit ? 'folder-cog' : 'plug-zap'" :size="23" :stroke-width="1.65" />
          </span>
          <div>
            <div class="workspace-eyebrow">
              {{ isEdit ? 'NODE CONFIGURATION / EDIT' : 'NODE CONFIGURATION / ONBOARD' }}
            </div>
            <h2>{{ dialogTitle }}</h2>
          </div>
        </div>
        <div class="workspace-header__context">
          <span>
            <LucideIcon name="database" :size="13" :stroke-width="1.8" />
            {{ downloaderTypeLabel }}
          </span>
          <span>
            <LucideIcon :name="isEdit ? 'pencil' : 'plus'" :size="13" :stroke-width="1.8" />
            {{ isEdit ? '编辑模式' : '新增模式' }}
          </span>
          <button type="button" aria-label="关闭下载器设置" @click="handleClose">
            <LucideIcon name="x" :size="18" :stroke-width="1.9" />
          </button>
        </div>
      </div>
    </template>

    <el-tabs v-model="activeTab" tab-position="left" class="settings-tabs">
      <!-- 标签页1: 基本信息（合并后） -->
      <el-tab-pane name="basic">
        <span slot="label" class="workspace-tab-label">
          <span class="workspace-tab-label__icon">
            <LucideIcon name="sliders-horizontal" :size="17" :stroke-width="1.8" />
          </span>
          <span class="workspace-tab-label__copy">
            <strong>基本信息</strong>
            <small>连接、认证与行为</small>
          </span>
        </span>
        <div class="tab-content tab-content--basic">
          <div class="panel-intro">
            <div>
              <span>01 / CONNECTION CORE</span>
              <h3>{{ isEdit ? '节点连接与基础策略' : '接入新的下载节点' }}</h3>
              <p>完成地址、认证与存储路径配置，并在保存前验证链路。</p>
            </div>
            <span class="panel-intro__badge">
              <LucideIcon name="cable" :size="14" :stroke-width="1.8" />
              核心配置
            </span>
          </div>
          <el-form
            ref="basicFormRef"
            :model="formData"
            :rules="basicFormRules"
            label-width="140px"
            class="workspace-basic-form"
          >
            <!-- 连接配置 -->
            <div class="form-section">
              <div class="form-section-title">
                <LucideIcon name="cable" :size="18" :stroke-width="1.8" class="section-icon" />
                连接配置
              </div>
              <div class="form-section-card">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-form-item label="下载器名称" prop="nickname">
                      <el-input
                        v-model="formData.nickname"
                        placeholder="请输入下载器名称"
                        clearable
                      >
                        <template slot="prefix">
                          <LucideIcon name="user-round" :size="15" :stroke-width="1.8" class="input-icon" />
                        </template>
                      </el-input>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item label="端口" prop="port">
                      <el-input-number
                        v-model="formData.port"
                        :min="1"
                        :max="65535"
                        :controls="false"
                        style="width: 100%;"
                      />
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-form-item label="主机地址" prop="host">
                      <el-input
                        v-model="formData.host"
                        placeholder="例如: 192.168.1.100"
                        clearable
                      >
                        <template slot="prefix">
                          <LucideIcon name="server" :size="15" :stroke-width="1.8" class="input-icon" />
                        </template>
                      </el-input>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item label="下载器类型" prop="downloader_type">
                      <el-select
                        v-model="formData.downloader_type"
                        placeholder="请选择下载器类型"
                        style="width: 100%;"
                        :disabled="isEdit"
                      >
                        <el-option label="qBittorrent" :value="0" />
                        <el-option label="Transmission" :value="1" />
                      </el-select>
                    </el-form-item>
                  </el-col>
                </el-row>

                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-form-item label="HTTPS" prop="is_ssl">
                      <div class="switch-control">
                        <span class="switch-label-text">{{ formData.is_ssl === '1' ? '已启用' : '已禁用' }}</span>
                        <el-switch
                          v-model="formData.is_ssl"
                          active-value="1"
                          inactive-value="0"
                          active-color="#059669"
                          inactive-color="#d1d5db"
                        />
                      </div>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                  </el-col>
                </el-row>
              </div>
            </div>

            <!-- 认证信息 -->
            <div class="form-section">
              <div class="form-section-title">
                <LucideIcon name="lock-keyhole" :size="18" :stroke-width="1.8" class="section-icon" />
                认证信息
              </div>
              <div class="form-section-card">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-form-item label="用户名" prop="username">
                      <el-input
                        v-model="formData.username"
                        placeholder="请输入用户名"
                        clearable
                      >
                        <template slot="prefix">
                          <LucideIcon name="user-round" :size="15" :stroke-width="1.8" class="input-icon" />
                        </template>
                      </el-input>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <el-form-item label="密码" prop="password">
                      <el-input
                        v-model="formData.password"
                        type="password"
                        show-password
                        :placeholder="isEdit ? '不修改密码请留空' : '请输入密码'"
                        clearable
                      >
                        <template slot="prefix">
                          <LucideIcon name="key-round" :size="15" :stroke-width="1.8" class="input-icon" />
                        </template>
                      </el-input>
                    </el-form-item>
                  </el-col>
                </el-row>
                <!-- 原密码字段：仅在编辑模式下，用户名改变或密码有输入时显示 -->
                <el-row v-if="showOldPassword" :gutter="16">
                  <el-col :span="12">
                    <el-form-item label="原密码" prop="old_password" :rules="[{required: true, message: '请输入原密码', trigger: 'blur'}]">
                      <el-input
                        v-model="formData.old_password"
                        type="password"
                        show-password
                        placeholder="请输入原密码以验证身份"
                        clearable
                      >
                        <template slot="prefix">
                          <LucideIcon name="lock-keyhole" :size="15" :stroke-width="1.8" class="input-icon" />
                        </template>
                      </el-input>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <div class="old-password-hint">
                      <LucideIcon name="info" :size="13" :stroke-width="1.8" class="help-icon" />
                      <span>修改用户名或密码时需要验证原密码</span>
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>

            <!-- 配置选项 -->
            <div class="form-section">
              <div class="form-section-title">
                <LucideIcon name="settings" :size="18" :stroke-width="1.8" class="section-icon" />
                配置选项
              </div>
              <div class="form-section-card">
                <div class="override-setting-item">
                  <div class="override-setting-content">
                    <div class="override-setting-title">覆盖下载器本地配置</div>
                    <div class="override-setting-desc">启用后，将强制覆盖下载器本地的配置项，建议谨慎使用</div>
                  </div>
                  <el-switch
                    v-model="formData.override_local"
                    active-color="#059669"
                    inactive-color="#d1d5db"
                  />
                </div>
              </div>
            </div>

            <!-- 连接测试 -->
            <div class="form-section">
              <div class="form-section-title">
                <LucideIcon name="activity" :size="18" :stroke-width="1.8" class="section-icon" />
                连接测试
              </div>
              <div class="form-section-card">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-button
                      type="primary"
                      :disabled="testing"
                      @click="handleTestConnection"
                      style="width: 100%;"
                      size="medium"
                    >
                      <LucideIcon
                        v-if="!testing"
                        name="activity"
                        :size="15"
                        :stroke-width="1.9"
                        class="button-icon"
                      />
                      <LucideIcon
                        v-else
                        name="refresh-cw"
                        :size="15"
                        :stroke-width="1.9"
                        class="button-icon is-spinning"
                      />
                      {{ testing ? '测试中...' : '测试连接' }}
                    </el-button>
                  </el-col>
                  <el-col :span="12">
                    <div v-if="testResult" :class="['test-result', testResult.success ? 'success' : 'error']">
                      <LucideIcon
                        :name="testResult.success ? 'circle-check-big' : 'circle-x'"
                        :size="16"
                        :stroke-width="1.9"
                        class="result-icon"
                      />
                      <span>{{ testResult.message }}</span>
                    </div>
                    <div v-else class="test-result-placeholder">
                      点击按钮测试连接
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>

            <!-- 功能开关 -->
            <div class="form-section">
              <div class="form-section-title">
                <LucideIcon name="power" :size="18" :stroke-width="1.8" class="section-icon" />
                功能开关
              </div>
              <div class="form-section-card">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <div class="feature-switch-item">
                      <div class="feature-switch-content">
                        <div class="feature-switch-title">启用搜索功能</div>
                        <div class="feature-switch-desc">允许此下载器用于种子搜索</div>
                      </div>
                      <el-switch
                        v-model="formData.is_search"
                        active-value="1"
                        inactive-value="0"
                        active-color="#059669"
                        inactive-color="#d1d5db"
                      />
                    </div>
                  </el-col>
                  <el-col :span="12">
                    <div class="feature-switch-item">
                      <div class="feature-switch-content">
                        <div class="feature-switch-title">启用下载器</div>
                        <div class="feature-switch-desc">启用后此下载器将正常工作</div>
                      </div>
                      <el-switch
                        v-model="formData.enabled"
                        active-value="1"
                        inactive-value="0"
                        active-color="#059669"
                        inactive-color="#d1d5db"
                      />
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>

            <!-- 存储配置 -->
            <div class="form-section">
              <div class="form-section-title">
                <LucideIcon name="folder-open" :size="18" :stroke-width="1.8" class="section-icon" />
                存储配置
              </div>
              <div class="form-section-card">
                <el-form-item label="种子保存目录" prop="torrent_save_path">
                  <el-input
                    v-model="formData.torrent_save_path"
                    placeholder="例如: /downloads/torrents 或 C:\Downloads\Torrents"
                    clearable
                  >
                    <template slot="prefix">
                      <LucideIcon name="folder-open" :size="15" :stroke-width="1.8" class="input-icon" />
                    </template>
                  </el-input>
                  <div class="form-item-help">
                    <LucideIcon name="info" :size="13" :stroke-width="1.8" class="help-icon" />
                    <span>保存种子文件的目录路径，必须为应用运行环境可直接访问的绝对路径</span>
                  </div>
                </el-form-item>
              </div>
            </div>

            <!-- 路径映射规则 -->
            <div class="form-section">
              <div class="form-section-title">
                <LucideIcon name="route" :size="18" :stroke-width="1.8" class="section-icon" />
                路径映射规则
              </div>
              <div class="form-section-card">
                <el-form-item label="路径转换规则" prop="path_mapping_rules">
                  <el-input
                    v-model="formData.path_mapping_rules"
                    type="textarea"
                    :rows="6"
                    placeholder="每行一条规则，格式：源路径{#**#}目标路径&#10;&#10;示例：&#10;/downloads{#**#}/volume1&#10;/volume1/downloads{#**#}/mnt/downloads&#10;&#10;转换类型自动判断：&#10;- /downloads{#**#}/volume1 → 加（结果：/volume1/downloads）&#10;- /downloads{#**#}/volume1/downloads → 替换（结果：/volume1/downloads）&#10;&#10;留空表示不进行路径转换"
                    clearable
                  />
                  <div class="form-item-help">
                    <LucideIcon name="info" :size="13" :stroke-width="1.8" class="help-icon" />
                    <span>路径转换规则用于定时任务扫描路径时自动生成外部路径。规则为空时表示路径相等（不转换）。</span>
                  </div>
                </el-form-item>
              </div>
            </div>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 标签页2: 速度设置 -->
      <el-tab-pane name="speed" :disabled="!isEdit">
        <span slot="label" class="workspace-tab-label">
          <span class="workspace-tab-label__icon">
            <LucideIcon name="gauge" :size="17" :stroke-width="1.8" />
          </span>
          <span class="workspace-tab-label__copy">
            <strong>速度设置</strong>
            <small>全局与分时段限速</small>
          </span>
          <LucideIcon v-if="!isEdit" name="lock-keyhole" :size="12" :stroke-width="1.8" class="workspace-tab-label__lock" />
        </span>
        <div class="tab-content">
          <div class="panel-intro">
            <div>
              <span>02 / BANDWIDTH ENGINE</span>
              <h3>速率与调度策略</h3>
              <p>以紧凑时间规则控制全局带宽和上下行窗口。</p>
            </div>
            <span class="panel-intro__badge">
              <LucideIcon name="activity" :size="14" :stroke-width="1.8" />
              实时应用
            </span>
          </div>
          <!-- 新增模式：显示提示信息 -->
          <div v-if="!downloader" class="empty-state">
            <LucideIcon name="lock-keyhole" :size="36" :stroke-width="1.4" class="empty-icon" />
            <h3>请先保存基本信息</h3>
            <p>速度设置需要下载器创建后才能配置</p>
          </div>
          <!-- 编辑模式：显示设置组件 -->
          <speed-settings-tab
            v-else
            :downloader="downloader"
            :settings="currentSettings"
            :capabilities="capabilities"
            ref="speedSettingsTabRef"
          />
        </div>
      </el-tab-pane>

      <!-- 标签页4: 高级设置 -->
      <!-- 【已废弃】高级设置页签已隐藏，不再显示给用户 -->
      <!-- 原因: qBittorrent客户端支持不完整，部分字段无法生效 -->
      <!-- 未来版本将完全移除此功能 -->
      <el-tab-pane v-if="false" label="高级设置" name="advanced">
        <div class="tab-content">
          <!-- 新增模式：显示提示信息 -->
          <div v-if="!downloader" class="empty-state">
            <LucideIcon name="lock-keyhole" :size="36" :stroke-width="1.4" class="empty-icon" />
            <h3>请先保存基本信息</h3>
            <p>高级设置需要下载器创建后才能配置</p>
          </div>
          <!-- 编辑模式：显示设置组件 -->
          <advanced-settings-tab
            v-else
            :downloader="downloader"
            :settings="currentSettings"
            ref="advancedSettingsTabRef"
          />
        </div>
      </el-tab-pane>

      <!-- 标签页5: 路径管理 (包含路径映射和下载器路径管理) -->
      <el-tab-pane name="pathManagement" :disabled="!isEdit">
        <span slot="label" class="workspace-tab-label">
          <span class="workspace-tab-label__icon">
            <LucideIcon name="route" :size="17" :stroke-width="1.8" />
          </span>
          <span class="workspace-tab-label__copy">
            <strong>路径管理</strong>
            <small>映射与可用目录</small>
          </span>
          <LucideIcon v-if="!isEdit" name="lock-keyhole" :size="12" :stroke-width="1.8" class="workspace-tab-label__lock" />
        </span>
        <div class="tab-content">
          <div class="panel-intro">
            <div>
              <span>03 / PATH TOPOLOGY</span>
              <h3>存储路径拓扑</h3>
              <p>校验下载器内部目录与 BtDeck 可访问路径之间的真实映射。</p>
            </div>
            <span class="panel-intro__badge">
              <LucideIcon name="folder-sync" :size="14" :stroke-width="1.8" />
              双向映射
            </span>
          </div>
          <!-- 新增模式：显示提示信息 -->
          <div v-if="!downloader" class="empty-state">
            <LucideIcon name="lock-keyhole" :size="36" :stroke-width="1.4" class="empty-icon" />
            <h3>请先保存基本信息</h3>
            <p>路径管理需要下载器创建后才能配置</p>
          </div>
          <!-- 编辑模式：显示路径管理组件 -->
          <path-management-tab
            v-else
            :downloader="downloader"
            :settings="currentSettings"
            ref="pathManagementTabRef"
          />
        </div>
      </el-tab-pane>

      <!-- 标签页6: 标签/分类管理 -->
      <el-tab-pane name="tagManagement" :disabled="!isEdit">
        <span slot="label" class="workspace-tab-label">
          <span class="workspace-tab-label__icon">
            <LucideIcon name="tags" :size="17" :stroke-width="1.8" />
          </span>
          <span class="workspace-tab-label__copy">
            <strong>{{ tabLabel }}</strong>
            <small>组织下载任务</small>
          </span>
          <LucideIcon v-if="!isEdit" name="lock-keyhole" :size="12" :stroke-width="1.8" class="workspace-tab-label__lock" />
        </span>
        <div class="tab-content">
          <div class="panel-intro">
            <div>
              <span>04 / TAXONOMY</span>
              <h3>{{ tabLabel }}</h3>
              <p>集中维护节点上的分类与标签，使任务结构保持清晰。</p>
            </div>
            <span class="panel-intro__badge">
              <LucideIcon name="tags" :size="14" :stroke-width="1.8" />
              结构同步
            </span>
          </div>
          <!-- 标签管理组件 -->
          <tag-management-tab
            :downloader="downloader"
            ref="tagManagementTabRef"
          />
        </div>
      </el-tab-pane>
    </el-tabs>

    <div slot="footer" class="dialog-footer">
      <div class="footer-left">
        <el-button class="workspace-footer-button" @click="handleSelectTemplate">
          <LucideIcon name="layout-template" :size="15" :stroke-width="1.8" />
          <span>从模板选择</span>
        </el-button>
        <span class="footer-hint">模板可快速载入速度、路径与高级策略</span>
      </div>
      <div class="footer-right">
        <el-button class="workspace-footer-button" :disabled="submitting" @click="handleClose">
          <LucideIcon name="x" :size="15" :stroke-width="1.9" />
          <span>取消</span>
        </el-button>
        <el-button
          class="workspace-footer-button workspace-footer-button--primary"
          type="primary"
          :disabled="submitting"
          @click="handleSubmit"
        >
          <LucideIcon
            :name="submitting ? 'refresh-cw' : (isEdit ? 'save' : 'plus')"
            :size="15"
            :stroke-width="1.9"
            :class="{'is-spinning': submitting}"
          />
          <span>{{ submitting ? '正在保存' : (isEdit ? '保存并应用' : '确认接入') }}</span>
        </el-button>
      </div>
    </div>

    <!-- 模板选择对话框 -->
    <template-selection-dialog
      :visible.sync="templateDialogVisible"
      :downloader-type="formData.downloader_type"
      :downloader-id="downloader?.id || ''"
      @template-selected="handleTemplateSelected"
    />
  </el-dialog>
</template>

<script lang="ts">
import { Component, Vue, Prop, Watch } from 'vue-property-decorator'
import { ElForm } from 'element-ui/types/form'
import {
  Downloader,
  DownloaderFormData,
  DownloaderSettings,
  DownloaderCapabilities,
  SettingTemplate
} from '../types'
import {
  addDownloader,
  upDownloader,
  getDownloaderCapabilities,
  getDownloaderSettings,
  updateDownloaderSettings,
  applyDownloaderSettings,
  testDownloaderSettings,
  getDetail
} from '@/api/downloader'
import SpeedSettingsTab from './SpeedSettingsTab.vue'
import AdvancedSettingsTab from './AdvancedSettingsTab.vue'
import PathManagementTab from './PathManagementTab.vue'
import TagManagementTab from './TagManagementTab.vue'
import TemplateSelectionDialog from './TemplateSelectionDialog.vue'
import { resolveEnableSchedule } from '../settings'

type SettingsApiData = DownloaderSettings & {
  dl_speed_limit?: number
  ul_speed_limit?: number
  dl_speed_unit?: number | string
  ul_speed_unit?: number | string
  advanced_settings?: Record<string, unknown>
}

interface CapabilityApiData {
  downloaderId?: string
  downloader_id?: string
  downloaderType?: number
  downloader_type?: number
  capabilities?: {
    supports_speed_scheduling?: boolean
    connectionLimits?: boolean
    queueSettings?: boolean
    downloadPaths?: boolean
    advancedSettings?: boolean
  }
}

interface ApiErrorLike {
  response?: { data?: { msg?: string } }
  message?: string
}

type DownloaderSubmitData = Omit<DownloaderFormData, 'password'> & {
  password?: string
  old_password?: string
  override_local?: boolean
  path_mapping?: unknown
}

const normalizeSpeedUnit = (value: unknown): 0 | 1 => Number(value) === 1 ? 1 : 0

@Component({
  name: 'DownloaderSettingsDialog',
  components: {
    SpeedSettingsTab,
    AdvancedSettingsTab,
    PathManagementTab,
    TagManagementTab,
    TemplateSelectionDialog
  }
})
export default class DownloaderSettingsDialog extends Vue {
  @Prop({ default: false }) visible!: boolean
  @Prop({ default: null }) downloader!: Downloader | null

  // 当前激活的标签页
  private activeTab = 'basic'

  // 提交状态
  private submitting = false

  // 模板对话框显示状态
  private templateDialogVisible = false

  // 连接测试状态
  private testing = false
  private testResult: { success: boolean, message: string } | null = null

  // 表单数据
  private formData: DownloaderFormData & { override_local: boolean, old_password?: string } = {
    nickname: '',
    host: '',
    port: 8080,
    username: '',
    password: '',
    is_ssl: '0',
    is_search: '1',
    downloader_type: 0,
    enabled: '1',
    override_local: false,
    path_mapping_rules: '',
    torrent_save_path: '',
    old_password: ''
  }

  // 保存原始用户名，用于判断是否需要原密码
  private originalUsername = ''

  // 当前设置
  private currentSettings: DownloaderSettings = {
    downloader_id: '',
    override_local: false,
    // 新字段
    dlSpeedLimit: 0,
    ulSpeedLimit: 0,
    dlSpeedUnit: 0,
    ulSpeedUnit: 0,
    // 兼容旧字段
    download_speed_limit: 0,
    upload_speed_limit: 0,
    speed_unit: 0
  }

  // 下载器能力信息（后端返回的嵌套结构）
  private capabilities: DownloaderCapabilities = {
    downloader_id: '',
    downloader_type: 0,
    supports_speed_scheduling: false,  // 从 capabilities.supports_speed_scheduling 读取
    supports_connection_limits: true,
    supports_queue_management: true,
    supports_path_mapping: false,
    supports_advanced_options: true
  }

  // 基本信息表单验证规则
  get basicFormRules() {
    return {
      nickname: [
        { required: true, message: '请输入下载器名称', trigger: 'blur' }
      ],
      host: [
        { required: true, message: '请输入主机地址', trigger: 'blur' }
      ],
      username: [
        { required: true, message: '请输入用户名', trigger: 'blur' }
      ],
      password: [
        { required: !this.isEdit, message: '请输入密码', trigger: 'blur' }  // 新增模式必填，编辑模式可选
      ],
      old_password: [
        { required: false, message: '请输入原密码', trigger: 'blur' }  // 动态验证
      ],
      port: [
        { required: true, message: '请输入端口号', trigger: 'blur' },
        { type: 'number', min: 1, max: 65535, message: '端口范围为1-65535', trigger: 'blur' }
      ],
      downloader_type: [
        { required: true, message: '请选择下载器类型', trigger: 'change' }
      ]
    }
  }

  // 获取表单引用
  get basicFormRef(): ElForm {
    return this.$refs.basicFormRef as ElForm
  }

  // 计算属性：是否为编辑模式
  get isEdit(): boolean {
    return this.downloader !== null
  }

  // 计算属性：对话框标题
  get dialogTitle(): string {
    if (this.isEdit) {
      return `下载器设置 • ${this.downloader?.nickname || ''}`
    }
    return '新增下载器'
  }

  get downloaderTypeLabel(): string {
    return this.formData.downloader_type === 1 ? 'Transmission' : 'qBittorrent'
  }

  // 计算属性：标签页签标题（Transmission显示"分类管理"，qBittorrent显示"标签/分类管理"）
  get tabLabel(): string {
    // 当下载器是Transmission时，显示"分类管理"（因为Transmission只有标签）
    if (this.downloader && this.downloader.downloader_type === 1) {
      return '分类管理'
    }
    return '标签/分类管理'
  }

  // 计算属性：是否需要显示原密码字段
  get showOldPassword(): boolean {
    if (!this.isEdit) return false  // 新增模式不显示原密码
    // 用户名发生变化，或密码字段有输入时，显示原密码字段
    const usernameChanged = this.formData.username !== this.originalUsername
    const passwordHasInput = this.formData.password && this.formData.password.trim() !== ''
    return usernameChanged || passwordHasInput
  }

  // 监听对话框显示状态
  @Watch('visible')
  onVisibleChange(val: boolean) {
    if (val) {
      this.initDialog()
    }
  }

  // 初始化对话框
  private async initDialog() {
    if (this.isEdit && this.downloader) {
      // 编辑模式：加载数据

      // 检查是否有完整的下载器信息（包含 username）
      // 列表接口返回的数据不包含 username，需要调用详情接口
      if (!this.downloader.username) {
        try {
          const response = await getDetail(this.downloader.id || this.downloader.downloaderId)
          if (response.code === '200' && response.data && response.data.length > 0) {
            // 使用详情接口返回的完整数据
            const detailData = response.data[0]
            // 保存原始用户名，用于判断是否需要原密码
            const originalUsername = detailData.username || ''

            this.formData = {
              id: detailData.id,
              nickname: detailData.nickname,
              host: detailData.host,
              port: detailData.port,
              username: detailData.username,
              password: '',  // 后端不返回密码，初始化为空
              is_ssl: detailData.isSsl,
              is_search: detailData.isSearch,
              downloader_type: detailData.downloaderType,
              enabled: detailData.enabled,
              override_local: false,
              path_mapping_rules: detailData.pathMappingRules || '',
              torrent_save_path: detailData.torrentSavePath || ''
            }

            // 保存原始用户名
            this.originalUsername = originalUsername
          } else {
            throw new Error('获取下载器详情失败')
          }
        } catch (error) {
          console.error('获取下载器详情失败:', error)
          this.$message.error('获取下载器详情失败')
          return
        }
      } else {
        // 如果已经有完整数据（例如从其他地方传入），直接使用
        const originalUsername = this.downloader.username || ''

        this.formData = {
          id: this.downloader.id,
          nickname: this.downloader.nickname,
          host: this.downloader.host,
          port: this.downloader.port,
          username: this.downloader.username,
          password: '',  // 后端不返回密码，初始化为空
          is_ssl: this.downloader.is_ssl,
          is_search: this.downloader.is_search,
          downloader_type: this.downloader.downloader_type,
          enabled: this.downloader.enabled,
          override_local: false,
          path_mapping_rules: this.downloader.path_mapping_rules || '',
          torrent_save_path: this.downloader.torrentSavePath || ''
        }

        // 保存原始用户名
        this.originalUsername = originalUsername
      }

      // 加载设置和能力信息
      await this.loadDownloaderSettings()
    } else {
      // 新增模式：重置表单
      this.resetForm()
    }
  }

  // 加载下载器设置和能力信息
  private async loadDownloaderSettings() {
    if (!this.downloader) return

    try {
      // 查询下载器设置（速度限制、高级配置等）
      const settingsResponse = await getDownloaderSettings(this.downloader.id)

      if (settingsResponse.code === '200' && settingsResponse.data) {
        const responseData = settingsResponse.data as SettingsApiData

        // 处理字段名映射（支持新旧格式）：
        // 后端返回：dl_speed_limit, ul_speed_limit, dl_speed_unit, ul_speed_unit（新格式）
        // 前端期望：同时支持新字段和旧字段名（向后兼容）

        // 确保速度单位是数字枚举，否则 el-select 无法匹配
        const dlSpeedUnitValue = responseData.dl_speed_unit ?? responseData.dlSpeedUnit ?? responseData.speed_unit ?? 0
        const dlSpeedUnitNumber = normalizeSpeedUnit(dlSpeedUnitValue)

        const ulSpeedUnitValue = responseData.ul_speed_unit ?? responseData.ulSpeedUnit ?? responseData.speed_unit ?? 0
        const ulSpeedUnitNumber = normalizeSpeedUnit(ulSpeedUnitValue)
        const enableSchedule = resolveEnableSchedule(responseData)

        this.currentSettings = {
          downloader_id: responseData.downloader_id || this.downloader.id,
          override_local: responseData.override_local || false,
          // 新字段（优先使用）
          dlSpeedLimit: responseData.dl_speed_limit ?? responseData.dlSpeedLimit ?? 0,
          ulSpeedLimit: responseData.ul_speed_limit ?? responseData.ulSpeedLimit ?? 0,
          dlSpeedUnit: dlSpeedUnitNumber,
          ulSpeedUnit: ulSpeedUnitNumber,
          enableSchedule,
          enable_schedule: enableSchedule,
          // 兼容旧字段名
          download_speed_limit: responseData.dl_speed_limit ?? responseData.dlSpeedLimit ?? 0,
          upload_speed_limit: responseData.ul_speed_limit ?? responseData.ulSpeedLimit ?? 0,
          speed_unit: dlSpeedUnitNumber,  // 旧字段使用下载单位（向后兼容）
          // 其他字段
          username: responseData.username || undefined,
          password: undefined, // 后端不返回密码
          advanced_settings: responseData.advanced_settings || undefined,
          // 路径映射（稍后加载）
          path_mapping: undefined,
          // 分时段限速规则
          schedule_rules: responseData.schedule_rules || []
        }

        // 使用 $set 确保 Vue 响应式更新
        this.$set(this, 'currentSettings', this.currentSettings)
      } else {
        // 使用默认值，包含空的 schedule_rules
        this.currentSettings = {
          downloader_id: this.downloader.id,
          override_local: false,
          dlSpeedLimit: 0,
          ulSpeedLimit: 0,
          dlSpeedUnit: 0,
          ulSpeedUnit: 0,
          download_speed_limit: 0,
          upload_speed_limit: 0,
          speed_unit: 0,
          username: undefined,
          password: undefined,
          advanced_settings: undefined,
          path_mapping: undefined,
          schedule_rules: []
        }
        this.$set(this, 'currentSettings', this.currentSettings)
      }

      // 加载能力信息
      const capResponse = await getDownloaderCapabilities(this.downloader.id)
      if (capResponse.code === '200' && capResponse.data) {
        // 后端返回的是嵌套结构，需要从 capabilities 对象中提取字段
        const responseData = capResponse.data as unknown as CapabilityApiData
        const capabilitiesData = responseData.capabilities || {}

        // 构建扁平化的 capabilities 对象（兼容前端类型定义）
        this.capabilities = {
          downloader_id: responseData.downloaderId || responseData.downloader_id || '',
          downloader_type: normalizeSpeedUnit(responseData.downloaderType ?? responseData.downloader_type),
          supports_speed_scheduling: capabilitiesData.supports_speed_scheduling || false,
          supports_connection_limits: capabilitiesData.connectionLimits !== undefined ? capabilitiesData.connectionLimits : true,
          supports_queue_management: capabilitiesData.queueSettings !== undefined ? capabilitiesData.queueSettings : true,
          supports_path_mapping: capabilitiesData.downloadPaths || false,
          supports_advanced_options: capabilitiesData.advancedSettings !== undefined ? capabilitiesData.advancedSettings : true
        }
      }

      // 加载设置信息，包括 override_local
      if (this.currentSettings.override_local !== undefined) {
        this.formData.override_local = this.currentSettings.override_local
      }

      // 加载路径映射配置
      const { getPathMappings } = await import('@/api/downloader')

      const pathMappingResponse = await getPathMappings(this.downloader.id)

      if (pathMappingResponse.code === '200' && pathMappingResponse.data) {
        // 使用 $set 确保 Vue 响应式更新
        this.$set(this.currentSettings, 'path_mapping', pathMappingResponse.data)
      }
    } catch (error) {
      console.error('加载下载器设置失败:', error)
      // 异常时也使用默认值，包含空的 schedule_rules
      if (this.downloader) {
        this.currentSettings = {
          downloader_id: this.downloader.id,
          override_local: false,
          dlSpeedLimit: 0,
          ulSpeedLimit: 0,
          dlSpeedUnit: 0,
          ulSpeedUnit: 0,
          download_speed_limit: 0,
          upload_speed_limit: 0,
          speed_unit: 0,
          username: undefined,
          password: undefined,
          advanced_settings: undefined,
          path_mapping: undefined,
          schedule_rules: []
        }
        this.$set(this, 'currentSettings', this.currentSettings)
      }
    }
  }

  // 连接测试
  private async handleTestConnection() {
    // 验证必填字段（新增模式必须填写完整连接信息）
    if (!this.formData.host || !this.formData.port ||
        !this.formData.username || !this.formData.password) {
      this.$message.warning('请先填写完整的连接信息（主机、端口、用户名、密码）')
      return
    }

    this.testing = true
    this.testResult = null

    try {
      // 构建测试参数（使用当前表单数据）
      const testParams = {
        host: this.formData.host,
        port: this.formData.port,
        username: this.formData.username,
        password: this.formData.password,  // 新增模式必填，编辑模式可能为空
        downloader_type: this.formData.downloader_type,
        is_ssl: this.formData.is_ssl
      }

      // 新增模式：使用临时ID；编辑模式：使用真实ID
      // 后端接口根据请求体参数测试连接，downloader_id 仅用于查询数据库密码
      const downloaderId = this.downloader?.id || 'temp-test-id'

      const response = await testDownloaderSettings(downloaderId, testParams)

      if (response.code === '200') {
        this.testResult = {
          success: response.data.success,
          message: response.data.success
            ? `连接成功 • 延迟 ${response.data.delay || 0}ms`
            : response.data.message || '连接失败'
        }
      } else {
        this.testResult = {
          success: false,
          message: response.msg || '连接失败'
        }
      }
    } catch (error: unknown) {
      const apiError = error as ApiErrorLike
      this.testResult = {
        success: false,
        message: apiError.response?.data?.msg || apiError.message || '连接失败'
      }
    } finally {
      this.testing = false
    }
  }

  // 对话框打开后的回调
  private handleDialogOpened() {
    this.$nextTick(() => {
      if (this.basicFormRef) {
        this.basicFormRef.clearValidate()
      }
    })
  }

  // 重置表单
  private resetForm() {
    this.formData = {
      nickname: '',
      host: '',
      port: 8080,
      username: '',
      password: '',
      is_ssl: '0',
      is_search: '1',
      downloader_type: 0,
      enabled: '1',
      path_mapping_rules: '',
      torrent_save_path: '',
      old_password: ''
    }
    this.originalUsername = ''
    this.currentSettings = {
      downloader_id: '',
      override_local: false,
      // 新字段
      dlSpeedLimit: 0,
      ulSpeedLimit: 0,
      dlSpeedUnit: 0,
      ulSpeedUnit: 0,
      // 兼容旧字段
      download_speed_limit: 0,
      upload_speed_limit: 0,
      speed_unit: 0
    }
    this.activeTab = 'basic'
  }

  // 关闭对话框
  private handleClose() {
    this.$emit('update:visible', false)
    this.resetForm()
  }

  // 从模板选择
  private handleSelectTemplate() {
    this.templateDialogVisible = true
  }

  // 模板选择回调
  private handleTemplateSelected(template: SettingTemplate) {
    // 应用模板到当前设置
    Object.assign(this.currentSettings, template.settings)

    // 切换到基础设置标签页查看应用结果
    this.activeTab = 'basic'
  }

  // 提交表单
  private async handleSubmit() {
    try {
      // 验证基本信息表单
      await this.basicFormRef.validate()

      // 收集所有标签页的数据（不包括基本信息页签，因为已经在 formData 中）
      const speedData = (this.$refs.speedSettingsTabRef as SpeedSettingsTab | undefined)?.getFormData() || {}
      const advancedData = (this.$refs.advancedSettingsTabRef as AdvancedSettingsTab | undefined)?.getFormData() || {}
      const pathMappingData = (this.$refs.pathManagementTabRef as PathManagementTab | undefined)?.getPathMappingData() || null

      // 从 formData 中提取需要提交到设置的数据
      const settingsData = {
        override_local: this.formData.override_local
      }

      // 构建基本信息提交数据（只包含基本信息字段）
      const basicData: DownloaderSubmitData = {
        ...this.formData
      }

      // 添加路径映射数据（包括空数组，用于清空配置）
      // 只要 pathMappingData 不是 null/undefined，就提交（让后端判断是更新还是清空）
      if (pathMappingData !== null && pathMappingData !== undefined) {
        basicData['path_mapping'] = pathMappingData
      }

      // 处理密码和原密码字段
      if (this.isEdit) {
        if (!this.downloader) {
          throw new Error('Missing downloader for edit mode')
        }
        // 编辑模式：只有在密码字段有输入时才包含密码
        if (!basicData.password || basicData.password.trim() === '') {
          delete basicData.password
        }
        // 只有在显示原密码字段时才包含原密码
        if (!this.showOldPassword) {
          delete basicData.old_password
        }
      } else {
        // 新增模式：删除原密码字段
        delete basicData.old_password
      }

      // 删除不需要的字段
      delete basicData.override_local  // override_local 应该在 settingsData 中
      delete basicData.id  // id 不需要提交

      this.submitting = true

      if (this.isEdit) {
        // 编辑模式：更新下载器基本信息（只包含基本信息字段）
        if (!this.downloader) {
          throw new Error('Missing downloader for edit mode')
        }
        const downloaderId = this.downloader.id
        await upDownloader({ ...basicData, id: downloaderId })

        // 如果有设置变更，同时更新设置并应用到下载器
        if (Object.keys(settingsData).length > 0 || Object.keys(speedData).length > 0 || Object.keys(advancedData).length > 0) {
          // 1. 保存设置到数据库
          const updateResponse = await updateDownloaderSettings(downloaderId, {
            ...settingsData,
            ...speedData,
            ...advancedData
          })

          if (updateResponse.code === '200' && updateResponse.data?.schedule_rules !== undefined) {
            this.$set(this.currentSettings, 'schedule_rules', updateResponse.data.schedule_rules)
          }

          // 2. 应用设置到下载器客户端
          const loadingMessage = this.$message({
            message: '正在应用配置到下载器...',
            type: 'info',
            duration: 0
          })

          try {
            await applyDownloaderSettings(downloaderId)
            loadingMessage.close()
            this.$message.success('保存成功，配置已应用到下载器')
          } catch (applyError: unknown) {
            loadingMessage.close()
            const apiError = applyError as ApiErrorLike
            const applyErrorMsg = apiError.response?.data?.msg || apiError.message || '配置应用失败'
            this.$message.warning(`保存成功，但配置应用失败: ${applyErrorMsg}`)
            // 不抛出错误，因为数据库已经保存成功
          }
        } else {
          this.$message.success('保存成功')
        }
      } else {
        // 新增模式：创建下载器
        await addDownloader({ ...basicData, id: '' })
        this.$message.success('新增成功')
      }

      this.$emit('submit')
      this.handleClose()
    } catch (error: unknown) {
      console.error('提交失败:', error)
      const apiError = error as ApiErrorLike
      const errorMsg = apiError.response?.data?.msg || apiError.message || '操作失败'
      this.$message.error(errorMsg)
    } finally {
      this.submitting = false
    }
  }
}
</script>

<style lang="scss" scoped>
@import '@/styles/theme-variables.scss';

::v-deep .downloader-settings-dialog {
  // 水平居中，垂直向上偏移50px
  position: fixed;
  left: 50%;
  top: calc(10% - 170px);
  transform: translate(-50%, 0);
  margin: 0;
  .el-dialog__header {
    padding: var(--spacing-lg) var(--spacing-xl);
    border-bottom: 1px solid var(--color-border-primary);
  }

  .el-dialog__title {
    font-size: 20px;
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-primary);
  }

  .el-dialog__body {
    padding: 0;
  }

  .el-dialog__footer {
    padding: var(--spacing-lg) var(--spacing-xl);
    border-top: 1px solid var(--color-border-primary);
  }
}

.settings-tabs {
  border: none;
  box-shadow: none;

  ::v-deep .el-tabs__header {
    background: var(--color-bg-secondary);
    margin: 0;
    padding: var(--spacing-sm) var(--spacing-xl);
    border-bottom: 1px solid var(--color-border-primary);
  }

  ::v-deep .el-tabs__content {
    padding: 0;
  }

  ::v-deep .el-tabs__item {
    border: none;
    padding: 8px 20px;
    font-size: 14px;
    font-weight: var(--font-weight-medium);
    color: var(--color-text-secondary);
    transition: all var(--transition-base);
    // 标签文字水平垂直居中
    display: inline-flex;
    align-items: center;
    justify-content: center;

    &:hover {
      color: var(--color-primary);
    }

    &.is-active {
      color: var(--color-primary);
      background: var(--color-primary-lightest);
      border-radius: var(--radius-md);
    }
  }
}

.tab-content {
  padding: var(--spacing-xl);
  max-height: 500px;
  overflow-y: auto;
}

.switch-row {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-lg);
  border-top: 1px solid var(--color-border-primary);
}

.switch-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
}

.switch-title {
  font-size: 13px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  text-align: center;
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-left,
.footer-right {
  display: flex;
  gap: var(--spacing-sm);
}

.button-icon {
  display: inline;
  vertical-align: middle;
  margin-right: 6px;
  width: 16px;
  height: 16px;
}

// 滚动条样式
.tab-content::-webkit-scrollbar {
  width: 8px;
}

.tab-content::-webkit-scrollbar-track {
  background: var(--color-bg-secondary);
}

.tab-content::-webkit-scrollbar-thumb {
  background: var(--color-border-primary);
  border-radius: 4px;
}

.tab-content::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-tertiary);
}

// ==================== 卡片分组式布局样式 ====================

// 表单分组
.form-section {
  margin-bottom: var(--spacing-xl);
}

// 分组标题
.form-section-title {
  font-size: 16px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-md);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);

  .section-icon {
    width: 20px;
    height: 20px;
    color: var(--color-primary);
  }
}

// 分组卡片
.form-section-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  transition: all var(--transition-base);

  &:hover {
    border-color: var(--color-border-focus);
    box-shadow: var(--shadow-sm);
  }
}

// 输入框图标
.input-icon {
  width: 16px;
  height: 16px;
  color: var(--color-text-tertiary);
}

// 帮助提示图标
.help-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}

// 表单项帮助文本
.form-item-help {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: var(--spacing-xs);
  padding: 0;
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.5;
}

// 原密码提示
.old-password-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-info-light);
  border-radius: var(--radius-md);
  font-size: 12px;
  color: var(--color-info);
  line-height: 1.5;
  height: 40px;
}

::v-deep .el-input__prefix {
  left: 8px;
}

::v-deep .el-input--prefix .el-input__inner {
  padding-left: 36px;
}

// 开关控件
.switch-control {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  height: 40px;
}

.switch-label-text {
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

// 覆盖配置项
.override-setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  gap: var(--spacing-md);
}

.override-setting-content {
  flex: 1;
}

.override-setting-title {
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.override-setting-desc {
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.5;
}

// 功能开关项
.feature-switch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  gap: var(--spacing-md);
  height: 100%;
}

.feature-switch-content {
  flex: 1;
}

.feature-switch-title {
  font-size: 14px;
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.feature-switch-desc {
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.5;
}

// 测试结果
.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: var(--font-weight-medium);
  height: 40px;
  transition: all var(--transition-base);

  &.success {
    background: var(--color-success-light);
    color: var(--color-success);
  }

  &.error {
    background: var(--color-error-light);
    color: var(--color-error);
  }
}

.test-result-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--color-border-primary);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--color-text-tertiary);
  height: 40px;
}

.result-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.button-icon {
  display: inline;
  vertical-align: middle;
  margin-right: 6px;
  width: 16px;
  height: 16px;
}

// ==================== 空状态样式 ====================
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xxl) var(--spacing-xl);
  min-height: 300px;
  text-align: center;

  .empty-icon {
    width: 64px;
    height: 64px;
    color: var(--color-text-tertiary);
    margin-bottom: var(--spacing-lg);
    opacity: 0.5;
  }

  h3 {
    font-size: 18px;
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-primary);
    margin: 0 0 var(--spacing-sm) 0;
  }

  p {
    font-size: 14px;
    color: var(--color-text-secondary);
    margin: 0;
    line-height: 1.5;
  }
}

// ==================== Node workspace redesign ====================
::v-deep .downloader-settings-dialog {
  position: relative !important;
  top: auto !important;
  left: auto !important;
  display: flex;
  flex-direction: column;
  width: min(1320px, calc(100vw - 36px)) !important;
  height: min(860px, calc(100vh - 32px));
  margin: 16px auto 0 !important;
  overflow: hidden;
  transform: none !important;
  border: 1px solid rgba(var(--color-primary-rgb), 0.17);
  border-radius: 24px;
  background:
    linear-gradient(145deg, rgba(255, 255, 255, 0.98), rgba(var(--color-primary-rgb), 0.025)),
    var(--color-bg-primary);
  box-shadow: 0 40px 120px rgba(15, 23, 42, 0.2);

  &::after {
    content: '';
    position: absolute;
    top: -190px;
    right: -90px;
    width: 430px;
    height: 430px;
    pointer-events: none;
    border: 1px solid rgba(var(--color-primary-rgb), 0.1);
    border-radius: 50%;
    box-shadow: 0 0 0 48px rgba(var(--color-primary-rgb), 0.025), 0 0 0 96px rgba(var(--color-primary-rgb), 0.014);
  }

  .el-dialog__header {
    z-index: 2;
    flex: 0 0 auto;
    padding: 0;
    border-bottom: 1px solid rgba(var(--color-primary-rgb), 0.12);
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(18px);
  }

  .el-dialog__body {
    position: relative;
    z-index: 1;
    flex: 1;
    min-height: 0;
    padding: 0;
    overflow: hidden;
  }

  .el-dialog__footer {
    z-index: 2;
    flex: 0 0 auto;
    padding: 10px 14px;
    border-top: 1px solid rgba(var(--color-primary-rgb), 0.12);
    background: rgba(255, 255, 255, 0.86);
    backdrop-filter: blur(18px);
  }
}

.workspace-header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 78px;
  padding: 12px 16px 12px 18px;

  &__identity,
  &__context {
    display: flex;
    align-items: center;
  }

  &__identity {
    gap: 13px;
    min-width: 0;

    h2 {
      overflow: hidden;
      margin: 3px 0 0;
      color: var(--color-text-primary);
      font-size: 20px;
      font-weight: 680;
      letter-spacing: -0.035em;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }

  &__mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 46px;
    height: 46px;
    flex: 0 0 46px;
    border: 1px solid rgba(var(--color-primary-rgb), 0.24);
    border-radius: 14px;
    background: linear-gradient(145deg, var(--color-bg-primary), rgba(var(--color-primary-rgb), 0.08));
    color: var(--color-primary);
    box-shadow: 0 12px 28px rgba(var(--color-primary-rgb), 0.12);
  }

  &__context {
    justify-content: flex-end;
    gap: 7px;

    > span {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 6px 9px;
      border: 1px solid var(--color-border-primary);
      border-radius: 8px;
      background: rgba(249, 250, 251, 0.76);
      color: var(--color-text-secondary);
      font-family: var(--font-mono);
      font-size: 9px;
    }

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      margin-left: 4px;
      padding: 0;
      border: 1px solid var(--color-border-primary);
      border-radius: 10px;
      background: var(--color-bg-primary);
      color: var(--color-text-secondary);
      cursor: pointer;
      transition: color var(--transition-fast), border-color var(--transition-fast), transform var(--transition-fast);

      &:hover,
      &:focus-visible {
        border-color: rgba(var(--color-error-rgb), 0.32);
        color: var(--color-error);
        transform: rotate(4deg);
        outline: none;
      }
    }
  }
}

.workspace-eyebrow {
  color: var(--color-primary);
  font-family: var(--font-mono);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.16em;
}

.settings-tabs {
  height: 100%;
  border: 0;
  background: transparent;
  box-shadow: none;

  ::v-deep > .el-tabs__header.is-left {
    width: 218px;
    height: 100%;
    margin: 0;
    padding: 17px 12px;
    border-right: 1px solid rgba(var(--color-primary-rgb), 0.11);
    background:
      linear-gradient(rgba(var(--color-primary-rgb), 0.045) 1px, transparent 1px),
      linear-gradient(90deg, rgba(var(--color-primary-rgb), 0.045) 1px, transparent 1px),
      rgba(249, 250, 251, 0.72);
    background-size: 24px 24px;
  }

  ::v-deep > .el-tabs__header .el-tabs__nav-wrap {
    height: 100%;

    &::after {
      display: none;
    }
  }

  ::v-deep > .el-tabs__header .el-tabs__active-bar {
    display: none;
  }

  ::v-deep > .el-tabs__header .el-tabs__item.is-left {
    display: flex;
    align-items: center;
    width: 100%;
    height: 61px;
    margin-bottom: 5px;
    padding: 0 10px !important;
    border: 1px solid transparent;
    border-radius: 12px;
    color: var(--color-text-secondary);
    line-height: normal;
    text-align: left;
    transition: color var(--transition-base), border-color var(--transition-base), background var(--transition-base), transform var(--transition-base);

    &:hover:not(.is-disabled) {
      border-color: rgba(var(--color-primary-rgb), 0.14);
      background: rgba(255, 255, 255, 0.72);
      color: var(--color-text-primary);
      transform: translateX(2px);
    }

    &.is-active {
      border-color: rgba(var(--color-primary-rgb), 0.2);
      background: rgba(255, 255, 255, 0.92);
      color: var(--color-primary);
      box-shadow: 0 12px 28px rgba(15, 23, 42, 0.06);
    }

    &.is-disabled {
      opacity: 0.48;
      cursor: not-allowed;
    }
  }

  ::v-deep > .el-tabs__content {
    height: 100%;
    padding: 0;
    overflow: hidden;
  }

  ::v-deep > .el-tabs__content > .el-tab-pane {
    height: 100%;
  }
}

.workspace-tab-label {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  gap: 9px;

  &__icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    flex: 0 0 30px;
    border: 1px solid var(--color-border-primary);
    border-radius: 9px;
    background: var(--color-bg-primary);
    color: var(--color-text-tertiary);

    .is-active & {
      border-color: rgba(var(--color-primary-rgb), 0.18);
      background: var(--color-primary-lightest);
      color: var(--color-primary);
    }
  }

  &__copy {
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: 3px;

    strong,
    small {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    strong {
      font-size: 11px;
      font-weight: 680;
    }

    small {
      color: var(--color-text-tertiary);
      font-size: 8px;
      font-weight: 400;
    }
  }

  &__lock {
    margin-left: auto;
    color: var(--color-text-tertiary);
  }
}

.tab-content {
  height: 100%;
  max-height: none;
  padding: 18px 20px 26px;
  overflow: auto;
  scrollbar-gutter: stable;
}

.panel-intro {
  position: sticky;
  top: -18px;
  z-index: 8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin: -18px -20px 16px;
  padding: 16px 20px 13px;
  border-bottom: 1px solid rgba(var(--color-primary-rgb), 0.09);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(14px);

  > div {
    min-width: 0;
  }

  > div > span {
    color: var(--color-primary);
    font-family: var(--font-mono);
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.15em;
  }

  h3 {
    margin: 4px 0 2px;
    font-size: 17px;
    font-weight: 680;
    letter-spacing: -0.025em;
  }

  p {
    margin: 0;
    color: var(--color-text-tertiary);
    font-size: 10px;
  }

  &__badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex: 0 0 auto;
    padding: 6px 9px;
    border: 1px solid rgba(var(--color-primary-rgb), 0.15);
    border-radius: 999px;
    background: var(--color-primary-lightest);
    color: var(--color-primary);
    font-size: 9px;
    font-weight: 650;
  }
}

.workspace-basic-form {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 12px;

  > .form-section {
    min-width: 0;
    margin: 0;

    &:nth-child(1) { grid-column: span 7; }
    &:nth-child(2) { grid-column: span 5; }
    &:nth-child(3) { grid-column: span 5; }
    &:nth-child(4) { grid-column: span 7; }
    &:nth-child(5) { grid-column: span 5; }
    &:nth-child(6) { grid-column: span 7; }
    &:nth-child(7) { grid-column: 1 / -1; }
  }

  .form-section-title {
    gap: 7px;
    margin-bottom: 7px;
    color: var(--color-text-secondary);
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.11em;
    text-transform: uppercase;

    .section-icon {
      color: var(--color-primary);
    }
  }

  .form-section-card {
    height: calc(100% - 25px);
    padding: 12px;
    border-color: rgba(var(--color-primary-rgb), 0.1);
    border-radius: 13px;
    background: rgba(249, 250, 251, 0.7);
    box-shadow: none;

    &:hover {
      border-color: rgba(var(--color-primary-rgb), 0.24);
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.045);
    }
  }

  ::v-deep .el-row:last-child .el-form-item {
    margin-bottom: 0;
  }

  ::v-deep .el-form-item {
    margin-bottom: 10px;
  }

  ::v-deep .el-form-item__label {
    height: 30px;
    padding-right: 10px;
    color: var(--color-text-secondary);
    font-size: 10px;
    line-height: 30px;
  }

  ::v-deep .el-input__inner,
  ::v-deep .el-input-number,
  ::v-deep .el-input-number .el-input__inner {
    height: 32px;
    font-size: 11px;
    line-height: 32px;
  }

  ::v-deep .el-textarea__inner {
    min-height: 92px !important;
    padding: 9px 11px;
    font-family: var(--font-mono);
    font-size: 10px;
    line-height: 1.55;
  }
}

.switch-control,
.feature-switch-item,
.override-setting-item {
  min-height: 38px;
  height: auto;
  padding: 9px 10px;
  border: 1px solid var(--color-border-secondary);
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.76);
}

.override-setting-title,
.feature-switch-title,
.switch-label-text {
  font-size: 11px;
}

.override-setting-desc,
.feature-switch-desc,
.form-item-help,
.old-password-hint {
  font-size: 9px;
}

.test-result,
.test-result-placeholder {
  height: 36px;
  min-height: 36px;
  font-size: 10px;
}

.dialog-footer {
  min-height: 42px;
}

.footer-left,
.footer-right,
.workspace-footer-button ::v-deep span {
  display: flex;
  align-items: center;
}

.footer-left {
  min-width: 0;
  gap: 10px;
}

.footer-right {
  gap: 7px;
}

.footer-hint {
  overflow: hidden;
  color: var(--color-text-tertiary);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-footer-button {
  height: 34px;
  padding: 0 12px;
  border-radius: 9px;
  font-size: 10px;

  ::v-deep span {
    gap: 6px;
  }

  &--primary {
    min-width: 126px;
    border-color: var(--color-primary);
    background: var(--color-primary);
    box-shadow: 0 9px 22px rgba(var(--color-primary-rgb), 0.2);
  }
}

.is-spinning {
  animation: workspace-spin 0.85s linear infinite;
}

@keyframes workspace-spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 1120px) {
  .workspace-basic-form > .form-section {
    &:nth-child(n) {
      grid-column: span 6;
    }

    &:nth-child(7) {
      grid-column: 1 / -1;
    }
  }
}

@media (max-width: 780px) {
  ::v-deep .downloader-settings-dialog {
    width: 100% !important;
    height: 100vh;
    margin: 0 !important;
    border-radius: 0;
  }

  .workspace-header {
    min-height: 68px;
    padding: 10px 12px;

    &__mark {
      width: 40px;
      height: 40px;
      flex-basis: 40px;
    }

    &__identity h2 {
      font-size: 16px;
    }

    &__context > span {
      display: none;
    }
  }

  .settings-tabs {
    ::v-deep > .el-tabs__header.is-left {
      width: 64px;
      padding: 12px 7px;
    }

    ::v-deep > .el-tabs__header .el-tabs__item.is-left {
      justify-content: center;
      height: 52px;
      padding: 0 !important;
    }
  }

  .workspace-tab-label {
    justify-content: center;

    &__copy,
    &__lock {
      display: none;
    }
  }

  .tab-content {
    padding: 14px 12px 22px;
  }

  .panel-intro {
    top: -14px;
    margin: -14px -12px 12px;
    padding: 13px 12px 11px;

    p,
    &__badge {
      display: none;
    }
  }

  .workspace-basic-form > .form-section:nth-child(n) {
    grid-column: 1 / -1;
  }

  .footer-hint {
    display: none;
  }
}

@media (max-width: 520px) {
  .workspace-eyebrow {
    display: none;
  }

  .workspace-basic-form ::v-deep .el-col {
    width: 100%;
  }

  .workspace-footer-button {
    min-width: 34px;
    padding: 0 9px;

    span span {
      display: none;
    }

    &--primary {
      min-width: 110px;

      span span {
        display: inline;
      }
    }
  }
}

@media (prefers-reduced-motion: reduce) {
  .settings-tabs ::v-deep .el-tabs__item,
  .workspace-header__context button,
  .form-section-card {
    transition-duration: 0.01ms !important;
  }

  .is-spinning {
    animation: none !important;
  }
}
</style>
