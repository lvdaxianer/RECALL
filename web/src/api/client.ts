/**
 * Recall · 通用 API 客户端
 *
 * 集中封装 fetch + JSON 解析 + 错误抛出，所有 api/* 模块都通过本文件发起请求。
 * 这样上游只需要 import { requestJson } 即可，省去每个模块重复 fetch / 状态码判断。
 *
 * @author lvdaxianerplus
 */

/**
 * API 错误：携带 HTTP 状态码，供 UI 决定是否提示重试 / 401 跳转等。
 *
 * @author lvdaxianerplus
 */
export class ApiError extends Error {
  /** HTTP 状态码（4xx / 5xx） */
  status: number;

  /**
   * @param message 错误消息
   * @param status  HTTP 状态码
   * @author lvdaxianerplus
   */
  constructor(message: string, status: number) {
    super(message);
    // 显式赋值，让 TS 把字段也写入实例
    this.status = status;
  }
}

/**
 * 发起 fetch 请求并解析 JSON 响应。
 *
 * @param url  请求 URL
 * @param init fetch 选项
 * @returns 解析后的 JSON payload
 * @throws {ApiError} 当 response.ok 为 false 时抛出
 * @author lvdaxianerplus
 */
export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  // 1. 发起请求
  const response = await fetch(url, init);
  // 2. 非 2xx 响应直接抛 ApiError
  if (!response.ok) {
    throw new ApiError("请求失败", response.status);
  }
  // 3. 解析 JSON（调用方负责类型断言）
  return response.json() as Promise<T>;
}
