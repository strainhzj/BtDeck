<template>
  <el-dialog
    :title="dialogTitle"
    :visible.sync="visible"
    :before-close="handleClose"
    :close-on-click-modal="false"
    width="70%"
    custom-class="downloader-settings-dialog"
    @opened="handleDialogOpened"
  >
    <el-tabs v-model="activeTab" type="border-card" class="settings-tabs">
      <!-- 标签页1: 基本信息（合并后） -->
      <el-tab-pane label="基本信息" name="basic">
        <div class="tab-content">
          <el-form
            ref="basicFormRef"
            :model="formData"
            :rules="basicFormRules"
            label-width="140px"
          >
            <!-- 🔌 连接配置 -->
            <div class="form-section">
              <div class="form-section-title">
                <svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path>
                  <line x1="12" y1="2" x2="12" y2="12"></line>
                </svg>
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
                          <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                            <circle cx="12" cy="7" r="4"></circle>
                          </svg>
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
                        controls-position="right"
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
                          <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
                            <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
                            <line x1="6" y1="6" x2="6.01" y2="6"></line>
                            <line x1="6" y1="18" x2="6.01" y2="18"></line>
                          </svg>
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

            <!-- 🔐 认证信息 -->
            <div class="form-section">
              <div class="form-section-title">
                <svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
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
                          <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                            <circle cx="12" cy="7" r="4"></circle>
                          </svg>
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
                          <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                            <path d="M7 11V7a5 5 0 0 1 9.9-1"></path>
                          </svg>
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
                          <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                          </svg>
                        </template>
                      </el-input>
                    </el-form-item>
                  </el-col>
                  <el-col :span="12">
                    <div class="old-password-hint">
                      <svg class="help-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="16" x2="12" y2="12"></line>
                        <line x1="12" y1="8" x2="12.01" y2="8"></line>
                      </svg>
                      <span>修改用户名或密码时需要验证原密码</span>
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>

            <!-- ⚙️ 配置选项 -->
            <div class="form-section">
              <div class="form-section-title">
                <svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="3"></circle>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                </svg>
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

            <!-- 🧪 连接测试 -->
            <div class="form-section">
              <div class="form-section-title">
                <svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
                </svg>
                连接测试
              </div>
              <div class="form-section-card">
                <el-row :gutter="16">
                  <el-col :span="12">
                    <el-button
                      type="primary"
                      :loading="testing"
                      @click="handleTestConnection"
                      style="width: 100%;"
                      size="medium"
                    >
                      <svg v-if="!testing" class="button-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>
                      </svg>
                      {{ testing ? '测试中...' : '测试连接' }}
                    </el-button>
                  </el-col>
                  <el-col :span="12">
                    <div v-if="testResult" :class="['test-result', testResult.success ? 'success' : 'error']">
                      <svg v-if="testResult.success" class="result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                      </svg>
                      <svg v-else class="result-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="15" y1="9" x2="9" y2="15"></line>
                        <line x1="9" y1="9" x2="15" y2="15"></line>
                      </svg>
                      <span>{{ testResult.message }}</span>
                    </div>
                    <div v-else class="test-result-placeholder">
                      点击按钮测试连接
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>

            <!-- 🎛️ 功能开关 -->
            <div class="form-section">
              <div class="form-section-title">
                <svg class="section-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path>
                  <line x1="12" y1="2" x2="12" y2="12"></line>
                </svg>
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

            <!-- 💾 存储配置 -->
            <div class="form-section">
              <div class="form-section-title">
                <svg class="section-icon" style="width: 20px; height: 20px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                </svg>
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
                      <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                      </svg>
                    </template>
                  </el-input>
                  <div class="form-item-help">
                    <svg class="help-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="12" y1="16" x2="12" y2="12"></line>
                      <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    <span>保存种子文件的目录路径，必须为应用运行环境可直接访问的绝对路径</span>
                  </div>
                </el-form-item>
              </div>
            </div>

            <!-- 🔄 路径映射规则 -->
            <div class="form-section">
              <div class="form-section-title">
                <svg class="section-icon" style="width: 20px; height: 20px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M3 3v18h18"></path>
                  <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
                </svg>
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
                    <svg class="help-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <circle cx="12" cy="12" r="10"></circle>
                      <line x1="12" y1="16" x2="12" y2="12"></line>
                      <line x1="12" y1="8" x2="12.01" y2="8"></line>
                    </svg>
                    <span>路径转换规则用于定时任务扫描路径时自动生成外部路径。规则为空时表示路径相等（不转换）。</span>
                  </div>
                </el-form-item>
              </div>
            </div>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 标签页2: 速度设置 -->
      <el-tab-pane label="速度设置" name="speed">
        <div class="tab-content">
          <!-- 新增模式：显示提示信息 -->
          <div v-if="!downloader" class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
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
      <!-- ⚠️ 【已废弃】高级设置页签已隐藏，不再显示给用户 -->
      <!-- 原因: qBittorrent客户端支持不完整，部分字段无法生效 -->
      <!-- 未来版本将完全移除此功能 -->
      <el-tab-pane v-if="false" label="高级设置" name="advanced">
        <div class="tab-content">
          <!-- 新增模式：显示提示信息 -->
          <div v-if="!downloader" class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
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
      <el-tab-pane label="路径管理" name="pathManagement">
        <div class="tab-content">
          <!-- 新增模式：显示提示信息 -->
          <div v-if="!downloader" class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
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
      <el-tab-pane :label="tabLabel" name="tagManagement">
        <div class="tab-content">
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
        <el-button @click="handleSelectTemplate">
          <svg class="button-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7"></rect>
            <rect x="14" y="3" width="7" height="7"></rect>
            <rect x="14" y="14" width="7" height="7"></rect>
            <rect x="3" y="14" width="7" height="7"></rect>
          </svg>
          从模板选择
        </el-button>
      </div>
      <div class="footer-right">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          {{ isEdit ? '保存修改' : '确认新增' }}
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
  DownloaderCapabilities
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
    console.log('🔍 [DownloaderSettingsDialog] loadDownloaderSettings() called')
    console.log('🔍 [DownloaderSettingsDialog] downloader:', this.downloader)

    if (!this.downloader) return

    try {
      console.log('🔍 [DownloaderSettingsDialog] 开始加载下载器设置...')
      // ✅ 添加：查询下载器设置（速度限制、高级配置等）
      const settingsResponse = await getDownloaderSettings(this.downloader.id)
      console.log('🔍 [DownloaderSettingsDialog] 下载器设置响应:', settingsResponse)

      if (settingsResponse.code === '200' && settingsResponse.data) {
        const responseData = settingsResponse.data as any

        // 🔍 调试：输出后端返回的原始数据
        console.log('🔍 [DEBUG] 后端返回的原始数据:', JSON.stringify(responseData, null, 2))
        console.log('🔍 [DEBUG] dl_speed_unit 原始值:', responseData.dl_speed_unit, '类型:', typeof responseData.dl_speed_unit)
        console.log('🔍 [DEBUG] ul_speed_unit 原始值:', responseData.ul_speed_unit, '类型:', typeof responseData.ul_speed_unit)

        // 处理字段名映射（支持新旧格式）：
        // 后端返回：dl_speed_limit, ul_speed_limit, dl_speed_unit, ul_speed_unit（新格式）
        // 前端期望：同时支持新字段和旧字段名（向后兼容）

        // ⚠️ 重要：确保速度单位是数字类型，否则 el-select 无法匹配
        const dlSpeedUnitValue = responseData.dl_speed_unit ?? responseData.dlSpeedUnit ?? responseData.speed_unit ?? 0
        const dlSpeedUnitNumber = typeof dlSpeedUnitValue === 'number' ? dlSpeedUnitValue : parseInt(dlSpeedUnitValue, 10)

        const ulSpeedUnitValue = responseData.ul_speed_unit ?? responseData.ulSpeedUnit ?? responseData.speed_unit ?? 0
        const ulSpeedUnitNumber = typeof ulSpeedUnitValue === 'number' ? ulSpeedUnitValue : parseInt(ulSpeedUnitValue, 10)

        this.currentSettings = {
          downloader_id: responseData.downloader_id || this.downloader.id,
          override_local: responseData.override_local || false,
          // 新字段（优先使用）
          dlSpeedLimit: responseData.dl_speed_limit ?? responseData.dlSpeedLimit ?? 0,
          ulSpeedLimit: responseData.ul_speed_limit ?? responseData.ulSpeedLimit ?? 0,
          dlSpeedUnit: dlSpeedUnitNumber,
          ulSpeedUnit: ulSpeedUnitNumber,
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

        console.log('✅ [DownloaderSettingsDialog] 下载器设置已加载:', {
          ...this.currentSettings,
          schedule_rules_count: this.currentSettings.schedule_rules?.length || 0
        })
        console.log('✅ [DownloaderSettingsDialog] 速度限制 - 下载:', this.currentSettings.dlSpeedLimit || this.currentSettings.download_speed_limit, '上传:', this.currentSettings.ulSpeedLimit || this.currentSettings.upload_speed_limit)
        console.log('✅ [DownloaderSettingsDialog] 分时段规则数量:', this.currentSettings.schedule_rules?.length || 0)
      } else {
        console.warn('⚠️ [DownloaderSettingsDialog] 下载器设置响应无效，使用默认值')
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

      console.log('🔍 [DownloaderSettingsDialog] 开始加载能力信息...')
      // 加载能力信息
      const capResponse = await getDownloaderCapabilities(this.downloader.id)
      console.log('🔍 [DownloaderSettingsDialog] 能力信息响应:', capResponse)
      if (capResponse.code === '200' && capResponse.data) {
        // 后端返回的是嵌套结构，需要从 capabilities 对象中提取字段
        const responseData = capResponse.data as any
        const capabilitiesData = responseData.capabilities || {}

        // 构建扁平化的 capabilities 对象（兼容前端类型定义）
        this.capabilities = {
          downloader_id: responseData.downloaderId || responseData.downloader_id || '',
          downloader_type: responseData.downloaderType || responseData.downloader_type || 0,
          supports_speed_scheduling: capabilitiesData.supports_speed_scheduling || false,
          supports_connection_limits: capabilitiesData.connectionLimits !== undefined ? capabilitiesData.connectionLimits : true,
          supports_queue_management: capabilitiesData.queueSettings !== undefined ? capabilitiesData.queueSettings : true,
          supports_path_mapping: capabilitiesData.downloadPaths || false,
          supports_advanced_options: capabilitiesData.advancedSettings !== undefined ? capabilitiesData.advancedSettings : true
        }
        console.log('🔍 [DownloaderSettingsDialog] 能力信息已保存:', this.capabilities)
        console.log('🔍 [DownloaderSettingsDialog] supports_speed_scheduling:', this.capabilities.supports_speed_scheduling)
      }

      // 加载设置信息，包括 override_local
      if (this.currentSettings.override_local !== undefined) {
        this.formData.override_local = this.currentSettings.override_local
      }

      console.log('🔍 [DownloaderSettingsDialog] 开始加载路径映射配置...')
      // 加载路径映射配置
      const { getPathMappings } = await import('@/api/downloader')
      console.log('🔍 [DownloaderSettingsDialog] getPathMappings 函数已导入:', getPathMappings)
      console.log('🔍 [DownloaderSettingsDialog] 准备调用 getPathMappings, downloader.id:', this.downloader.id)

      const pathMappingResponse = await getPathMappings(this.downloader.id)
      console.log('🔍 [DownloaderSettingsDialog] 路径映射响应:', pathMappingResponse)

      if (pathMappingResponse.code === '200' && pathMappingResponse.data) {
        console.log('🔍 [DownloaderSettingsDialog] 路径映射数据有效，准备保存')
        // 使用 $set 确保 Vue 响应式更新
        this.$set(this.currentSettings, 'path_mapping', pathMappingResponse.data)
        console.log('🔍 [DownloaderSettingsDialog] currentSettings.path_mapping 已更新:', this.currentSettings.path_mapping)
      } else {
        console.log('🔍 [DownloaderSettingsDialog] 路径映射响应无效，code:', pathMappingResponse.code, 'data:', pathMappingResponse.data)
      }
    } catch (error) {
      console.error('🔍 [DownloaderSettingsDialog] 加载下载器设置失败:', error)
      console.error('🔍 [DownloaderSettingsDialog] 错误详情:', error?.response?.data || error?.message || error)
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
    // ✅ 验证必填字段（新增模式必须填写完整连接信息）
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
    } catch (error: any) {
      this.testResult = {
        success: false,
        message: error?.response?.data?.msg || error?.message || '连接失败'
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
  private handleTemplateSelected(template: any) {
    // 应用模板到当前设置
    Object.assign(this.currentSettings, template.settings)

    // 切换到基础设置标签页查看应用结果
    this.activeTab = 'auth'
  }

  // 提交表单
  private async handleSubmit() {
    try {
      // 验证基本信息表单
      await this.basicFormRef.validate()

      // 收集所有标签页的数据（不包括基本信息页签，因为已经在 formData 中）
      console.log('🔍 [DEBUG] 开始收集数据...')
      console.log('🔍 [DEBUG] this.$refs:', this.$refs)
      console.log('🔍 [DEBUG] speedSettingsTabRef:', this.$refs.speedSettingsTabRef)

      const speedData = (this.$refs.speedSettingsTabRef as any)?.getFormData() || {}
      const advancedData = (this.$refs.advancedSettingsTabRef as any)?.getFormData() || {}
      const pathMappingData = (this.$refs.pathManagementTabRef as any)?.getPathMappingData() || null

      console.log('🔍 [DEBUG] speedData:', speedData)
      console.log('🔍 [DEBUG] advancedData:', advancedData)
      console.log('🔍 [DEBUG] pathMappingData:', pathMappingData)

      // 从 formData 中提取需要提交到设置的数据
      const settingsData = {
        override_local: this.formData.override_local
      }

      // 构建基本信息提交数据（只包含基本信息字段）
      const basicData: any = {
        ...this.formData
      }

      // 添加路径映射数据（包括空数组，用于清空配置）
      // 只要 pathMappingData 不是 null/undefined，就提交（让后端判断是更新还是清空）
      if (pathMappingData !== null && pathMappingData !== undefined) {
        basicData['path_mapping'] = pathMappingData
      }

      // 处理密码和原密码字段
      if (this.isEdit) {
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
        await upDownloader({ ...basicData, id: this.downloader!.id })

        // 如果有设置变更，同时更新设置并应用到下载器
        console.log('🔍 [DEBUG] settingsData:', settingsData)
        console.log('🔍 [DEBUG] speedData:', speedData)
        console.log('🔍 [DEBUG] advancedData:', advancedData)
        console.log('🔍 [DEBUG] 条件判断:', Object.keys(settingsData).length, Object.keys(speedData).length, Object.keys(advancedData).length)

        if (Object.keys(settingsData).length > 0 || Object.keys(speedData).length > 0 || Object.keys(advancedData).length > 0) {
          // 1. 保存设置到数据库
          const updateResponse = await updateDownloaderSettings(this.downloader!.id, {
            ...settingsData,
            ...speedData,
            ...advancedData
          })

          if (updateResponse.code === '200' && updateResponse.data?.schedule_rules !== undefined) {
            this.$set(this.currentSettings, 'schedule_rules', updateResponse.data.schedule_rules)
            console.log('✅ [DownloaderSettingsDialog] 规则ID已更新:', this.currentSettings.schedule_rules)
          }

          // 2. 应用设置到下载器客户端
          const loadingMessage = this.$message({
            message: '正在应用配置到下载器...',
            type: 'info',
            duration: 0,
            iconClass: 'el-icon-loading'
          })

          try {
            await applyDownloaderSettings(this.downloader!.id)
            loadingMessage.close()
            this.$message.success('保存成功，配置已应用到下载器')
          } catch (applyError: any) {
            loadingMessage.close()
            const applyErrorMsg = applyError?.response?.data?.msg || applyError?.message || '配置应用失败'
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
    } catch (error: any) {
      console.error('提交失败:', error)
      const errorMsg = error?.response?.data?.msg || error?.message || '操作失败'
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
</style>
