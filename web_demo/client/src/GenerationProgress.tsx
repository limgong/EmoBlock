export type ProgressState={step:number;status:'queued'|'running'|'done'|'failed'|'cancelled'};

// Coarse milestones reached by the real job, not an estimated percentage or timer.
export function progressStep(phase?:string){
 const steps:Record<string,number>={BASE_COMPLETION:1,BRIDGE_DECISION:2,BRIDGE_LOCKED:2,BRIDGE_GENERATION:2,CONNECTIONS:3,BOUNDARIES:4,VALIDATION:5,ARRANGEMENT:6,RENDERING:7};
 return steps[phase||'']||0;
}

export function GenerationProgress({value,onCancel,disabled}:{value:ProgressState;onCancel?:()=>void;disabled:boolean}){
 const labels={queued:'方案已排队',running:'正在生成方案…',done:'方案已生成',failed:'生成未完成',cancelled:'已取消生成'};
 const current=value.status==='done'?8:value.step;
 return <section className={'generation-progress '+value.status} aria-label="方案生成状态">
  <div className="progress-heading"><strong role="status" aria-live="polite">{labels[value.status]}</strong>
   {onCancel&&<button disabled={disabled} onClick={onCancel}>取消生成</button>}
   {value.status==='done'&&<span className="muted">选择方案试听</span>}
  </div>
  <div className="progress-track" role="progressbar" aria-label="方案生成流程进度" aria-valuemin={0} aria-valuemax={8} aria-valuenow={current} aria-valuetext={labels[value.status]}>
   {Array.from({length:8},(_,i)=><span className="progress-part" key={i} aria-hidden="true">
    {i>0&&<span className={'progress-link '+(i<=current?'reached':'')}/>}
    <span className="progress-node" data-state={i<current?'complete':i===current?'current':'pending'}>{i<current?'✓':''}</span>
   </span>)}
  </div>
 </section>
}
