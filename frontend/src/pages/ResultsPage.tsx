import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useJob } from '@/features/jobs/useJob'
import { restoreSubmission } from '@/features/jobs/submission'
import { Activity, Download, Fingerprint } from 'lucide-react'
import { PageHeading } from '@/components/PageHeading'
import { StatusPanel } from '@/components/StatusPanel'
import { useResources } from '@/features/resources/context'
const states: Record<string, string> = {
  awaiting_visual_review: '技术完成 · 待人工审核',
  failed: '失败',
  interrupted: '中断',
  unknown: '证据不可核验',
  created: '已创建',
  preparing: '准备中',
  rendering: '渲染中',
  encoding: '编码中',
}
export function ResultsPage() {
  const r = useResources()
  const [query, setQuery] = useSearchParams()
  const pending = restoreSubmission()
  const scene = query.get('scene') ?? pending?.payload.scene_code ?? null
  const jobId = query.get('job') ?? pending?.job_id ?? null
  const tracker = useJob(scene, jobId)
  const v1 = r.jobs
    .filter((j) => j.preset === 'final' && j.technical_complete && j.video_available)
    .sort((a, b) => a.job_id.localeCompare(b.job_id))[0]
  const job = jobId
    ? (tracker.job ?? r.jobs.find((j) => j.job_id === jobId && j.scene_code === scene))
    : (v1 ?? r.jobs[0])
  const history =
    tracker.job && !r.jobs.some((j) => j.job_id === tracker.job?.job_id)
      ? [tracker.job, ...r.jobs]
      : r.jobs
  const [failedMediaJob, setFailedMediaJob] = useState<string>()
  const mediaError = Boolean(job && failedMediaJob === job.job_id)
  return (
    <>
      <PageHeading
        number="04"
        title="任务与成果中心"
        description="恢复指定任务、查看真实进度并交付对应视频；不自动重试渲染。"
      />
      {jobId && (
        <div className="connection-notice">
          <p>
            当前任务：{jobId} {tracker.loading ? '正在读取…' : ''}
          </p>
          {tracker.error && <p role="alert">{tracker.error}。进度已停止刷新，请手动重取。</p>}
          <button className="ui-button button-outline" onClick={tracker.refresh}>
            重新读取任务
          </button>
          {tracker.trace && (
            <p>
              trace_id：{tracker.trace.trace_id}{' '}
              {tracker.trace.request_id ? `request_id：${tracker.trace.request_id}` : ''}
            </p>
          )}
          {pending?.job_id === jobId && (
            <p>
              提交追踪：{pending.submission_trace_id ?? pending.trace_id ?? '未提供'}；
              {pending.request_id ?? '无提交request_id'}
            </p>
          )}
        </div>
      )}
      <div className="results-layout">
        <section className="panel history-panel">
          <div className="panel-heading">
            <h2>
              <Activity size={17} />
              真实任务历史
            </h2>
          </div>
          {history.length ? (
            history.map((j) => (
              <button
                key={j.job_id}
                className="history-button"
                aria-pressed={job?.job_id === j.job_id}
                onClick={() => {
                  setQuery({ scene: r.source?.scene_code ?? scene ?? '', job: j.job_id })
                  setFailedMediaJob(undefined)
                }}
              >
                <code>{j.job_id}</code>
                <span className="job-state">{states[j.runtime_state] ?? j.runtime_state}</span>
              </button>
            ))
          ) : (
            <StatusPanel
              state={r.status === 'loading' ? 'loading' : r.status === 'error' ? 'error' : 'empty'}
              title="暂无可显示的任务"
              description={r.error ?? '连接来源后读取已有历史，不生成演示记录。'}
              traceId={r.traceId}
            />
          )}
        </section>
        <div className="results-main">
          <section className="panel">
            <div className="panel-heading">
              <h2>已有视频成果</h2>
              <span className="badge">{job?.preset === 'final' ? '正式档归档' : '历史任务'}</span>
            </div>
            {job?.video_url && !mediaError ? (
              <video
                className="results-video"
                key={job.job_id}
                aria-label="归档任务视频"
                src={job.video_url}
                controls
                preload="metadata"
                onError={() => setFailedMediaJob(job.job_id)}
              />
            ) : (
              <StatusPanel
                state={mediaError ? 'error' : 'empty'}
                title={mediaError ? '视频读取失败' : '当前任务无可用视频'}
                description="仅播放通过技术验证的实际文件。"
              />
            )}
            <div className="result-actions">
              {job?.video_url ? (
                <a
                  className="ui-button button-outline"
                  href={job.video_url}
                  download={job.job_id + '.mp4'}
                >
                  <Download size={14} />
                  下载已有视频
                </a>
              ) : null}
              {mediaError && (
                <button
                  className="ui-button button-outline"
                  onClick={() => setFailedMediaJob(undefined)}
                >
                  重新获取视频
                </button>
              )}
            </div>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>任务进度与结果</h2>
            </div>
            {job ? (
              <>
                <dl className="data-list">
                  <div>
                    <dt>任务编号</dt>
                    <dd>
                      <code>{job.job_id}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>实际状态</dt>
                    <dd>{states[job.runtime_state] ?? job.runtime_state}</dd>
                  </div>
                  <div>
                    <dt>帧数</dt>
                    <dd>
                      {job.completed_frames ?? '—'} / {job.total_frames ?? '—'}
                    </dd>
                  </div>
                  <div>
                    <dt>本次尝试耗时</dt>
                    <dd>
                      {job.total_seconds == null ? '未提供' : job.total_seconds.toFixed(3) + ' 秒'}
                    </dd>
                  </div>
                  <div>
                    <dt>人工审核</dt>
                    <dd>
                      {job.human_acceptance === 'not_recorded'
                        ? '未记录'
                        : (job.human_acceptance ?? '未提供')}
                    </dd>
                  </div>
                  <div>
                    <dt>错误摘要</dt>
                    <dd>{job.error_code ?? '无错误码'}</dd>
                  </div>
                  <div>
                    <dt>技术校验</dt>
                    <dd>
                      {job.technical_complete === true
                        ? '已通过'
                        : job.technical_complete === false
                          ? '未完成或未通过'
                          : '未提供'}
                    </dd>
                  </div>
                  <div>
                    <dt>房间 / 资产版本</dt>
                    <dd>
                      {job.room_id ?? r.source?.room_id ?? '未提供'} /{' '}
                      {job.asset_version ?? '未提供'}
                    </dd>
                  </div>
                  <div>
                    <dt>配置摘要</dt>
                    <dd>
                      {job.style_preset ?? '—'} / {job.preset ?? '—'} / {job.camera_mode ?? '—'} /{' '}
                      {job.fps ?? '—'}帧每秒 / {job.resolution?.join('×') ?? '—'}
                    </dd>
                  </div>
                  <div>
                    <dt>GPU / 完整运行报告</dt>
                    <dd>现有只读接口未提供</dd>
                  </div>
                </dl>
                {job.completed_frames != null &&
                job.total_frames != null &&
                job.total_frames > 0 ? (
                  <div className="runtime-progress">
                    <label>
                      服务器记录的完成帧数
                      <progress value={job.completed_frames} max={job.total_frames} />
                    </label>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="panel-note">尚未选择任务。</p>
            )}
          </section>
          <details className="panel diagnostics">
            <summary className="panel-heading">
              <h2>
                <Fingerprint size={17} />
                API 诊断与追踪
              </h2>
            </summary>
            <dl className="data-list">
              <div>
                <dt>读取状态</dt>
                <dd>{r.status}</dd>
              </div>
              <div>
                <dt>最近失败追踪编号</dt>
                <dd>{r.traceId ?? '无失败编号'}</dd>
              </div>
              <div>
                <dt>读取方式</dt>
                <dd>任务查询与视频为本机同源只读请求；受控提交由独立开关保护</dd>
              </div>
            </dl>
            <p className="panel-note">
              代理读请求记录脱敏JSONL，复用既有日志字段；前端按钮全链路接收、授权日志查询仍待接入。不会向浏览器公开签名URL或服务器原始日志。
            </p>
          </details>
        </div>
      </div>
    </>
  )
}
