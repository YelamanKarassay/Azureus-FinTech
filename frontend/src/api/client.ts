const BASE_URL = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly statusText: string
  readonly path: string

  constructor(status: number, statusText: string, path: string) {
    super(`API ${path} failed: ${status} ${statusText}`)
    this.name = 'ApiError'
    this.status = status
    this.statusText = statusText
    this.path = path
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init)
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText, path)
  }
  return response.json() as Promise<T>
}
