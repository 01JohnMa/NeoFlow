import { Link } from 'react-router-dom'
import { useDocumentList } from '@/hooks/useDocuments'
import { useProfile } from '@/hooks/useProfile'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/spinner'
import { getStatusColor, getStatusText, formatDate } from '@/lib/utils'
import {
  FileText,
  Upload,
  CheckCircle,
  Clock,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  Building2,
  ClipboardList,
  Package,
  TestTube,
} from 'lucide-react'

// 辅助函数：获取模板图标
function getTemplateIcon(code: string) {
  const iconClass = "h-5 w-5"
  switch (code) {
    case 'inspection_report':
      return <TestTube className={`${iconClass} text-primary-400`} />
    case 'express':
      return <Package className={`${iconClass} text-accent-400`} />
    case 'sampling':
      return <ClipboardList className={`${iconClass} text-success-400`} />
    default:
      return <FileText className={`${iconClass} text-primary-400`} />
  }
}

// 辅助函数：获取模板渐变色
function getTemplateGradient(index: number) {
  const gradients = [
    'from-primary-900/50 to-primary-800/30 border-primary-500',
    'from-accent-900/50 to-accent-800/30 border-accent-500',
    'from-success-900/50 to-success-800/30 border-success-500',
    'from-yellow-900/50 to-yellow-800/30 border-yellow-500',
  ]
  return gradients[index % gradients.length]
}

// 辅助函数：获取模板描述
function getTemplateDescription(code: string) {
  switch (code) {
    case 'inspection_report':
      return '自动提取检测项目、结论等关键信息'
    case 'express':
      return '快速提取运单号、收发件人信息'
    case 'sampling':
      return '自动识别抽样单位、产品信息'
    default:
      return '智能识别文档关键信息'
  }
}

