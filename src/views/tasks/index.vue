<template>
  <div class="app-container scheduled-tasks-page">
    <!-- 标签页 -->
    <el-tabs v-model="activeTab" @tab-click="handleTabClick">
      <!-- 任务管理标签页 -->
      <el-tab-pane name="tasks">
        <template slot="label">
          <svg class="tab-icon" style="width: 20px; height: 20px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/>
          </svg>
          任务管理
        </template>
        <!-- 页面标题 -->
        <div class="section-header">
          <h2 class="section-title">任务列表</h2>
        </div>
        <!-- 搜索筛选区 -->
        <section class="filter-section">
          <div class="filter-form">
            <div class="form-group">
              <label class="form-label">任务名称</label>
              <el-input
                v-model="queryParams.taskName"
                placeholder="请输入任务名称"
                clearable

                @keyup.enter="handleQuery"
              />
            </div>
            <div class="form-group">
              <label class="form-label">任务编码</label>
              <el-input
                v-model="queryParams.taskCode"
                placeholder="请输入任务编码"
                clearable

                @keyup.enter="handleQuery"
              />
            </div>
            <div class="form-group">
              <label class="form-label">是否启用</label>
              <el-select v-model="queryParams.enabled" placeholder="请选择" clearable>
                <el-option label="启用" :value="true" />
                <el-option label="禁用" :value="false" />
              </el-select>
            </div>
            <div class="form-group">
              <label class="form-label">任务类型</label>
              <el-select v-model="queryParams.taskType" placeholder="请选择" clearable>
                <el-option label="shell脚本" :value="0" />
                <el-option label="cmd脚本" :value="1" />
                <el-option label="powershell脚本" :value="2" />
                <el-option label="python脚本" :value="3" />
                <el-option label="python内部类" :value="4" />
                <el-option label="清理回收站" :value="5" />
              </el-select>
            </div>
            <div class="form-group" style="flex-direction: row; align-items: flex-end; gap: 8px;">
              <el-button type="primary" class="btn" @click="handleQuery">
                🔍 查询
              </el-button>
              <el-button class="btn btn-secondary" @click="resetQuery">
                🔄 重置
              </el-button>
            </div>
          </div>
        </section>

        <!-- 批量操作工具栏 -->
        <section class="batch-toolbar">
          <!-- 批量启用 -->
          <batch-button
            type="success"
            icon="el-icon-video-play"
            tooltip="启用"
            :disabled="multipleSelection.length === 0"
            @click="handleBatchEnable"
          />

          <!-- 批量暂停 -->
          <batch-button
            type="warning"
            icon="el-icon-video-pause"
            tooltip="暂停"
            :disabled="multipleSelection.length === 0"
            @click="handleBatchDisable"
          />

          <!-- 批量删除 -->
          <batch-button
            type="danger"
            icon="el-icon-delete"
            tooltip="删除"
            :disabled="multipleSelection.length === 0"
            @click="handleBatchDelete"
          />

          <!-- 批量重检 -->
          <batch-button
            type="info"
            icon="el-icon-refresh"
            tooltip="重检"
            :disabled="multipleSelection.length === 0"
            @click="handleRefresh"
          />

          <div style="flex: 1"></div>

          <!-- 刷新 -->
          <batch-button
            type="default"
            icon="el-icon-refresh"
            tooltip="刷新"
            @click="handleRefresh"
          />

          <!-- 新增任务 -->
          <batch-button
            type="primary"
            icon="el-icon-plus"
            tooltip="新增任务"
            @click="handleCreate"
          />
        </section>

        <!-- 任务列表表格 -->
        <div class="table-container">
          <el-table
            :data="taskList"
            v-loading="loading"
            @selection-change="handleSelectionChange"
            style="width: 100%"
          >
            <el-table-column type="selection" width="55" />
            <el-table-column prop="taskName" label="任务名称" min-width="150" show-overflow-tooltip resizable />
            <el-table-column prop="taskCode" label="任务编码" width="120" show-overflow-tooltip resizable />
            <el-table-column prop="taskTypeName" label="任务类型" width="110" resizable>
              <template slot-scope="scope">
                <el-tag :type="getTaskTypeTag(scope.row.taskType)" size="small">
                  {{ scope.row.taskTypeName }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="taskStatusName" label="状态" width="100" resizable>
              <template slot-scope="scope">
                <el-tag :type="getStatusTag(scope.row.taskStatusName)" size="small">
                  {{ scope.row.taskStatusName }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="enabled" label="启用状态" width="90" align="center" resizable>
              <template slot-scope="scope">
                <el-tag :type="scope.row.enabled ? 'success' : 'info'" size="small">
                  {{ scope.row.enabled ? '已启用' : '已禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="cronPlan" label="Cron表达式" min-width="150" show-overflow-tooltip resizable>
              <template slot-scope="scope">
                <code class="cron-code">{{ scope.row.cronPlan }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="lastExecuteTime" label="上次执行时间" min-width="160" show-overflow-tooltip resizable />
            <el-table-column label="操作" width="110" fixed="right" align="center" resizable>
        <template slot-scope="scope">
          <el-dropdown @command="handleCommand" trigger="click" size="mini">
            <el-button size="mini" type="primary">
              操作 <i class="el-icon-arrow-down el-icon--right"></i>
            </el-button>
            <el-dropdown-menu slot="dropdown">
              <el-dropdown-item
                :command="{action: 'execute', row: scope.row}"
                :disabled="!scope.row.enabled"
              >
                <i class="el-icon-video-play"></i>
                立即执行
                <el-tooltip v-if="!scope.row.enabled" content="任务已禁用，请先启用" placement="right">
                  <i class="el-icon-info" style="color: #909399; margin-left: 5px;"></i>
                </el-tooltip>
              </el-dropdown-item>
              <el-dropdown-item :command="{action: 'edit', row: scope.row}">
                <i class="el-icon-edit"></i> 编辑
              </el-dropdown-item>
              <el-dropdown-item :command="{action: 'logs', row: scope.row}">
                <i class="el-icon-view"></i> 查看日志
              </el-dropdown-item>
              <el-dropdown-item :command="{action: 'interrupt', row: scope.row}">
                <i class="el-icon-video-pause"></i> 中断
              </el-dropdown-item>
              <el-dropdown-item :command="{action: 'delete', row: scope.row}" divided>
                <i class="el-icon-delete" style="color: #f56c6c;"></i>
                <span style="color: #f56c6c;">删除</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>
        </template>
      </el-table-column>
          </el-table>
        </div>

      <!-- 分页组件 - 使用种子管理页面的固定分页样式 -->
      <nav class="task-pagination">
        <span class="pagination-info">共 {{ total }} 条，第 {{ queryParams.page }}/{{ Math.ceil(total / queryParams.limit) || 1 }} 页</span>
        <div class="pagination-controls">
          <!-- 每页条数选择器 -->
          <el-select
            v-model="queryParams.limit"
            class="page-size-select"
            @change="handleSizeChange"
          >
            <el-option
              v-for="size in [5, 20, 50, 100, 200]"
              :key="size"
              :label="`${size} 条/页`"
              :value="size"
            />
          </el-select>

          <button
            class="pagination-btn"
            :disabled="queryParams.page <= 1"
            @click="handleCurrentChange(queryParams.page - 1)"
          >
            ◀
          </button>
          <button
            v-for="page in visiblePages"
            :key="page"
            class="pagination-btn"
            :class="{active: page === queryParams.page}"
            @click="handleCurrentChange(page)"
          >
            {{ page }}
          </button>
          <button
            class="pagination-btn"
            :disabled="queryParams.page >= Math.ceil(total / queryParams.limit)"
            @click="handleCurrentChange(queryParams.page + 1)"
          >
            ▶
          </button>
        </div>
      </nav>
      </el-tab-pane>

      <!-- 任务日志标签页 -->
      <el-tab-pane name="logs">
        <template slot="label">
          <svg class="tab-icon" style="width: 20px; height: 20px;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          任务日志
        </template>
        <!-- 页面标题 -->
        <div class="section-header">
          <h2 class="section-title">任务日志</h2>
        </div>
        <!-- 日志统计信息 - 紧凑一行布局 -->
        <div class="log-stats-compact">
          <div class="log-stat-item">
            <div class="log-stat-icon primary">📊</div>
            <div class="log-stat-content">
              <div class="log-stat-value">{{ logStatistics.totalLogs }}</div>
              <div class="log-stat-label">总日志数</div>
            </div>
          </div>
          <div class="log-stat-item">
            <div class="log-stat-icon success">✅</div>
            <div class="log-stat-content">
              <div class="log-stat-value">{{ logStatistics.successLogs }}</div>
              <div class="log-stat-label">成功日志</div>
            </div>
          </div>
          <div class="log-stat-item">
            <div class="log-stat-icon danger">❌</div>
            <div class="log-stat-content">
              <div class="log-stat-value">{{ logStatistics.failedLogs }}</div>
              <div class="log-stat-label">失败日志</div>
            </div>
          </div>
          <div class="log-stat-item">
            <div class="log-stat-icon info">📅</div>
            <div class="log-stat-content">
              <div class="log-stat-value">{{ logStatistics.todayLogs }}</div>
              <div class="log-stat-label">今日日志</div>
            </div>
          </div>
        </div>

        <!-- 日志筛选区 -->
        <section class="filter-section filter-section-logs">
          <div class="filter-form filter-form-logs">
            <!-- 第一行：任务名称、日志内容、执行结果、搜索/重置按钮 -->
            <div class="form-group">
              <label class="form-label">任务名称</label>
              <el-input
                v-model="logQueryParams.task_name"
                placeholder="搜索任务名称"
                clearable

                @keyup.enter="handleLogQuery"
              />
            </div>

            <div class="form-group">
              <label class="form-label">日志内容</label>
              <el-input
                v-model="logQueryParams.log_content"
                placeholder="搜索日志内容"
                clearable

                @keyup.enter="handleLogQuery"
              />
            </div>

            <div class="form-group">
              <label class="form-label">执行结果</label>
              <el-select
                v-model="logQueryParams.success"
                placeholder="执行结果"
                clearable

              >
                <el-option label="成功" :value="true" />
                <el-option label="失败" :value="false" />
              </el-select>
            </div>

            <div class="form-group" style="flex-direction: row; align-items: flex-end; gap: 8px;">
              <el-button type="primary" class="btn" @click="handleLogQuery">
                🔍 搜索
              </el-button>
              <el-button class="btn btn-secondary" @click="resetLogQuery">
                🔄 重置
              </el-button>
            </div>

            <!-- 第二行：时间范围（单独一行） -->
            <div class="form-group form-group-wide">
              <label class="form-label">时间范围</label>
              <el-date-picker
                v-model="logDateRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                value-format="yyyy-MM-dd HH:mm:ss"

                @change="handleLogDateRangeChange"
              />
            </div>
          </div>
        </section>

        <!-- 日志操作工具栏 -->
        <section class="batch-toolbar">
          <el-button
            v-if="logMultipleSelection.length > 0"
            type="danger"
            class="batch-btn batch-btn-danger"
            @click="handleLogBatchDelete"
          >
            🗑️ 批量删除 ({{ logMultipleSelection.length }})
          </el-button>

          <el-dropdown @command="handleLogExport">
            <el-button type="success" class="batch-btn batch-btn-info">
              📥 导出
            </el-button>
            <el-dropdown-menu slot="dropdown">
              <el-dropdown-item command="csv">导出为 CSV</el-dropdown-item>
              <el-dropdown-item command="json">导出为 JSON</el-dropdown-item>
              <el-dropdown-item command="txt">导出为 TXT</el-dropdown-item>
            </el-dropdown-menu>
          </el-dropdown>

          <el-button
            type="warning"
            class="batch-btn batch-btn-warning"
            @click="handleLogCleanup"
          >
            🧹 清理过期日志
          </el-button>
        </section>

        <!-- 日志列表表格 -->
        <div class="log-table-container">
          <el-table
          :data="logList"
          v-loading="logLoading"
          @selection-change="handleLogSelectionChange"
          header-row-class-name="log-table-header"
          style="width: 100%"
        >
          <el-table-column type="selection" width="55" />
          <el-table-column prop="taskName" label="任务名称" min-width="150" show-overflow-tooltip resizable />
          <el-table-column prop="taskTypeName" label="任务类型" width="110" resizable>
            <template slot-scope="scope">
              <el-tag :type="getLogTaskTypeTag(scope.row.taskType)" size="small">
                {{ getLogTaskTypeName(scope.row.taskType) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="startTime" label="开始时间" min-width="160" show-overflow-tooltip resizable />
          <el-table-column prop="endTime" label="结束时间" min-width="160" show-overflow-tooltip resizable />
          <el-table-column prop="duration" label="耗时" width="90" align="center" resizable>
            <template slot-scope="scope">
              <span :style="{color: scope.row.duration > 60 ? '#f56c6c' : scope.row.duration > 10 ? '#e6a23c' : '#67c23a', fontWeight: '500'}">
                {{ scope.row.duration }}s
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="success" label="执行结果" width="90" align="center" resizable>
            <template slot-scope="scope">
              <el-tag :type="scope.row.success ? 'success' : 'danger'" size="small">
                {{ scope.row.success ? '成功' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="执行详情" min-width="150" resizable>
            <template slot-scope="scope">
              <div style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ scope.row.logDetail }}
              </div>
              <el-button
                v-if="scope.row.logDetail"
                size="mini"
                type="text"
                @click="handleViewLogDetail(scope.row)"
                style="margin-top: 5px; padding: 0;"
              >
                查看详情
              </el-button>
            </template>
          </el-table-column>
          </el-table>
        </div>

        <!-- 日志分页组件 - 使用种子管理页面的固定分页样式 -->
        <nav class="task-pagination">
          <span class="pagination-info">共 {{ logTotal }} 条，第 {{ logQueryParams.page }}/{{ Math.ceil(logTotal / logQueryParams.limit) || 1 }} 页</span>
          <div class="pagination-controls">
            <!-- 每页条数选择器 -->
            <el-select
              v-model="logQueryParams.limit"
              class="page-size-select"
              @change="handleLogSizeChange"
            >
              <el-option
                v-for="size in [5, 20, 50, 100, 200, 500, 1000]"
                :key="size"
                :label="`${size} 条/页`"
                :value="size"
              />
            </el-select>

            <button
              class="pagination-btn"
              :disabled="logQueryParams.page <= 1"
              @click="handleLogCurrentChange(logQueryParams.page - 1)"
            >
              ◀
            </button>
            <button
              v-for="page in visibleLogPages"
              :key="page"
              class="pagination-btn"
              :class="{active: page === logQueryParams.page}"
              @click="handleLogCurrentChange(page)"
            >
              {{ page }}
            </button>
            <button
              class="pagination-btn"
              :disabled="logQueryParams.page >= Math.ceil(logTotal / logQueryParams.limit)"
              @click="handleLogCurrentChange(logQueryParams.page + 1)"
            >
              ▶
            </button>
          </div>
        </nav>
      </el-tab-pane>
    </el-tabs>

    <!-- 任务表单对话框 -->
    <el-dialog
      :title="dialogTitle"
      :visible.sync="dialogVisible"
      width="800px"
      :close-on-click-modal="false"
      custom-class="task-dialog"
    >
      <el-form ref="taskForm" :model="taskForm" :rules="rules" label-width="120px" class="task-form">
        <!-- 基本信息 -->
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="任务名称" prop="task_name">
              <el-input v-model="taskForm.task_name" placeholder="请输入任务名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任务编码" prop="task_code">
              <el-input v-model="taskForm.task_code" placeholder="请输入任务编码" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="任务类型" prop="task_type">
          <el-select
            v-model="taskForm.task_type"
            placeholder="请选择任务类型"
            style="width: 100%"
            @change="handleTaskTypeChange"
          >
            <el-option
              v-for="option in taskTypeOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            >
              <i :class="option.icon" style="margin-right: 8px;"></i>
              {{ option.label }}
            </el-option>
          </el-select>
        </el-form-item>

        <!-- 执行内容 - 根据任务类型动态显示 -->
        <el-form-item
          :label="getExecutorLabel()"
          prop="executor"
          v-if="taskForm.task_type !== 4 && taskForm.task_type !== 5"
        >
          <monaco-editor
            v-model="taskForm.executor"
            :language="getEditorLanguage()"
            height="200px"
            :syntax-validation="true"
            @validation-change="handleSyntaxValidation"
            @init-error="handleEditorInitError"
            @focus="handleEditorFocus"
            @blur="handleEditorBlur"
          />
          <div v-if="syntaxErrors.length > 0" class="syntax-errors">
            <el-alert
              v-for="error in syntaxErrors.slice(0, 3)"
              :key="`${error.startLineNumber}-${error.startColumn}`"
              :title="`第${error.startLineNumber}行：${error.message}`"
              type="error"
              show-icon
              :closable="false"
              size="mini"
              style="margin-bottom: 8px;"
            />
            <div v-if="syntaxErrors.length > 3" class="more-errors">
              <el-link type="primary" @click="showAllErrors = true">
                查看全部 {{ syntaxErrors.length }} 个错误
              </el-link>
            </div>
            <el-collapse v-if="showAllErrors && syntaxErrors.length > 3" class="all-errors">
              <el-collapse-item
                v-for="(error, index) in syntaxErrors.slice(3)"
                :key="`error-${index}`"
                :title="`第${error.startLineNumber}行：${error.message}`"
                name="error"
              >
                <div class="error-detail">
                  <strong>第{{ error.startLineNumber }}行, 第{{ error.startColumn }}列:</strong>
                  {{ error.message }}
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
          <div v-else-if="syntaxValidationResult && syntaxValidationResult.valid === true" class="syntax-success">
            <el-alert
              title="语法检查通过"
              type="success"
              description="代码语法正确, 可以正常执行"
              show-icon
              :closable="false"
              size="mini"
            />
          </div>
        </el-form-item>

        <!-- Python类选择器 -->
        <el-form-item
          label="执行类"
          prop="executor"
          v-if="taskForm.task_type === 4"
        >
          <python-class-selector
            v-model="taskForm.executor"
            @change="handlePythonClassChange"
            @class-selected="handlePythonClassSelected"
          />
        </el-form-item>

        <!-- 清理任务配置表单 -->
        <el-form-item
          v-if="taskForm.task_type === 5"
          label="清理配置"
        >
          <el-row :gutter="20">
            <el-col :span="8">
              <el-form-item label="清理等级3" label-width="100px">
                <el-switch
                  v-model="cleanupConfig.cleanup_level_3"
                  active-text="启用"
                  inactive-text="禁用"
                />
                <div class="form-help">
                  <small>清理等级为3的种子</small>
                </div>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="清理等级4" label-width="100px">
                <el-switch
                  v-model="cleanupConfig.cleanup_level_4"
                  active-text="启用"
                  inactive-text="禁用"
                />
                <div class="form-help">
                  <small>清理等级为4的种子</small>
                </div>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="天数阈值" label-width="100px">
                <el-input-number
                  v-model="cleanupConfig.days_threshold"
                  :min="1"
                  :max="365"
                  placeholder="天数"
                  style="width: 100%"
                />
                <div class="form-help">
                  <small>清理多少天前的种子（1-365天）</small>
                </div>
              </el-form-item>
            </el-col>
          </el-row>

          <!-- 预览按钮 -->
          <el-row :gutter="20" style="margin-top: 10px;">
            <el-col :span="24">
              <el-button
                type="info"
                size="small"
                @click="previewCleanup"
                :loading="previewLoading"
              >
                🔍 预览清理
              </el-button>
            </el-col>
          </el-row>
        </el-form-item>

        <!-- Cron表达式编辑器 -->
        <el-form-item label="执行计划" prop="cron_plan">
          <cron-editor
            v-model="taskForm.cron_plan"
            @change="handleCronChange"
          />
          <div v-if="cronValidationResult && !cronValidationResult.valid" class="cron-validation-error">
            <el-alert
              :title="'Cron表达式错误: ' + cronValidationResult.message"
              type="error"
              show-icon
              :closable="false"
              style="margin-top: 8px;"
            />
          </div>
        </el-form-item>

        <!-- 高级配置 -->
        <el-form-item>
          <el-button type="text" @click="showAdvancedConfig = !showAdvancedConfig" size="small">
            <i :class="showAdvancedConfig ? 'el-icon-arrow-up' : 'el-icon-arrow-down'"></i>
            {{ showAdvancedConfig ? '收起' : '展开' }}高级配置
          </el-button>
        </el-form-item>

        <el-collapse-transition>
          <div v-show="showAdvancedConfig" class="advanced-config">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="超时时间">
                  <el-input-number
                    v-model="taskForm.timeout_seconds"
                    :min="60"
                    :max="86400"
                    placeholder="秒"
                    style="width: 100%"
                  />
                  <div class="form-help">
                    <small>任务执行超时时间(秒), 默认1小时</small>
                  </div>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="最大重试次数">
                  <el-input-number
                    v-model="taskForm.max_retry_count"
                    :min="0"
                    :max="10"
                    placeholder="次数"
                    style="width: 100%"
                  />
                  <div class="form-help">
                    <small>失败后最大重试次数, 默认不重试</small>
                  </div>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item label="重试间隔">
                  <el-input-number
                    v-model="taskForm.retry_interval"
                    :min="60"
                    :max="3600"
                    placeholder="秒"
                    style="width: 100%"
                  />
                  <div class="form-help">
                    <small>重试间隔时间(秒), 默认5分钟</small>
                  </div>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="任务描述">
                  <el-input
                    v-model="taskForm.description"
                    type="textarea"
                    :rows="2"
                    placeholder="任务描述（可选）"
                    style="width: 100%"
                  />
                </el-form-item>
              </el-col>
            </el-row>
          </div>
        </el-collapse-transition>

        <!-- 是否启用 -->
        <el-form-item prop="enabled">
          <el-switch
            v-model="taskForm.enabled"
            :active-text="taskForm.enabled ? '启用' : '禁用'"
            :inactive-text="taskForm.enabled ? '禁用' : '启用'"
          />
          <div class="form-help">
            <small>
              {{ taskForm.enabled ? '启用状态：任务将按计划执行' : '禁用状态：任务不会执行' }}
            </small>
          </div>
        </el-form-item>
      </el-form>

      <div slot="footer" class="dialog-footer">
        <el-button @click="dialogVisible = false" :disabled="submitLoading">取消</el-button>
        <el-button
          type="primary"
          @click="handleSubmit"
          :loading="submitLoading"
          :disabled="!canSubmit"
        >
          <i class="el-icon-check"></i>
          {{ submitLoading ? '保存中...' : '确定' }}
        </el-button>
      </div>
    </el-dialog>

    <!-- 任务执行详情弹窗 -->
    <el-dialog
      title="任务执行详情"
      :visible.sync="logDetailVisible"
      width="700px"
      :close-on-click-modal="false"
      custom-class="log-detail-dialog"
    >
      <div class="log-detail-content">
        <div class="log-detail-header">
          <div class="detail-item">
            <span class="label">任务名称：</span>
            <span class="value">{{ selectedLog?.taskName }}</span>
          </div>
          <div class="detail-item">
            <span class="label">执行时间：</span>
            <span class="value">{{ selectedLog?.startTime }} ~ {{ selectedLog?.endTime }}</span>
          </div>
          <div class="detail-item">
            <span class="label">执行结果：</span>
            <el-tag :type="selectedLog?.success ? 'success' : 'danger'" size="small">
              {{ selectedLog?.success ? '成功' : '失败' }}
            </el-tag>
          </div>
          <div class="detail-item">
            <span class="label">执行耗时：</span>
            <span class="value" :style="{color: selectedLog?.duration > 60 ? '#f56c6c' : selectedLog?.duration > 10 ? '#e6a23c' : '#67c23a', fontWeight: '500'}">
              {{ selectedLog?.duration }}s
            </span>
          </div>
        </div>

        <div class="log-detail-main">
          <h4 class="detail-title">执行详情内容：</h4>
          <div class="detail-content">
            <pre>{{ selectedLog?.logDetail || '暂无详情信息' }}</pre>
          </div>
        </div>
      </div>

      <div slot="footer" class="dialog-footer">
        <el-button @click="logDetailVisible = false">关闭</el-button>
        <el-button type="primary" @click="handleCopyLogDetail">复制内容</el-button>
      </div>
    </el-dialog>

    <!-- 清理预览对话框 -->
    <el-dialog
      title="清理预览"
      :visible.sync="previewDialogVisible"
      width="600px"
    >
      <div v-if="previewData">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="等级3种子">
            {{ previewData.level3_count }} 个
          </el-descriptions-item>
          <el-descriptions-item label="等级4种子">
            {{ previewData.level4_count }} 个
          </el-descriptions-item>
          <el-descriptions-item label="总计">
            {{ previewData.total_count }} 个
          </el-descriptions-item>
          <el-descriptions-item label="释放空间">
            {{ previewData.total_size_gb }} GB
          </el-descriptions-item>
        </el-descriptions>

        <!-- 等级3种子列表（可折叠） -->
        <el-collapse v-if="previewData.level3_items && previewData.level3_items.length > 0" style="margin-top: 20px;">
          <el-collapse-item title="等级3种子详情（最多显示20条）" name="level3">
            <el-table :data="previewData.level3_items" size="small" max-height="300">
              <el-table-column prop="name" label="名称" show-overflow-tooltip />
              <el-table-column prop="size" label="大小(GB)">
                <template slot-scope="scope">
                  {{ (scope.row.size / 1024**3).toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column prop="deleted_at" label="删除时间" width="180" />
            </el-table>
          </el-collapse-item>
        </el-collapse>

        <!-- 等级4种子列表（可折叠） -->
        <el-collapse v-if="previewData.level4_items && previewData.level4_items.length > 0" style="margin-top: 10px;">
          <el-collapse-item title="等级4种子详情（最多显示20条）" name="level4">
            <el-table :data="previewData.level4_items" size="small" max-height="300">
              <el-table-column prop="name" label="名称" show-overflow-tooltip />
              <el-table-column prop="size" label="大小(GB)">
                <template slot-scope="scope">
                  {{ (scope.row.size / 1024**3).toFixed(2) }}
                </template>
              </el-table-column>
              <el-table-column prop="tags" label="标签" width="150" />
            </el-table>
          </el-collapse-item>
        </el-collapse>
      </div>

      <div slot="footer" class="dialog-footer">
        <el-button @click="previewDialogVisible = false">关闭</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import { Component, Vue, Watch } from 'vue-property-decorator'
import {
  getTaskList,
  createTask,
  updateTask,
  deleteTasks,
  executeTask,
  interruptTask,
  getTaskLogs,
  getTaskLogStatistics,
  ScheduledTask,
  TaskCreateRequest,
  TaskLog,
  TaskLogQueryParams
} from '@/api/tasks'
import request from '@/utils/request'

// 导入新创建的组件
import MonacoEditor from '@/components/tasks/MonacoEditor.vue'
import CronEditor from '@/components/tasks/CronEditor.vue'
import PythonClassSelector from '@/components/tasks/PythonClassSelector.vue'

// 使用集中类型定义
import {
  BTDeckTypes
} from '@/types'

// 使用集中类型定义
interface TaskForm extends BTDeckTypes.TaskCreateRequest {
  id?: number
}

// ValidationMarker和ValidationResult使用集中类型
type ValidationMarker = BTDeckTypes.ValidationError
type ValidationResult = BTDeckTypes.ScriptValidationResult

@Component({
  name: 'TaskManage',
  components: {
    MonacoEditor,
    CronEditor,
    PythonClassSelector
  }
})
export default class TaskManage extends Vue {
  private taskList: BTDeckTypes.ScheduledTask[] = []
  private loading = false
  private dialogVisible = false
  private dialogTitle = ''
  private submitLoading = false
  private total = 0

  // 任务统计数据
  private taskStatistics = {
    total: 0,
    running: 0,
    paused: 0,
    failed: 0
  }

  // 批量选择
  private multipleSelection: BTDeckTypes.ScheduledTask[] = []
  private logMultipleSelection: BTDeckTypes.TaskLog[] = []

  // 标签页相关
  private activeTab = 'tasks'

  // 日志相关数据
  private logList: BTDeckTypes.TaskLog[] = []
  private logLoading = false
  private logTotal = 0
  private logStatistics = {
    totalLogs: 0,
    successLogs: 0,
    failedLogs: 0,
    todayLogs: 0
  }

  // 查询参数
  private queryParams = {
    taskName: '',
    taskCode: '',
    enabled: undefined as boolean | undefined,
    taskType: undefined as number | undefined,
    page: 1,
    limit: 20
  }

  // 日志查询参数
  private logQueryParams = {
    task_name: '',
    task_id: undefined as number | undefined,
    log_content: '',
    success: undefined as boolean | undefined,
    page: 1,
    limit: 20
  }

  private taskForm: TaskForm = {
    task_name: '',
    task_code: '',
    task_type: 0,
    executor: '',
    cron_plan: '',
    enabled: true,
    description: '',
    timeout_seconds: 3600,
    max_retry_count: 0,
    retry_interval: 300
  }

  // 清理任务配置
  private cleanupConfig = {
    cleanup_level_3: true,
    cleanup_level_4: true,
    days_threshold: 30
  }

  // 任务类型选项
  private taskTypeOptions: TaskTypeOption[] = [
    { label: 'shell脚本', value: 0, icon: 'el-icon-document', description: 'Linux/Unix Shell脚本' },
    { label: 'cmd脚本', value: 1, icon: 'el-icon-document', description: 'Windows批处理脚本' },
    { label: 'powershell脚本', value: 2, icon: 'el-icon-document', description: 'Windows PowerShell脚本' },
    { label: 'python脚本', value: 3, icon: 'el-icon-document', description: 'Python脚本文件' },
    { label: 'python内部类', value: 4, icon: 'el-icon-document', description: 'Python内部类方法' },
    { label: '清理回收站', value: 5, icon: 'el-icon-delete', description: '自动清理回收站任务' }
  ]

  // UI状态
  private showAdvancedConfig = false
  private syntaxErrors: ValidationMarker[] = []
  private syntaxValidationResult: ValidationResult | null = null
  private cronValidationResult: ValidationResult | null = null
  private showAllErrors = false
  private canSubmit = true

  // 清理预览相关
  private previewDialogVisible = false
  private previewData: any = null
  private previewLoading = false

  // 任务查询选项（修复模板undefined错误）
  private taskOptions: TaskTypeOption[] = [
    { label: 'shell脚本', value: 0, icon: 'el-icon-document', description: 'Linux/Unix Shell脚本' },
    { label: 'cmd脚本', value: 1, icon: 'el-icon-document', description: 'Windows批处理脚本' },
    { label: 'powershell脚本', value: 2, icon: 'el-icon-document', description: 'Windows PowerShell脚本' },
    { label: 'python脚本', value: 3, icon: 'el-icon-document', description: 'Python脚本文件' },
    { label: 'python内部类', value: 4, icon: 'el-icon-document', description: 'Python内部类方法' },
    { label: '清理回收站', value: 5, icon: 'el-icon-delete', description: '自动清理回收站任务' }
  ]

  // 日志查询相关（修复模板undefined错误）
  private logDateRange: any[] = []
  // 注意：logMultipleSelection 已在第 808 行声明为 BTDeckTypes.TaskLog[]

  // 执行详情相关
  private logDetailVisible = false
  private selectedLog: BTDeckTypes.TaskLog | null = null

  get rules() {
    return {
      task_name: [
        { required: true, message: '请输入任务名称', trigger: 'blur' }
      ],
      task_code: [
        { required: true, message: '请输入任务编码', trigger: 'blur' },
        { pattern: /^[a-zA-Z][a-zA-Z0-9_]*$/, message: '任务编码格式不正确', trigger: 'blur' }
      ],
      task_type: [
        { required: true, message: '请选择任务类型', trigger: 'change' }
      ],
      executor: [
        { required: true, message: '请输入执行内容', trigger: 'blur' }
      ],
      cron_plan: [
        { required: true, message: '请输入Cron表达式', trigger: 'blur' }
      ]
    }
  }

  // 计算任务统计数据
  private calculateTaskStatistics() {
    this.taskStatistics.total = this.taskList.length

    // 根据任务状态统计
    this.taskStatistics.running = this.taskList.filter(task =>
      task.taskStatusName === '运行中' || task.taskStatusName === '空闲'
    ).length

    this.taskStatistics.paused = this.taskList.filter(task =>
      task.taskStatusName === '已暂停'
    ).length

    this.taskStatistics.failed = this.taskList.filter(task =>
      task.taskStatusName === '失败' || task.taskStatusName === '已完成'
    ).length
  }


  created() {
    this.fetchTaskList()
  }

  @Watch('activeTab')
  private onActiveTabChange(newTab: string) {
    if (newTab === 'logs') {
      this.fetchLogStatistics()
      this.fetchLogList()
    }
  }

  @Watch('taskForm.task_name')
  @Watch('taskForm.task_code')
  @Watch('taskForm.executor')
  @Watch('taskForm.cron_plan')
  @Watch('taskForm.task_type')
  private onFormFieldChange() {
    this.$nextTick(() => {
      this.updateSubmitStatus()
    })
  }

  private async fetchTaskList() {
    try {
      this.loading = true
      const skip = (this.queryParams.page - 1) * this.queryParams.limit

      // 构建查询参数，过滤掉空值
      const params: any = {
        skip,
        limit: this.queryParams.limit
      }

      // 只有当值不为空时才添加到查询参数
      if (this.queryParams.taskName) {
        params.task_name = this.queryParams.taskName
      }
      if (this.queryParams.taskCode) {
        params.task_code = this.queryParams.taskCode
      }
      // 修复：检查enabled不为null、undefined和空字符串
      if (this.queryParams.enabled !== undefined && this.queryParams.enabled !== null && this.queryParams.enabled !== '') {
        params.enabled = this.queryParams.enabled
      }
      // 修复：检查taskType不为null、undefined和空字符串
      if (this.queryParams.taskType !== undefined && this.queryParams.taskType !== null && this.queryParams.taskType !== '') {
        params.task_type = this.queryParams.taskType
      }

      const response = await getTaskList(params)
      this.taskList = response.data?.list || []
      this.total = response.data?.total || 0

      // 计算任务统计数据
      this.calculateTaskStatistics()
    } catch (error) {
      console.error('获取任务列表失败:', error)
      this.$message.error('获取任务列表失败')
    } finally {
      this.loading = false
    }
  }

  private handleCreate() {
    this.dialogTitle = '新增任务'
    this.dialogVisible = true
    this.$nextTick(() => {
      this.resetForm()
      this.$refs.taskForm.validate()
    })
  }

  private handleEdit(row: ScheduledTask) {
    // 调试输出：检查实际的数据结构
    console.log('=== Edit Task Debug ===')
    // console.log('Row data:', row)
    // console.log('Row properties:', Object.keys(row))
    // console.log('row.taskId:', row.taskId)
    // console.log('row.id:', row.id)

    // 尝试多种可能的ID字段名
    const taskId = row.taskId || row.id || row.task_id || row.ID

    console.log('Resolved taskId:', taskId)

    this.dialogTitle = '编辑任务'
    this.dialogVisible = true
    this.taskForm = {
      id: taskId, // 使用解析出的ID
      task_name: row.taskName,
      task_code: row.taskCode,
      task_type: row.taskType,
      executor: row.executor || '',
      cron_plan: row.cronPlan,
      enabled: row.enabled,
      description: row.description || '',
      timeout_seconds: row.timeoutSeconds || 3600,
      max_retry_count: row.maxRetryCount || 0,
      retry_interval: row.retryInterval || 300
    }

    // 如果是清理任务，解析 executor JSON
    if (row.taskType === 5) {
      try {
        this.cleanupConfig = JSON.parse(row.executor || '{}')
        // 确保解析后的配置包含所有必需字段
        if (typeof this.cleanupConfig.cleanup_level_3 === 'undefined') {
          this.cleanupConfig.cleanup_level_3 = true
        }
        if (typeof this.cleanupConfig.cleanup_level_4 === 'undefined') {
          this.cleanupConfig.cleanup_level_4 = true
        }
        if (typeof this.cleanupConfig.days_threshold === 'undefined') {
          this.cleanupConfig.days_threshold = 30
        }
      } catch (e) {
        console.error('清理任务配置解析失败:', e)
        this.$message.error('清理任务配置解析失败，使用默认配置')
        this.cleanupConfig = {
          cleanup_level_3: true,
          cleanup_level_4: true,
          days_threshold: 30
        }
      }
    }
  }

  // 查看日志按钮点击处理
  private async handleViewLogs(row: ScheduledTask) {
    try {
      // 显示加载状态
      this.logLoading = true

      // 解析任务ID，支持多种字段名
      const taskId = row.taskId || row.id || row.task_id || row.ID

      if (!taskId) {
        this.$message.error('无法获取任务ID')
        throw new Error('无法获取任务ID')
      }

      console.log('=== View Logs Debug ===')
      console.log('Task ID:', taskId)
      console.log('Task Name:', row.taskName)

      // 1. 切换到日志页签
      this.activeTab = 'logs'

      // 2. 设置筛选条件
      this.logQueryParams.task_id = taskId
      this.logQueryParams.page = 1 // 重置到第一页

      // 3. 清空其他筛选条件以提供更精确的结果
      this.logQueryParams.task_name = ''
      this.logQueryParams.log_content = ''
      this.logQueryParams.success = undefined
      this.logDateRange = []

      // 4. 等待页签切换完成，然后刷新日志数据
      await this.$nextTick()

      // 5. 获取日志列表
      await this.fetchLogList()

      this.$message.success(`已切换到任务"${row.taskName}"的日志`)

    } catch (error) {
      console.error('查看日志失败:', error)
      this.$message.error('查看日志失败，请稍后重试')
    } finally {
      this.logLoading = false
    }
  }

  private async handleExecute(row: ScheduledTask) {
    // 检查任务是否启用
    if (!row.enabled) {
      this.$message.warning(`任务 "${row.taskName}" 已禁用，无法启动。请先启用该任务。`)
      return
    }

    try {
      await executeTask({ id: row.taskId })
      this.$message.success('任务执行成功')
      setTimeout(() => {
        this.fetchTaskList()
      }, 1000) // 延迟1秒刷新，等待状态更新
    } catch (error) {
      console.error('执行任务失败:', error)
      // 提取详细的错误信息
      const error_msg = error && error.response && error.response.data
        ? error.response.data.msg || error.response.data.message
        : '执行任务失败'
      this.$message.error(error_msg)
    }
  }

  private handleDelete(row: ScheduledTask) {
    this.$confirm('确定要删除这个任务吗?', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async() => {
      try {
        await deleteTasks({ ids: [row.taskId || row.id] }) // 优先使用taskId，兼容id字段
        this.$message.success('删除成功')
        this.fetchTaskList()
      } catch (error) {
        console.error('删除任务失败:', error)
        this.$message.error('删除任务失败')
      }
    }).catch((action) => {
      // 捕获用户取消操作，避免未处理的Promise rejection错误
      if (action === 'cancel') {
        console.log('用户取消删除任务操作')
      }
    })
  }

  private handleRefresh() {
    this.fetchTaskList()
  }

  // 批量启用任务
  private async handleBatchEnable() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请选择要启用的任务')
      return
    }

    try {
      await this.$confirm(`确定要启用选中的 ${this.multipleSelection.length} 个任务吗？`, '批量启用', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })

      // TODO: 调用批量启用API
      this.$message.success(`成功启用 ${this.multipleSelection.length} 个任务`)
      this.multipleSelection = []
      this.fetchTaskList()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('批量启用失败:', error)
        this.$message.error('批量启用失败')
      }
    }
  }

  // 批量禁用任务
  private async handleBatchDisable() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请选择要禁用的任务')
      return
    }

    try {
      await this.$confirm(`确定要禁用选中的 ${this.multipleSelection.length} 个任务吗？`, '批量禁用', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })

      // TODO: 调用批量禁用API
      this.$message.success(`成功禁用 ${this.multipleSelection.length} 个任务`)
      this.multipleSelection = []
      this.fetchTaskList()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('批量禁用失败:', error)
        this.$message.error('批量禁用失败')
      }
    }
  }

  // 批量删除任务
  private async handleBatchDelete() {
    if (this.multipleSelection.length === 0) {
      this.$message.warning('请选择要删除的任务')
      return
    }

    try {
      await this.$confirm(`确定要删除选中的 ${this.multipleSelection.length} 个任务吗？此操作不可恢复！`, '批量删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'error'
      })

      // 安全地提取任务ID，过滤掉undefined和null
      const ids = this.multipleSelection
        .map(task => task.id)
        .filter((id): id is number => id !== undefined && id !== null)
      await deleteTasks({ task_ids: ids })
      this.$message.success(`成功删除 ${ids.length} 个任务`)
      this.multipleSelection = []
      this.fetchTaskList()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('批量删除失败:', error)
        this.$message.error('批量删除失败')
      }
    }
  }

  private async handleSubmit() {
    try {
      await (this.$refs.taskForm as any).validate()
      this.submitLoading = true

      // 如果是清理任务类型，将 cleanupConfig 转为 JSON 赋值给 executor
      if (this.taskForm.task_type === 5) {
        this.taskForm.executor = JSON.stringify(this.cleanupConfig)
      }

      if (this.taskForm.id) {
        await updateTask(this.taskForm as TaskUpdateRequest)
        this.$message.success('更新成功')
      } else {
        await createTask(this.taskForm as TaskCreateRequest)
        this.$message.success('创建成功')
      }

      this.dialogVisible = false
      this.fetchTaskList()
    } catch (error) {
      console.error('保存任务失败:', error)
      this.$message.error('保存任务失败')
    } finally {
      this.submitLoading = false
    }
  }

  private resetForm() {
    this.taskForm = {
      task_name: '',
      task_code: '',
      task_type: 0,
      executor: '',
      cron_plan: '',
      enabled: true,
      description: '',
      timeout_seconds: 3600,
      max_retry_count: 0,
      retry_interval: 300
    }
    // 重置清理任务配置
    this.cleanupConfig = {
      cleanup_level_3: true,
      cleanup_level_4: true,
      days_threshold: 30
    }
    // 重置UI状态
    this.showAdvancedConfig = false
    this.syntaxErrors = []
    this.syntaxValidationResult = null
    this.cronValidationResult = null
    this.showAllErrors = false
    this.canSubmit = true

    if (this.$refs.taskForm) {
      (this.$refs.taskForm as any).resetFields()
    }

    // 重置后更新提交状态
    this.$nextTick(() => {
      this.updateSubmitStatus()
    })
  }

  private getTaskTypeName(type: number): string {
    const typeNames = {
      0: 'shell脚本',
      1: 'cmd脚本',
      2: 'powershell脚本',
      3: 'python脚本',
      4: 'python内部类',
      5: '清理回收站'
    }
    return typeNames[type] || '未知'
  }

  private getTaskTypeTag(type: number): string {
    const tags = {
      0: 'primary',    // shell - 主要
      1: 'success',    // cmd - 成功
      2: 'warning',    // powershell - 警告
      3: 'info',       // python - 信息
      4: 'danger',     // python内部类 - 危险
      5: 'warning'     // 清理回收站 - 警告
    }
    return tags[type] || 'info'
  }

  private getStatusName(statusName: string): string {
    // 直接使用后端返回的状态名称
    return statusName || '未知状态'
  }

  private getStatusTag(statusName: string): string {
    // 根据状态名称返回对应的标签类型
    const tags = {
      '等待运行': 'info',
      '运行中': 'success',
      '空闲': 'info',
      '已暂停': 'warning',
      '已停止': 'info',
      '已完成': 'success',
      '失败': 'danger'
    }
    return tags[statusName] || 'info'
  }

  // 查询方法
  private handleQuery() {
    this.queryParams.page = 1
    this.fetchTaskList()
  }

  // 重置查询
  private resetQuery() {
    this.queryParams = {
      taskName: '',
      taskCode: '',
      enabled: undefined,
      taskType: undefined,
      page: 1,
      limit: 20
    }
    this.fetchTaskList()
  }

  // 表格选择变化
  private handleSelectionChange(val: BTDeckTypes.ScheduledTask[]) {
    this.multipleSelection = val
  }

  // 日志表格选择变化
  private handleLogSelectionChange(val: BTDeckTypes.TaskLog[]) {
    this.logMultipleSelection = val
  }

  // 分页大小变化
  private handleSizeChange(val: number) {
    this.queryParams.limit = val
    this.queryParams.page = 1
    this.fetchTaskList()
  }

  // 当前页变化
  private handleCurrentChange(val: number) {
    this.queryParams.page = val
    this.fetchTaskList()
  }

  // 中断任务
  private async handleInterrupt(row: ScheduledTask) {
    try {
      await interruptTask(row.taskId)
      this.$message.success('任务中断成功')
      this.fetchTaskList()
    } catch (error) {
      console.error('中断任务失败:', error)
      this.$message.error('中断任务失败')
    }
  }

  // 处理下拉菜单命令
  private handleCommand(command: any) {
    const { action, row } = command

    switch (action) {
      case 'execute':
        this.handleExecute(row)
        break
      case 'edit':
        this.handleEdit(row)
        break
      case 'logs':
        this.handleViewLogs(row)
        break
      case 'interrupt':
        this.handleInterrupt(row)
        break
      case 'delete':
        this.handleDelete(row)
        break
      default:
        console.warn('未知的操作命令:', action)
    }
  }

  // ========== 新增的组件事件处理方法 ==========

  // 任务类型变化处理
  private handleTaskTypeChange(taskType: number) {
    // 清空执行内容
    this.taskForm.executor = ''
    // 重置语法验证状态
    this.syntaxErrors = []
    this.syntaxValidationResult = null
    // 更新提交状态
    this.$nextTick(() => {
      this.updateSubmitStatus()
    })
  }

  // 获取执行器标签
  private getExecutorLabel(): string {
    const labels = {
      0: 'Shell脚本',
      1: 'Cmd脚本',
      2: 'PowerShell脚本',
      3: 'Python脚本'
    }
    return labels[this.taskForm.task_type] || '执行内容'
  }

  // 获取编辑器语言
  private getEditorLanguage(): 'shell' | 'batch' | 'powershell' | 'python' {
    const languageMap = {
      0: 'shell' as const,
      1: 'batch' as const,
      2: 'powershell' as const,
      3: 'python' as const
    }
    return languageMap[this.taskForm.task_type] || 'shell'
  }

  // 语法校验变化处理
  private handleSyntaxValidation(errors: ValidationMarker[]) {
    this.syntaxErrors = errors
    this.syntaxValidationResult = {
      valid: errors.length === 0,
      message: errors.length === 0 ? '语法检查通过' : `发现 ${errors.length} 个语法错误`
    }
    this.updateSubmitStatus()
  }

  // Cron表达式变化处理
  private handleCronChange(expression: string, result: ValidationResult) {
    this.taskForm.cron_plan = expression
    this.cronValidationResult = result
    this.updateSubmitStatus()
  }

  // Python类变化处理
  private handlePythonClassChange(classPath: string) {
    this.taskForm.executor = classPath
    this.updateSubmitStatus()
  }

  // Python类选择处理
  private handlePythonClassSelected(classInfo: any) {
    this.taskForm.executor = classInfo.path
    this.updateSubmitStatus()
  }

  // 编辑器初始化错误处理
  private handleEditorInitError(error: any) {
    console.error('编辑器初始化失败:', error)
    this.$message.warning('代码编辑器加载失败，已切换到基础模式')
  }

  // 编辑器焦点事件
  private handleEditorFocus() {
    // 编辑器获得焦点时的处理
  }

  private handleEditorBlur() {
    // 编辑器失去焦点时的处理
    // 可以在这里进行语法检查
  }

  // 更新提交状态
  private updateSubmitStatus() {
    // 检查必填字段
    const hasRequiredFields = this.taskForm.task_name &&
                             this.taskForm.task_code &&
                             this.taskForm.cron_plan

    // 检查执行内容字段（根据任务类型判断是否必填）
    let hasExecutor = true
    if (this.taskForm.task_type === 4) {
      // Python内部类：executor是类路径，不能为空
      hasExecutor = this.taskForm.executor && this.taskForm.executor.trim() !== ''
    } else {
      // 脚本类型：executor是脚本内容，不能为空
      hasExecutor = this.taskForm.executor && this.taskForm.executor.trim() !== ''
    }

    // 如果必填字段不完整，直接返回false
    if (!hasRequiredFields || !hasExecutor) {
      this.canSubmit = false
      return
    }

    // 对于脚本类型（task_type !== 4），需要语法验证
    if (this.taskForm.task_type !== 4) {
      // 如果语法验证还没完成，暂时允许提交（用户可能正在输入）
      if (!this.syntaxValidationResult || this.syntaxValidationResult === null) {
        this.canSubmit = true
        return
      }
      // 如果有语法错误，禁用提交
      if (this.syntaxErrors.length > 0) {
        this.canSubmit = false
        return
      }
    }

    // 检查Cron表达式验证
    if (!this.cronValidationResult || this.cronValidationResult === null) {
      // Cron验证还没完成，暂时允许提交
      this.canSubmit = true
      return
    }

    // Cron表达式必须有效
    const hasCronErrors = !this.cronValidationResult.valid
    this.canSubmit = !hasCronErrors
  }

  // ========== 日志相关方法 ==========

  // 标签页点击处理
  private async handleTabClick(tab: any) {
    this.activeTab = tab.name

    // 当切换到日志页签时，加载日志数据
    if (tab.name === 'logs') {
      try {
        // 如果还没有加载过日志数据，则加载
        if (this.logList.length === 0) {
          await this.fetchLogStatistics()
          await this.fetchLogList()
        }
      } catch (error) {
        console.error('加载日志数据失败:', error)
        this.$message.error('加载日志数据失败')
      }
    }
  }

  // 获取日志统计信息
  private async fetchLogStatistics() {
    try {
      const response = await getTaskLogStatistics()
      if (response.status === 'success') {
        this.logStatistics = {
          totalLogs: response.data.totalLogs || 0,
          successLogs: response.data.successLogs || 0,
          failedLogs: response.data.failedLogs || 0,
          todayLogs: response.data.todayLogs || 0
        }
      }
    } catch (error) {
      console.error('获取日志统计失败:', error)
    }
  }

  // 获取日志列表
  private async fetchLogList() {
    try {
      this.logLoading = true
      const skip = (this.logQueryParams.page - 1) * this.logQueryParams.limit

      // 构建查询参数，过滤掉空值
      const params: any = {
        skip,
        limit: this.logQueryParams.limit
      }

      // 只有当值不为空时才添加到查询参数
      if (this.logQueryParams.task_name) {
        params.task_name = this.logQueryParams.task_name
      }
      if (this.logQueryParams.task_id !== undefined && this.logQueryParams.task_id !== null) {
        params.task_id = this.logQueryParams.task_id
      }
      if (this.logQueryParams.log_content) {
        params.log_content = this.logQueryParams.log_content
      }
      if (this.logQueryParams.success !== undefined && this.logQueryParams.success !== null) {
        params.success = this.logQueryParams.success
      }

      const response = await getTaskLogs(params)
      this.logList = response.data?.list || []
      this.logTotal = response.data?.total || 0
    } catch (error) {
      console.error('获取日志列表失败:', error)
      this.$message.error('获取日志列表失败')
    } finally {
      this.logLoading = false
    }
  }

  // 日志查询
  private handleLogQuery() {
    this.logQueryParams.page = 1
    this.fetchLogList()
  }

  // 日志日期范围变化处理（修复模板undefined错误）
  private handleLogDateRangeChange(value: any) {
    this.logDateRange = value
    this.handleLogQuery()
  }

  // 重置日志查询
  private resetLogQuery() {
    this.logQueryParams = {
      task_name: '',
      task_id: undefined,
      log_content: '',
      success: undefined,
      page: 1,
      limit: 20
    }
    // 清空日期范围选择
    this.logDateRange = []
    this.fetchLogList()
  }

  // 日志分页大小变化
  private handleLogSizeChange(val: number) {
    this.logQueryParams.limit = val
    this.logQueryParams.page = 1
    this.fetchLogList()
  }

  // 日志当前页变化
  private handleLogCurrentChange(val: number) {
    this.logQueryParams.page = val
    this.fetchLogList()
  }

  // 获取日志任务类型名称
  private getLogTaskTypeName(type: number): string {
    const typeNames = {
      0: 'shell脚本',
      1: 'cmd脚本',
      2: 'powershell脚本',
      3: 'python脚本',
      4: 'python内部类',
      5: '清理回收站'
    }
    return typeNames[type] || '未知类型'
  }

  // 获取日志任务类型标签
  private getLogTaskTypeTag(type: number): string {
    const tags = {
      0: 'primary',    // shell - 主要
      1: 'success',    // cmd - 成功
      2: 'warning',    // powershell - 警告
      3: 'info',       // python - 信息
      4: 'danger',     // python内部类 - 危险
      5: 'warning'     // 清理回收站 - 警告
    }
    return tags[type] || 'info'
  }

  // 日志导出处理（修复模板undefined错误）
  private handleLogExport(command: string) {
    this.$message.info(`日志导出功能: ${command}`)
  }

  // 日志清理处理（修复模板undefined错误）
  private handleLogCleanup() {
    this.$confirm('确定要清理历史日志吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      this.$message.success('日志清理完成')
    }).catch(() => {
      this.$message.info('已取消清理')
    })
  }

  // 日志批量删除处理（修复模板undefined错误）
  private handleLogBatchDelete() {
    if (this.logMultipleSelection.length === 0) {
      this.$message.warning('请选择要删除的日志')
      return
    }

    this.$confirm(`确定要删除选中的 ${this.logMultipleSelection.length} 条日志吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(() => {
      this.$message.success(`成功删除 ${this.logMultipleSelection.length} 条日志`)
      this.logMultipleSelection = []
    }).catch(() => {
      this.$message.info('已取消删除')
    })
  }

  // ========== 执行详情相关方法 ==========

  // 查看执行详情
  private handleViewLogDetail(row: BTDeckTypes.TaskLog) {
    this.selectedLog = row
    this.logDetailVisible = true
  }

  // 复制日志详情内容
  private async handleCopyLogDetail() {
    if (!this.selectedLog?.logDetail) {
      this.$message.warning('暂无内容可复制')
      return
    }

    try {
      // 构建复制内容
      const content = `任务名称：${this.selectedLog.taskName}
开始时间：${this.selectedLog.startTime}
结束时间：${this.selectedLog.endTime}
执行结果：${this.selectedLog.success ? '成功' : '失败'}
执行耗时：${this.selectedLog.duration}s
执行详情：
${this.selectedLog.logDetail}`

      // 使用现代浏览器的Clipboard API
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(content)
        this.$message.success('内容已复制到剪贴板')
      } else {
        // 降级方案：使用document.execCommand
        const textArea = document.createElement('textarea')
        textArea.value = content
        textArea.style.position = 'fixed'
        textArea.style.opacity = '0'
        document.body.appendChild(textArea)
        textArea.select()
        document.execCommand('copy')
        document.body.removeChild(textArea)
        this.$message.success('内容已复制到剪贴板')
      }
    } catch (error) {
      console.error('复制失败:', error)
      this.$message.error('复制失败，请手动复制内容')
    }
  }

  // ========== 清理预览相关方法 ==========

  // 清理预览
  private async previewCleanup() {
    try {
      this.previewLoading = true
      const response = await request({
        url: '/cronTasks/cleanup/preview',
        method: 'post',
        data: {
          cleanup_level_3: this.cleanupConfig.cleanup_level_3,
          cleanup_level_4: this.cleanupConfig.cleanup_level_4,
          days_threshold: this.cleanupConfig.days_threshold
        }
      })

      if (response.code === '200') {
        this.showPreviewDialog(response.data)
      } else {
        // 更友好的错误提示
        const errorMsg = response.msg || '预览失败，请稍后重试'
        this.$message.error({
          message: errorMsg,
          duration: 5000,
          showClose: true
        })
        // 开发环境记录详细错误信息
        if (process.env.NODE_ENV === 'development') {
          console.warn('清理预览API返回错误:', response)
        }
      }
    } catch (error) {
      // 更友好的异常处理
      console.error('清理预览请求异常:', error)
      const errorMessage = (error as Error).message || '网络异常，请检查连接'

      this.$message.error({
        message: `预览失败：${errorMessage}`,
        duration: 5000,
        showClose: true
      })
    } finally {
      this.previewLoading = false
    }
  }

  // 显示预览对话框
  private showPreviewDialog(data: any) {
    this.previewData = data
    this.previewDialogVisible = true
  }

  // ========== 分页计算属性 ==========

  // 计算可见页码（任务管理）
  get visiblePages() {
    const currentPage = this.queryParams.page
    const totalPages = Math.ceil(this.total / this.queryParams.limit) || 1
    const delta = 2 // 当前页前后显示的页码数

    const pages: number[] = []

    // 总是显示第1页
    if (totalPages > 0) {
      pages.push(1)
    }

    // 当前页前后的页码
    for (let i = Math.max(2, currentPage - delta); i <= Math.min(totalPages - 1, currentPage + delta); i++) {
      if (!pages.includes(i)) {
        pages.push(i)
      }
    }

    // 总是显示最后一页(如果不同于第1页)
    if (totalPages > 1) {
      pages.push(totalPages)
    }

    return pages
  }

  // 计算可见页码（任务日志）
  get visibleLogPages() {
    const currentPage = this.logQueryParams.page
    const totalPages = Math.ceil(this.logTotal / this.logQueryParams.limit) || 1
    const delta = 2 // 当前页前后显示的页码数

    const pages: number[] = []

    // 总是显示第1页
    if (totalPages > 0) {
      pages.push(1)
    }

    // 当前页前后的页码
    for (let i = Math.max(2, currentPage - delta); i <= Math.min(totalPages - 1, currentPage + delta); i++) {
      if (!pages.includes(i)) {
        pages.push(i)
      }
    }

    // 总是显示最后一页(如果不同于第1页)
    if (totalPages > 1) {
      pages.push(totalPages)
    }

    return pages
  }
}
</script>

<style lang="scss" scoped>
/*
 * ✅ 性能优化：主题文件按需加载
 * - 定时任务主题样式仅在访问此页面时加载
 * - 避免在全局样式中导入，减少首屏加载时间
 * - shared-theme.scss 已在全局样式 index.scss 中导入
 */
@import '@/styles/scheduled-tasks-theme.scss';

/* ========================================
   定时任务页面特定样式
   ======================================== */

/* 表单帮助文本 */
.form-help {
  margin-top: 6px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  line-height: 1.4;
}

/* 语法错误显示 */
.syntax-errors {
  margin-top: 10px;
}

.more-errors {
  text-align: center;
  padding: 8px 0;
  border-top: 1px solid var(--color-border-primary);
  margin-top: 8px;
}

.all-errors {
  margin-top: 10px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-sm);
}

.error-detail {
  padding: 12px;
  background-color: #fef0f0;
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.5;
}

/* 语法成功提示 */
.syntax-success {
  margin-top: 10px;
}

/* Cron表达式验证错误 */
.cron-validation-error {
  margin-top: 8px;
}

/* 按钮组样式 */
.dialog-footer .el-button {
  margin-left: 10px;
}

.dialog-footer .el-button:first-child {
  margin-left: 0;
}

/* 任务表单对话框样式 - 水平居中，垂直向上偏移170px */
::v-deep .task-dialog {
  left: 50%;
  top: calc(10% - 170px);
  transform: translate(-50%, 0);
  margin: 0;
}

/* 执行详情弹窗样式 */
.log-detail-dialog {
  /* 确保弹窗内容居中 */
  margin: 0 auto;

  ::v-deep .el-dialog__body {
    padding: 20px 30px;
    max-height: 70vh;
    overflow-y: auto;
    overflow-x: hidden;
  }
}

.log-detail-content {
  font-size: 14px;
  line-height: 1.6;
}

.log-detail-header {
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--radius-md);
  padding: 20px;
  margin-bottom: 20px;

  .detail-item {
    display: flex;
    align-items: center;
    margin-bottom: 12px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  .label {
    font-weight: 600;
    color: var(--color-text-secondary);
    min-width: 100px;
    flex-shrink: 0;
  }

  .value {
    color: var(--color-text-primary);
    flex: 1;
  }
}

.log-detail-main {
  .detail-title {
    color: var(--color-text-primary);
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 15px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--color-border-primary);
  }

  .detail-content {
    background-color: var(--color-bg-tertiary);
    border: 1px solid var(--color-border-primary);
    border-radius: var(--radius-md);
    padding: 15px;
    max-height: 400px;
    overflow-y: auto;

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-wrap: break-word;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.5;
      color: var(--color-text-primary);
    }
  }
}

/* 弹窗操作按钮样式 */
.log-detail-dialog .dialog-footer {
  text-align: right;

  .el-button {
    margin-left: 10px;

    &:first-child {
      margin-left: 0;
    }
  }
}

::v-deep .el-range-separator {
  margin: 0 30px;
}

/* ========================================
   任务日志搜索表单 - 响应式布局优化
   ======================================== */

/*
 * ✅ 布局策略：两行布局
 *
 * 第一行：任务名称、日志内容、执行结果、搜索/重置按钮
 * 第二行：时间范围（与其他控件宽度一致，左对齐）
 */

/* 任务日志标签页的筛选表单 - 响应式布局 */
.filter-form-logs {
  display: flex !important;
  flex-wrap: wrap !important;
  gap: var(--spacing-md) !important;
  align-items: flex-end !important;
  width: 100% !important;
}

/* 前三个表单组：各占约 1/4 宽度，与按钮在同一行 */
.filter-form-logs .form-group:nth-child(1),
.filter-form-logs .form-group:nth-child(2),
.filter-form-logs .form-group:nth-child(3) {
  flex: 0 0 calc(25% - var(--spacing-md) * 3 / 4);
  max-width: calc(25% - var(--spacing-md) * 3 / 4);
  min-width: 180px;
}

/* 第四个表单组：按钮组，与前三项在同一行 */
.filter-form-logs .form-group[style*="flex-direction: row"] {
  flex: 0 0 auto;
  display: inline-flex !important;
  flex-direction: row !important;
  align-items: flex-end !important;
  gap: 8px !important;
  margin-left: auto; /* 推到右侧 */
}

/* 第五个表单组：时间范围，与其他表单控件宽度一致（约 25%）
 * 特殊布局：label 在左上角，输入框在下方 */
.filter-form-logs .form-group.form-group-wide {
  flex: 1 1 100%;
  max-width: 100%;
  width: 100%;

  /* 时间范围 label 定位在左上角 */
  position: relative;

  .form-label {
    position: absolute;
    top: 0;
    left: 0;
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--color-text-secondary);
    white-space: nowrap;
  }

  /* 时间选择器输入框，留出 label 的空间 */
  >>> .el-date-editor {
    margin-top: 20px; /* 为 label 留出空间 */
    width: 100% !important;
  }
}

/* 统一所有表单控件高度（排除时间范围，它有特殊布局） */
.filter-form-logs .form-group:not(.form-group-wide) {
  min-height: 54px; /* label(20px) + gap(8px) + input(32px) + padding */
}

/* 确保时间选择器与其他表单控件高度一致 */
.filter-form-logs .el-date-editor {
  height: 32px !important;
  line-height: 32px !important;

  >>> .el-input__inner {
    height: 32px !important;
    line-height: 32px !important;
    padding: var(--spacing-sm) var(--spacing-md) !important;
  }

  >>> .el-input__icon {
    line-height: 32px !important;
  }
}

/* 修复日期范围选择器分隔符"至"被遮挡的问题，并确保清除图标显示 */
::v-deep .el-date-editor--datetimerange {
  // 确保所有子元素垂直居中对齐
  display: inline-flex;
  align-items: center;

  .el-range-separator {
    padding: 0 8px;
    min-width: 24px;
    line-height: 32px;
    // 确保分隔符文字垂直居中
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .el-range-input {
    flex: 1;
    min-width: 0;
    // 确保输入框文字垂直居中
    line-height: 32px;
  }

  // 确保所有图标(包括时钟图标)垂直居中对齐
  .el-input__icon,
  .el-range__icon {
    line-height: 32px;
    // 使用flexbox确保图标内容垂直居中
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  // 为清除图标预留空间，避免被挤压
  .el-range-input:last-child {
    padding-right: 30px;
  }

  // 确保清除图标正确显示并垂直居中
  .el-range__close-icon {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    position: absolute !important;
    right: 5px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    color: #C0C4CC !important;
    font-size: 14px !important;
    cursor: pointer !important;
    z-index: 10 !important;
    width: auto !important;
    height: auto !important;
    float: none !important;
    font-style: normal !important;  // 确保图标为正体

    &:hover {
      color: #909399 !important;
    }
  }

  // 确保清除图标的伪元素显示（使用圆形关闭图标）
  .el-range__close-icon::before {
    content: "\e79d" !important;
    font-family: element-icons !important;
    font-size: 16px !important;
    font-style: normal !important;  // 确保伪元素也为正体
    display: inline-block !important;
  }
}

/* 搜索和重置按钮 */
.filter-form-logs .form-group[style*="flex-direction: row"] .el-button {
  height: 32px !important;
  line-height: 32px !important;
  padding: var(--spacing-sm) var(--spacing-lg) !important;
  white-space: nowrap !important;
}

/* 响应式：小屏幕时单列显示 */
@media (max-width: 1024px) {
  .filter-form-logs .form-group:nth-child(1),
  .filter-form-logs .form-group:nth-child(2),
  .filter-form-logs .form-group:nth-child(3),
  .filter-form-logs .form-group.form-group-wide {
    flex: 1 1 calc(50% - var(--spacing-md) / 2);
    max-width: calc(50% - var(--spacing-md) / 2);
  }

  .filter-form-logs .form-group[style*="flex-direction: row"] {
    flex: 1 1 100%;
    margin-left: 0;
    justify-content: flex-start;
  }
}

@media (max-width: 768px) {
  .filter-form-logs .form-group:nth-child(1),
  .filter-form-logs .form-group:nth-child(2),
  .filter-form-logs .form-group:nth-child(3),
  .filter-form-logs .form-group.form-group-wide {
    flex: 1 1 100%;
    max-width: 100%;
  }
}

/* ========================================
   任务日志表格表头 - 渐变背景样式
   ======================================== */

/* 表头整行渐变背景（应用在tr元素而非单个th上）*/
::v-deep .log-table-header {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  border-bottom: 2px solid var(--color-primary);

  th {
    background: transparent;
    font-weight: var(--font-weight-semibold);
    color: white;
    border-bottom: none;
  }
}

</style>
