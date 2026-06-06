import { Alert, AlertDescription } from "../../components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader } from "../../components/ui/card";
import type { SettingsItem } from "./settingsSections";

/**
 * 预留设置项占位面板。
 *
 * @author lvdaxianerplus
 */
export interface SettingsPlaceholderProps {
  section: SettingsItem;
}

/**
 * 占位面板：当某设置模块尚未实现时展示的占位卡片。
 *
 * @param props.section 设置项元信息
 * @author lvdaxianerplus
 */
export function SettingsPlaceholder({ section }: SettingsPlaceholderProps) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>Reserved</CardDescription>
        <h3 className="text-lg font-semibold text-slate-900">{section.label}</h3>
        <p className="text-sm text-slate-500">{section.summary}</p>
      </CardHeader>
      <CardContent>
        <Alert>
          <AlertDescription>
            <strong className="block text-slate-900">该设置模块已预留，后续接入真实配置。</strong>
            当前版本先开放答案缓存管理，避免半成品配置影响线上检索链路。
          </AlertDescription>
        </Alert>
      </CardContent>
    </Card>
  );
}