export function Dashboard() {
  const { data: documents, isLoading } = useDocumentList({ limit: 5 })
  const { templates, tenantName, displayName, isLoading: profileLoading } = useProfile()

  // Calculate stats
  const stats = {
    total: documents?.total || 0,
    completed: documents?.items.filter((d) => d.status === 'completed').length || 0,
    processing: documents?.items.filter((d) => d.status === 'queued' || d.status === 'processing').length || 0,
    failed: documents?.items.filter((d) => d.status === 'failed').length || 0,
  }

  const statCards = [
    {
      title: '总文档数',
      value: stats.total,
      icon: FileText,
      color: 'text-primary-400',
      bgColor: 'bg-primary-400/10',
    },
    {
      title: '已完成（最近 5 条）',
      value: stats.completed,
      icon: CheckCircle,
      color: 'text-success-500',
      bgColor: 'bg-success-500/10',
    },
    {
      title: '处理中（最近 5 条）',
      value: stats.processing,
      icon: Clock,
      color: 'text-accent-400',
      bgColor: 'bg-accent-400/10',
    },
    {
      title: '失败（最近 5 条）',
      value: stats.failed,
      icon: AlertTriangle,
      color: 'text-error-500',
      bgColor: 'bg-error-500/10',
    },
  ]

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Welcome Section */}
      <section className="relative overflow-hidden rounded-2xl border border-border-default bg-bg-card px-6 py-7 md:px-8">
        <div className="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-primary-500/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-primary-300">Workspace overview</p>
          <h2 className="text-3xl font-semibold tracking-tight text-text-primary">
            {displayName ? `${displayName}，` : ''}欢迎使用 NeoFlow
          </h2>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <p className="text-sm text-text-secondary">
              快速识别和提取文档关键信息
            </p>
            {tenantName && (
              <Badge variant="secondary" className="gap-1">
                <Building2 className="h-3 w-3" />
                {tenantName}
              </Badge>
            )}
          </div>
        </div>
        <Link to="/upload" className="shrink-0">
          <Button size="lg" className="gap-2">
            <Upload className="h-4 w-4" />
            上传新文档
          </Button>
        </Link>
        </div>
      </section>

      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">Activity</p>
          <h3 className="mt-1 text-lg font-semibold text-text-primary">处理概览</h3>
        </div>
        <Link to="/documents" className="text-sm font-medium text-primary-300 transition-colors hover:text-primary-200">
          查看全部文档 <ArrowRight className="ml-1 inline h-4 w-4" />
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map((stat, index) => (
          <Card
            key={stat.title}
            className={`group animate-slideInUp stagger-${index + 1} transition-colors hover:border-primary-500/40`}
            style={{ animationFillMode: 'both' }}
          >
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{stat.title}</p>
                  <p className="mt-3 text-3xl font-semibold tracking-tight text-text-primary">{stat.value}</p>
                </div>
                <div className={`flex h-10 w-10 items-center justify-center rounded-xl border border-white/5 ${stat.bgColor}`}>
                  <stat.icon className={`h-5 w-5 ${stat.color}`} />
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent Documents */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary-400" />
            最近文档
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : documents?.items.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-text-muted mx-auto mb-4" />
              <p className="text-text-secondary">暂无文档</p>
              <Link to="/upload" className="mt-4 inline-block">
                <Button variant="outline" size="sm">
                  上传第一个文档
                </Button>
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {documents?.items.map((doc) => (
                <Link
                  key={doc.id}
                  to={`/documents/${doc.id}`}
                  className="group flex items-center justify-between rounded-xl border border-transparent bg-bg-secondary/70 p-4 transition-colors hover:border-primary-500/30 hover:bg-bg-hover"
                >
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-lg bg-primary-500/10 flex items-center justify-center">
                      <FileText className="h-5 w-5 text-primary-400" />
                    </div>
                    <div>
                      <p className="max-w-[200px] truncate font-medium text-text-primary transition-colors group-hover:text-primary-200 md:max-w-[300px]">
                        {doc.original_file_name || doc.file_name}
                      </p>
                      <p className="text-sm text-text-muted">{formatDate(doc.created_at)}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {doc.document_type && (
                      <Badge variant="secondary">{doc.document_type}</Badge>
                    )}
                    <Badge className={getStatusColor(doc.status)}>
                      {getStatusText(doc.status)}
                    </Badge>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick Actions - 根据模板动态渲染 */}
      <div>
        <div className="mb-4 flex items-end justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.18em] text-text-muted">Start here</p>
            <h3 className="mt-1 text-lg font-semibold text-text-primary">快速开始</h3>
          </div>
          <span className="hidden text-xs text-text-muted sm:block">选择一个配置开始处理</span>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {templates.length > 0 ? (
          // 显示用户租户的模板
          templates.slice(0, 3).map((template, index) => (
            <Card 
              key={template.id}
              className={`bg-gradient-to-br ${getTemplateGradient(index)} border-opacity-20`}
            >
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 mb-2">
                  {getTemplateIcon(template.code)}
                  <h3 className="font-semibold text-text-primary">{template.name}</h3>
                </div>
                <p className="text-sm text-text-secondary mb-4">
                  {template.description || getTemplateDescription(template.code)}
                </p>
                <Link to="/upload">
                  <Button size="sm" variant="secondary">开始识别</Button>
                </Link>
              </CardContent>
            </Card>
          ))
        ) : profileLoading ? (
          // 加载中
          <Card className="col-span-3 flex items-center justify-center py-12">
            <Spinner />
          </Card>
        ) : (
          // 默认卡片（未选择部门或无模板）
          <>
            <Card className="bg-gradient-to-br from-primary-900/50 to-primary-800/30 border-primary-500/20">
              <CardContent className="pt-6">
                <h3 className="font-semibold text-text-primary mb-2">检验报告识别</h3>
                <p className="text-sm text-text-secondary mb-4">
                  自动提取检测项目、结论等关键信息
                </p>
                <Link to="/upload">
                  <Button size="sm" variant="secondary">开始识别</Button>
                </Link>
              </CardContent>
            </Card>
            <Card className="bg-gradient-to-br from-accent-900/50 to-accent-800/30 border-accent-500/20">
              <CardContent className="pt-6">
                <h3 className="font-semibold text-text-primary mb-2">快递单识别</h3>
                <p className="text-sm text-text-secondary mb-4">
                  快速提取运单号、收发件人信息
                </p>
                <Link to="/upload">
                  <Button size="sm" variant="secondary">开始识别</Button>
                </Link>
              </CardContent>
            </Card>
            <Card className="bg-gradient-to-br from-success-900/50 to-success-800/30 border-success-500/20">
              <CardContent className="pt-6">
                <h3 className="font-semibold text-text-primary mb-2">抽样单识别</h3>
                <p className="text-sm text-text-secondary mb-4">
                  自动识别抽样单位、产品信息
                </p>
                <Link to="/upload">
                  <Button size="sm" variant="secondary">开始识别</Button>
                </Link>
              </CardContent>
            </Card>
          </>
        )}
        </div>
      </div>
    </div>
  )
}

