import { useState, useMemo, useCallback } from "react"

interface UsePaginationOptions<T> {
  data: T[]
  pageSize?: number
  initialPage?: number
}

interface UsePaginationReturn<T> {
  page: number
  totalPages: number
  totalItems: number
  pageSize: number
  pageData: T[]
  setPage: (page: number) => void
  nextPage: () => void
  prevPage: () => void
  firstPage: () => void
  lastPage: () => void
  hasNext: boolean
  hasPrev: boolean
}

export function usePagination<T>({
  data,
  pageSize = 20,
  initialPage = 1,
}: UsePaginationOptions<T>): UsePaginationReturn<T> {
  const [page, setPage] = useState(initialPage)
  const totalItems = data.length
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))

  const safePage = Math.min(Math.max(1, page), totalPages)
  if (safePage !== page) setPage(safePage)

  const pageData = useMemo(() => {
    const start = (safePage - 1) * pageSize
    return data.slice(start, start + pageSize)
  }, [data, safePage, pageSize])

  const nextPage = useCallback(() => setPage((p) => Math.min(p + 1, totalPages)), [totalPages])
  const prevPage = useCallback(() => setPage((p) => Math.max(p - 1, 1)), [])
  const firstPage = useCallback(() => setPage(1), [])
  const lastPage = useCallback(() => setPage(totalPages), [totalPages])

  return {
    page: safePage,
    totalPages,
    totalItems,
    pageSize,
    pageData,
    setPage,
    nextPage,
    prevPage,
    firstPage,
    lastPage,
    hasNext: safePage < totalPages,
    hasPrev: safePage > 1,
  }
}
