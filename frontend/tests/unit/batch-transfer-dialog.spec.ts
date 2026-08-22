import { shallowMount, createLocalVue } from '@vue/test-utils'
import BatchTransferDialog from '@/views/torrents/components/BatchTransferDialog.vue'
import { transferSeedsBatch } from '@/api/torrents'
import { ApiError } from '@/types/api'

/**
 * 批量转移失败语义回归（verified-bugfix-remediation W5-3）：
 * - 后端部分/全部失败返回 code=400（HTTP 200，被拦截器转为 rejected Promise）
 *   时，从 ApiError.rawResponse 取 results 展示失败明细弹窗
 * - 部分失败时 handleResultConfirm 不 emit success（不提示"完成"）
 * - 全部成功时正常 emit success
 */

jest.mock('@/api/torrents', () => ({
  transferSeedsBatch: jest.fn(),
  getDownloaderList: jest.fn(),
  getDownloaderPaths: jest.fn(),
  deleteTorrents: jest.fn()
}))

jest.mock('element-ui', () => ({
  Message: { success: jest.fn(), error: jest.fn() }
}))

const localVue = createLocalVue()

const makeWrapper = () => {
  const wrapper = shallowMount(BatchTransferDialog, {
    localVue,
    mocks: {
      $message: { success: jest.fn(), error: jest.fn() },
      $loading: jest.fn(() => ({ close: jest.fn() })),
      $confirm: jest.fn(() => Promise.resolve())
    },
    propsData: {
      visible: true,
      torrents: [
        {
          hash: 'a'.repeat(40),
          infoId: 't1',
          downloaderId: 'd1',
          name: '测试种子',
          downloaderName: '源下载器',
          savePath: '/downloads/source'
        }
      ]
    }
  })
  const vm = wrapper.vm as any
  vm.dialogVisible = true
  vm.formData = { target_downloader_id: 'd2', target_path: '/downloads/movies' }
  return wrapper
}

describe('BatchTransferDialog 批量转移失败语义', () => {
  afterEach(() => {
    jest.clearAllMocks()
  })

  it('code=400（ApiError）时从 rawResponse 取 results 并打开失败明细弹窗', async() => {
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any

    const payload = {
      total_count: 2,
      success_count: 1,
      failed_count: 1,
      results: [
        { success: true, transfer_status: 'success', info_hash: 'a'.repeat(40) },
        { success: false, transfer_status: 'failed', info_hash: 'b'.repeat(40), error_message: '备份未找到' }
      ]
    }
    ;(transferSeedsBatch as jest.Mock).mockRejectedValue(
      new ApiError('批量转移完成：成功1个，失败1个', {
        code: '400',
        httpStatus: 200,
        rawResponse: { data: { data: payload } }
      })
    )

    await vm.executeBatchTransfer()

    expect(vm.batchResult).toEqual(payload)
    expect(vm.dialogVisible).toBe(false)
    expect(vm.resultDialogVisible).toBe(true)
    expect(vm.submitting).toBe(false)
  })

  it('部分失败时 handleResultConfirm 不 emit success', async() => {
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any

    vm.batchResult = {
      total_count: 2,
      success_count: 1,
      failed_count: 1,
      results: [
        { success: true },
        { success: false, error_message: 'x' }
      ]
    }
    vm.resultDialogVisible = true

    await vm.handleResultConfirm()

    expect(wrapper.emitted('success')).toBeUndefined()
    expect(vm.resultDialogVisible).toBe(false)
  })

  it('全部成功时 handleResultConfirm 正常 emit success', async() => {
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any

    vm.batchResult = {
      total_count: 1,
      success_count: 1,
      failed_count: 0,
      results: [{ success: true }]
    }
    vm.resultDialogVisible = true
    vm.formData.delete_source = false

    await vm.handleResultConfirm()

    expect(wrapper.emitted('success')).toHaveLength(1)
  })

  it('删除源种子失败时不 emit success', async() => {
    const wrapper = makeWrapper()
    const vm = wrapper.vm as any

    vm.batchResult = {
      total_count: 1,
      success_count: 1,
      failed_count: 0,
      results: [{ success: true }]
    }
    vm.resultDialogVisible = true
    vm.formData.delete_source = true
    const { deleteTorrents } = require('@/api/torrents')
    ;(deleteTorrents as jest.Mock).mockRejectedValue(new Error('delete failed'))

    await vm.handleResultConfirm()

    expect(wrapper.emitted('success')).toBeUndefined()
  })
})
