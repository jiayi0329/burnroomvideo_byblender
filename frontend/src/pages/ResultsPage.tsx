import { useState } from 'react'
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
  rendering: '渲染中',
  encoding: '编码中',
}
export function ResultsPage() {
  const r = useResources()
  const [chosen, setChosen] = useState<string>()
  const v1 = r.jobs
    .filter((j) => j.preset === 'final' && j.technical_complete && j.video_available)
    .sort((a, b) => a.job_id.localeCompare(b.job_id))[0]
  const job = r.jobs.find((j) => j.job_id === chosen) ?? v1 ?? r.jobs[0]
  const [mediaError, setMediaError] = useState(false)
  return (
    <>
      <PageHeading
        number="04"
        title="任务与成果中心"
        description="只读查看已有任务、文件运行状态与归档视频，不创建新任务。"
      />
      <div className="results-layout">
        <section className="panel history-panel">
          <div className="panel-heading">
            <h2>
              <Activity size={17} />
              真实任务历史
            </h2>
          </div>
          {r.jobs.length ? (
            r.jobs.map((j) => (
              <button
                key={j.job_id}
                className="history-button"
                aria-pressed={job?.job_id === j.job_id}
                onClick={() => {
                  setChosen(j.job_id)
                  setMediaError(false)
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
                onError={() => setMediaError(true)}
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
                <button className="ui-button button-outline" onClick={() => setMediaError(false)}>
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
                    <dt>GPU / 配置 / 完整运行报告</dt>
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
                <dd>本机同源只读代理</dd>
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
