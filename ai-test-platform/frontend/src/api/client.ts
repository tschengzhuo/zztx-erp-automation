import axios from 'axios';
import { message } from 'antd';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 分钟（LLM 调用较慢）
});

// 响应拦截
api.interceptors.response.use(
  (response) => {
    // 自动解包 APIResponse: { success, message, data } → data
    const body = response.data;
    if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
      response.data = body.data;
    }
    return response;
  },
  (error) => {
    const msg = error.response?.data?.message || error.message || '请求失败';
    message.error(msg);
    return Promise.reject(error);
  }
);

export default api;

// ==================== 需求 API ====================

export const requirementApi = {
  create: (data: { title: string; module: string; raw_text: string; source?: string }) =>
    api.post('/requirements/', data),

  upload: (file: File, module: string) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/requirements/upload?module=${encodeURIComponent(module)}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  list: (params?: { module?: string; status?: string; page?: number; page_size?: number }) =>
    api.get('/requirements/', { params }),

  get: (id: string) => api.get(`/requirements/${id}`),

  update: (id: string, data: { title?: string; raw_text?: string }) =>
    api.put(`/requirements/${id}`, data),

  parse: (id: string) => api.post(`/requirements/${id}/parse`),

  delete: (id: string) => api.delete(`/requirements/${id}`),
};

// ==================== 测试点 API ====================

export const testPointApi = {
  generate: (requirement_id: string, max_points: number = 30) =>
    api.post('/test-points/generate', { requirement_id, max_points }),

  listByRequirement: (requirement_id: string, confirmed_only: boolean = false) =>
    api.get(`/test-points/by-requirement/${requirement_id}`, { params: { confirmed_only } }),

  update: (id: string, data: any) => api.put(`/test-points/${id}`, data),

  confirm: (confirmed_ids: string[], deleted_ids: string[] = []) =>
    api.post('/test-points/confirm', { confirmed_ids, deleted_ids }),
};

// ==================== 用例 API ====================

export const testCaseApi = {
  generate: (requirement_id: string, test_point_ids: string[], generate_both: boolean = true) =>
    api.post('/test-cases/generate', { requirement_id, test_point_ids, generate_both }),

  listByRequirement: (requirement_id: string, case_type?: string) =>
    api.get(`/test-cases/by-requirement/${requirement_id}`, { params: { case_type } }),

  get: (id: string) => api.get(`/test-cases/${id}`),

  update: (id: string, data: any) => api.put(`/test-cases/${id}`, data),

  confirm: (id: string) => api.post(`/test-cases/${id}/confirm`),

  lockStep: (caseId: string, stepIndex: number) =>
    api.post(`/test-cases/${caseId}/lock-step`, null, { params: { step_index: stepIndex } }),

  export: (requirement_id: string, format: string) =>
    api.post('/test-cases/export', { requirement_id, format }, { responseType: 'blob' }),
};

// ==================== 实体 API ====================

export const entityApi = {
  list: (params?: { entity_type?: string; module?: string }) =>
    api.get('/entities/', { params }),

  create: (data: any) => api.post('/entities/', data),

  batchImportSwagger: (module: string, swaggerJson: any) =>
    api.post('/entities/batch-import/swagger', null, { params: { module }, data: swaggerJson }),
};

// ==================== 平台统计 ====================

export const platformApi = {
  health: () => api.get('/health'),
  stats: () => api.get('/stats'),
};
