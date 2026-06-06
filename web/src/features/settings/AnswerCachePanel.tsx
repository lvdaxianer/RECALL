/**
 * Recall · 答案缓存管理面板
 *
 * 顶部：刷新按钮 + 加载/错误态；表格列出答案缓存条目。
 * 每行展示归一化问题、答案预览、命中次数、信任分数、过期时间、操作按钮。
 *
 * 设计要点：
 * 1. 加载用 listAnswerCache（不轮询，按需 reload）
 * 2. 删除走 cache_key（URL 编码防特殊字符）
 * 3. 删除成功就地从 items 里过滤掉，UI 立即反映
 * 4. message Alert 统一展示"缓存已删除" / "删除失败"
 * 5. 空数据走 Alert 提示文案（区别于 ErrorState 的加载失败）
 * 6. 表格横向滚动，移动端不至于被截断
 *
 * @author lvdaxianerplus
 */
import { deleteAnswerCache, listAnswerCache, type AnswerCacheRecord } from "../../api/retrieval";
import { ErrorState } from "../../components/common/ErrorState";
import { LoadingState } from "../../components/common/LoadingState";
import { Alert, AlertDescription } from "../../components/ui/alert";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "../../components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";

/**
 * 答案缓存面板 props。
 *
 * @author lvdaxianerplus
 */
export interface AnswerCachePanelProps {
  // 当前为占位预留：将来可接入全局权限 / 路由。
}

/**
 * 把 ISO 时间戳格式化为中文短日期。
 *
 * @param value ISO 字符串
 * @returns 形如 `04-15 14:30`，无法解析时回退到原值
 * @author lvdaxianerplus
 */
function formatDate(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

/**
 * 答案缓存管理面板。
 *
 * @author lvdaxianerplus
 */
export function AnswerCachePanel(_props: AnswerCachePanelProps = {}) {
  const [items, setItems] = useState<AnswerCacheRecord[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void load();
  }, []);

  /**
   * 加载答案缓存列表。
   *
   * @author lvdaxianerplus
   */
  async function load(): Promise<void> {
    setStatus("loading");
    setMessage("");
    try {
      const response = await listAnswerCache();
      setItems(Array.isArray(response.items) ? response.items : []);
      setStatus("success");
    } catch {
      setStatus("error");
      setMessage("加载答案缓存失败");
    }
  }

  /**
   * 删除指定答案缓存。失败时通过 message 提示用户。
   *
   * @param item 目标缓存条目
   * @author lvdaxianerplus
   */
  async function handleDelete(item: AnswerCacheRecord): Promise<void> {
    setMessage("");
    try {
      await deleteAnswerCache(item.cache_key);
      setItems((current) => current.filter((record) => record.cache_key !== item.cache_key));
      setMessage("缓存已删除");
    } catch {
      setMessage("删除失败");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 border-b border-slate-200">
        <div>
          <CardDescription>Answer Cache</CardDescription>
          <h3 className="text-lg font-semibold text-slate-900">答案缓存管理</h3>
          <p className="mt-2 text-sm text-slate-500">
            查看已沉淀的问答缓存、信任权重和命中次数，必要时手动删除缓存。
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => void load()}>
          刷新
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 pt-6">
        {status === "loading" ? <LoadingState label="加载答案缓存中" /> : null}
        {status === "error" ? <ErrorState title="答案缓存加载失败" onRetry={() => void load()} /> : null}
        {message ? (
          <Alert>
            <AlertDescription>{message}</AlertDescription>
          </Alert>
        ) : null}
        {status === "success" && items.length === 0 ? (
          <Alert>
            <AlertDescription>
              暂无答案缓存。当聊天问答成功生成后，相同归一化问题会在这里沉淀为可复用缓存。
            </AlertDescription>
          </Alert>
        ) : null}
        <div className="overflow-x-auto">
          <Table aria-label="答案缓存">
            <TableHeader>
              <TableRow>
                <TableHead>归一化问题</TableHead>
                <TableHead>答案预览</TableHead>
                <TableHead>指标</TableHead>
                <TableHead>过期时间</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length > 0 ? (
                items.map((item) => (
                  <TableRow key={item.cache_key}>
                    <TableCell>
                      <strong className="text-sm font-medium text-slate-900">{item.normalized_query}</strong>
                      <small className="block text-xs text-slate-500">
                        {item.knowledge_base_ids.length} 个知识库 · {item.citation_count} 条引用
                      </small>
                    </TableCell>
                    <TableCell className="text-slate-700">{item.answer_preview}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <span className="inline-flex h-[22px] items-center rounded bg-slate-100 px-2 font-mono text-xs text-slate-700">
                          命中 {item.hit_count} 次
                        </span>
                        <span className="inline-flex h-[22px] items-center rounded bg-emerald-50 px-2 font-mono text-xs text-emerald-700">
                          信任 {item.trust_score}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-slate-500">{formatDate(item.expires_at)}</TableCell>
                    <TableCell>
                      <Button
                        aria-label={`删除缓存 ${item.normalized_query}`}
                        size="sm"
                        type="button"
                        variant="destructive"
                        onClick={() => void handleDelete(item)}
                      >
                        删除
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell className="text-slate-500" colSpan={5}>
                    暂无答案缓存
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

// 在本文件内 import useEffect / useState 以减小外部依赖关系
import { useEffect, useState } from "react";
